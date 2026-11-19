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
        if classification not in VALID_CLASSIFICATIONS or not isinstance(reason, str) or not reason.strip():
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
    result["review_interval"] = interval if interval in VALID_REVIEW_INTERVALS else "90"
    return result


def set_entity_classification(stored, entity_id, classification, reason, *, now=None,
                              entity_domain=None, source_domain=None, source_unique_id=None):
    """Create/update one explicitly user-managed classification."""
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("entity_id must be a non-empty string")
    if classification not in VALID_CLASSIFICATIONS:
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

def mark_entity_observations(stored, present_entity_ids, *, entity_sources=None, entity_states=None, now=None):
    """Track presence, source identity and availability transitions for review."""
    data = normalize_classifications(stored)
    present = set(present_entity_ids)
    sources = entity_sources or {}
    states = entity_states or {}
    timestamp = _now_iso(now)
    for entity_id, record in data["entities"].items():
        if entity_id in present:
            if record.get("entity_missing"):
                record["entity_missing"] = False
                record["returned_at"] = timestamp
                record["last_seen"] = timestamp
                _flag_review(record, "entity_returned", timestamp)
            elif not record.get("last_seen"):
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
            _flag_review(record, "entity_missing", timestamp)
    return data

def set_review_interval(stored, interval):
    """Set the user's classification review cadence."""
    if interval not in VALID_REVIEW_INTERVALS:
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
