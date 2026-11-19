"""Persistent, user-managed entity classifications.

This module is intentionally independent of Home Assistant so its data
normalization and mutation rules can be tested without a running instance.
Classifications are metadata only: they never delete entities or mutate
Home Assistant entity state.
"""

from copy import deepcopy
from datetime import datetime, timezone

SCHEMA_VERSION = 1

VALID_CLASSIFICATIONS = {
    "actionable",
    "expected",
    "setup_in_progress",
    "seasonal",
}

VALID_REVIEW_INTERVALS = {"manual", "30", "60", "90"}


def _now_iso(now=None):
    """Return an ISO timestamp, accepting an injected clock for tests."""
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def normalize_classifications(value):
    """Normalize stored classification data without discarding valid records.

    Unknown future top-level keys and per-record metadata are preserved to
    support forward-compatible upgrades. Invalid records are ignored rather
    than interpreted as instructions to suppress entities.
    """
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
        item.setdefault("review_due", None)
        item.setdefault("entity_missing", False)
        if not isinstance(item["entity_missing"], bool):
            item["entity_missing"] = False
        normalized[entity_id] = item

    result["schema_version"] = SCHEMA_VERSION
    result["entities"] = normalized
    review_interval = result.get("review_interval", "90")
    result["review_interval"] = (
        review_interval if review_interval in VALID_REVIEW_INTERVALS else "90"
    )
    return result


def set_entity_classification(
    stored,
    entity_id,
    classification,
    reason,
    *,
    now=None,
    entity_domain=None,
    source_domain=None,
    source_unique_id=None,
):
    """Create or update one classification while preserving its metadata."""
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
        "entity_id": entity_id,
        "classification": classification,
        "reason": reason.strip(),
        "created_at": previous.get("created_at") or timestamp,
        "updated_at": timestamp,
        "last_reviewed": timestamp,
        "entity_missing": False,
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
    """Explicitly remove one record; callers must expose this as a user action."""
    data = normalize_classifications(stored)
    data["entities"].pop(entity_id, None)
    return data


def mark_entity_observations(stored, present_entity_ids, *, now=None):
    """Update last-seen/missing metadata without deleting absent records."""
    data = normalize_classifications(stored)
    present = set(present_entity_ids)
    timestamp = _now_iso(now)
    for entity_id, record in data["entities"].items():
        if entity_id in present:
            record["entity_missing"] = False
            record["last_seen"] = timestamp
        else:
            # Retain the record and its reason so it can be restored if the
            # entity returns. Missing entities are never silently discarded.
            record["entity_missing"] = True
            record.setdefault("missing_since", timestamp)
    return data


def set_review_interval(stored, interval):
    """Set the user-selected classification review cadence."""
    if interval not in VALID_REVIEW_INTERVALS:
        raise ValueError(f"Unsupported review interval: {interval}")
    data = normalize_classifications(stored)
    data["review_interval"] = interval
    return data
