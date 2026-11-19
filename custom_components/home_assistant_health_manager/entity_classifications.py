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


def mark_entity_observations(stored, present_entity_ids, *, now=None):
    """Track disappearance/return without deleting or reclassifying records."""
    data = normalize_classifications(stored)
    present = set(present_entity_ids)
    timestamp = _now_iso(now)
    for entity_id, record in data["entities"].items():
        if entity_id in present:
            if record.get("entity_missing"):
                record["entity_missing"] = False
                record["returned_at"] = timestamp
                record["review_due"] = True
                record["review_due_reason"] = "entity_returned"
            elif not record.get("last_seen"):
                record["last_seen"] = timestamp
        elif not record.get("entity_missing"):
            record["entity_missing"] = True
            record["missing_since"] = timestamp
            record["review_due"] = True
            record["review_due_reason"] = "entity_missing"
    return data


def set_review_interval(stored, interval):
    """Set the user's classification review cadence."""
    if interval not in VALID_REVIEW_INTERVALS:
        raise ValueError(f"Unsupported review interval: {interval}")
    data = normalize_classifications(stored)
    data["review_interval"] = interval
    return data


def get_review_due_entities(stored, *, now=None):
    """Return explicitly classified entities due for user review."""
    data = normalize_classifications(stored)
    interval = data["review_interval"]
    if interval == "manual":
        return []
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    due = []
    for entity_id, record in data["entities"].items():
        if record.get("review_due"):
            due.append(entity_id)
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
