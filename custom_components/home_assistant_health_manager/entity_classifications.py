"""Persistent, user-managed entity classifications.

Classifications are metadata only: they never delete entities or mutate HA state.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1
VALID_CLASSIFICATIONS = {"actionable", "expected", "setup_in_progress", "seasonal"}
VALID_REVIEW_INTERVALS = {"manual", "30", "60", "90"}
NON_ACTIONABLE_CLASSIFICATIONS = {"expected", "setup_in_progress", "seasonal"}


def _now_iso(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def normalize_classifications(value):
    """Normalize stored data while preserving future metadata and absent entities."""
    if not isinstance(value, dict):
        value = {}
    result = deepcopy(value)
    records = result.get("entities")
    if not isinstance(records, dict):
        records = {}
    normalized = {}
    for entity_id, record in records.items():
        if not isinstance(entity_id, str) or not entity_id or not isinstance(record, dict):
            continue
        classification = record.get("classification")
        reason = record.get("reason")
        if not isinstance(classification, str) or classification not in VALID_CLASSIFICATIONS or not isinstance(reason, str) or not reason.strip():
            continue
        item = deepcopy(record)
        item["reason"] = reason.strip()
        item.setdefault("created_at", None)
        item.setdefault("updated_at", item.get("created_at"))
        item.setdefault("last_reviewed", None)
        item.setdefault("review_due", False)
        item.setdefault("entity_missing", False)
        if not isinstance(item["entity_missing"], bool):
            item["entity_missing"] = False
        if not isinstance(item["review_due"], bool):
            item["review_due"] = False
        normalized[entity_id] = item
    result["schema_version"] = SCHEMA_VERSION
    result["entities"] = normalized
    interval = result.get("review_interval", "90")
    result["review_interval"] = interval if isinstance(interval, str) and interval in VALID_REVIEW_INTERVALS else "90"
    return result


def set_entity_classification(stored, entity_id, classification, reason, *, now=None,
                              entity_domain=None, source_domain=None, source_unique_id=None):
    """Create/update one explicitly user-managed classification."""
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("entity_id must be a non-empty string")
    if not isinstance(classification, str) or classification not in VALID_CLASSIFICATIONS:
        raise ValueError(f"Unsupported classification: {classification}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A non-empty explanation is required")
    data = normalize_classifications(stored)
    timestamp = _now_iso(now)
    previous = data["entities"].get(entity_id, {})
    record = deepcopy(previous)
    record.update({
        "entity_id": entity_id, "classification": classification,
        "reason": reason.strip(), "created_at": previous.get("created_at") or timestamp,
        "updated_at": timestamp, "last_reviewed": timestamp,
        "review_due": False, "entity_missing": False,
    })
    record.pop("review_due_reason", None)
    record.pop("review_due_reasons", None)
    record.pop("review_due_at", None)
    if entity_domain is not None:
        record["entity_domain"] = entity_domain
    if source_domain is not None:
        record["source_domain"] = source_domain
    if source_unique_id is not None:
        record["source_unique_id"] = source_unique_id
    data["entities"][entity_id] = record
    return data


def set_entity_classifications(stored, entity_ids, classification, reason, *,
                              now=None, metadata_by_entity=None):
    """Apply one explicit classification to a deduplicated entity set."""
    if not isinstance(entity_ids, (list, tuple, set)):
        raise ValueError("entity_ids must be a list of entity IDs")
    unique_ids = list(dict.fromkeys(
        entity_id.strip() for entity_id in entity_ids
        if isinstance(entity_id, str) and entity_id.strip()
    ))
    if not unique_ids:
        raise ValueError("At least one entity ID is required.")
    metadata_by_entity = metadata_by_entity if isinstance(metadata_by_entity, dict) else {}
    updated = normalize_classifications(stored)
    for entity_id in unique_ids:
        metadata = metadata_by_entity.get(entity_id, {})
        if not isinstance(metadata, dict):
            metadata = {}
        updated = set_entity_classification(
            updated, entity_id, classification, reason, now=now, **metadata
        )
    return updated


def remove_entity_classification(stored, entity_id):
    """Remove a record only after an explicit user request."""
    data = normalize_classifications(stored)
    data["entities"].pop(entity_id, None)
    return data


def _flag_review(record, reason, timestamp):
    """Retain every outstanding event trigger until the user confirms review."""
    reasons = record.get("review_due_reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    if reason not in reasons:
        reasons.append(reason)
    record["review_due"] = True
    record["review_due_reason"] = reason
    record["review_due_reasons"] = reasons
    record["review_due_at"] = timestamp

def _missing_duration_seconds(missing_since, now):
    """Return a non-negative missing duration, or None for invalid timestamps."""
    try:
        started = datetime.fromisoformat(missing_since)
        current = now if isinstance(now, datetime) else datetime.fromisoformat(now)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.0, (current - started).total_seconds())
    except (TypeError, ValueError):
        return None


def _clear_transient_missing_review(record, grace_minutes):
    """Clear legacy review flags caused only by a brief missing/return cycle."""
    reasons = record.get("review_due_reasons", [])
    if not isinstance(reasons, list):
        return
    reason_set = {reason for reason in reasons if isinstance(reason, str)}
    if len(reason_set) != len(reasons) or reason_set != {"entity_missing", "entity_returned"}:
        return
    # Reconcile only a legacy flag created by this exact short return event.
    # A previous episode's review must never be cleared by a later short restart.
    returned_at = record.get("returned_at")
    if not returned_at or record.get("review_due_at") != returned_at:
        return
    duration = _missing_duration_seconds(
        record.get("missing_since"), returned_at
    )
    if duration is None or duration >= max(1, int(grace_minutes)) * 60:
        return
    record["review_due"] = False
    record.pop("review_due_reason", None)
    record.pop("review_due_reasons", None)
    record.pop("review_due_at", None)
    record["last_missing_duration_seconds"] = round(duration, 1)
    record["last_presence_recovery"] = "within_grace_period"
    record["last_presence_recovery_at"] = record.get("returned_at")


def mark_entity_observations(
    stored, present_entity_ids, *, entity_sources=None, entity_states=None,
    now=None, missing_grace_minutes=15,
):
    """Track presence, source identity and availability transitions for review.

    Short missing/return cycles are retained as observations but do not require
    classification review. A continuously missing entity, or a return after the
    grace period, remains review-worthy.
    """
    data = normalize_classifications(stored)
    present = set(present_entity_ids)
    sources = entity_sources or {}
    states = entity_states or {}
    timestamp = _now_iso(now)
    for entity_id, record in data["entities"].items():
        if entity_id in present:
            if record.get("entity_missing"):
                duration = _missing_duration_seconds(
                    record.get("missing_since"), now or timestamp
                )
                record["entity_missing"] = False
                record["returned_at"] = timestamp
                record["last_seen"] = timestamp
                if duration is not None:
                    record["last_missing_duration_seconds"] = round(duration, 1)
                grace_seconds = max(1, int(missing_grace_minutes)) * 60
                if duration is None or duration >= grace_seconds:
                    _flag_review(record, "entity_returned", timestamp)
                    record["last_presence_recovery"] = (
                        "after_grace_period" if duration is not None else "duration_unknown"
                    )
                    record["last_presence_recovery_at"] = timestamp
                else:
                    record["last_presence_recovery"] = "within_grace_period"
                    record["last_presence_recovery_at"] = timestamp
                # Reconcile legacy flags only after this episode's return time
                # and duration have been recorded.
                _clear_transient_missing_review(record, missing_grace_minutes)
            else:
                # Also reconcile beta.10 legacy records already marked present,
                # but only when their review timestamp matches that same return.
                _clear_transient_missing_review(record, missing_grace_minutes)
                if not record.get("last_seen"):
                    record["last_seen"] = timestamp
            source = sources.get(entity_id, {})
            if isinstance(source, dict):
                for field in ("source_domain", "source_unique_id"):
                    observed = source.get(field)
                    previous = record.get(field)
                    if observed is not None and previous is None:
                        record[field] = observed
                    elif observed is not None and previous != observed:
                        record["previous_" + field] = previous
                        record[field] = observed
                        _flag_review(record, "source_changed", timestamp)
                        record["source_changed_at"] = timestamp
            current_state = states.get(entity_id)
            if current_state is not None:
                previous_state = record.get("last_observed_state")
                if previous_state is not None and previous_state != current_state:
                    if previous_state in {"unknown", "unavailable"} or current_state in {"unknown", "unavailable"}:
                        _flag_review(record, "availability_changed", timestamp)
                        record["availability_changed_at"] = timestamp
                        record["previous_observed_state"] = previous_state
                record["last_observed_state"] = current_state
        elif not record.get("entity_missing"):
            record["entity_missing"] = True
            record["missing_since"] = timestamp
            # Recovery metadata belongs to one disappearance episode only.
            # Clear stale values when a new episode begins.
            record.pop("returned_at", None)
            record.pop("last_missing_duration_seconds", None)
            record.pop("last_presence_recovery", None)
            record.pop("last_presence_recovery_at", None)
            record["missing_review_due_after"] = (
                datetime.fromisoformat(timestamp)
                + timedelta(minutes=max(1, int(missing_grace_minutes)))
            ).isoformat()
        else:
            duration = _missing_duration_seconds(
                record.get("missing_since"), now or timestamp
            )
            grace_seconds = max(1, int(missing_grace_minutes)) * 60
            if duration is None or duration >= grace_seconds:
                _flag_review(record, "entity_missing", timestamp)
    return data

def set_review_interval(stored, interval):
    """Set the user's classification review cadence."""
    if not isinstance(interval, str) or interval not in VALID_REVIEW_INTERVALS:
        raise ValueError(f"Unsupported review interval: {interval}")
    data = normalize_classifications(stored)
    data["review_interval"] = interval
    return data


def get_review_due_entities(stored, *, now=None):
    """Return explicitly triggered reviews plus periodic reviews when enabled."""
    data = normalize_classifications(stored)
    interval = data["review_interval"]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    due = []
    for entity_id, record in data["entities"].items():
        if record.get("review_due"):
            due.append(entity_id)
            continue
        # Manual disables calendar-based reviews, not event-triggered reviews.
        if interval == "manual":
            continue
        reviewed = record.get("last_reviewed") or record.get("created_at")
        try:
            reviewed_at = datetime.fromisoformat(reviewed)
            if reviewed_at.tzinfo is None:
                reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            due.append(entity_id)
            continue
        if current >= reviewed_at + timedelta(days=int(interval)):
            due.append(entity_id)
    return sorted(due)


def mark_classifications_reviewed(stored, entity_ids, *, now=None):
    """Confirm one or more classifications without changing their meaning."""
    data = normalize_classifications(stored)
    timestamp = _now_iso(now)
    for entity_id in set(entity_ids):
        record = data["entities"].get(entity_id)
        if record is None:
            continue
        record["last_reviewed"] = timestamp
        record["review_due"] = False
        record.pop("review_due_reason", None)
        record.pop("review_due_reasons", None)
        record.pop("review_due_at", None)
    return data
