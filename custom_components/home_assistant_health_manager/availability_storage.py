"""Safe, versioned persistence helpers for unavailable-entity investigations.

This module deliberately contains no Home Assistant imports so stored data can
be normalized and tested independently of a running Home Assistant instance.
"""
from datetime import datetime

STORE_VERSION = 1
MAX_OBSERVATIONS = 2000
MAX_INVESTIGATIONS = 500
MAX_EVENTS = 1000

INVESTIGATION_STATUSES = {
    "needs_review",
    "investigating",
    "waiting",
    "resolved",
    "expected",
}


def _valid_entity_id(value):
    if not isinstance(value, str) or "." not in value:
        return False
    domain, object_id = value.split(".", 1)
    return bool(domain and object_id and len(value) <= 255)


def _valid_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _clean_text(value, limit=255):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _normalize_observation(entity_id, value):
    if not _valid_entity_id(entity_id) or not isinstance(value, dict):
        return None
    state = _clean_text(value.get("state"), 64)
    if state not in {"unavailable", "unknown", "available"}:
        return None
    result = {
        "entity_id": entity_id,
        "state": state,
    }
    for key in ("first_seen", "last_seen", "unavailable_since", "last_changed", "missing_since", "last_unavailable_since", "last_recovered_at"):
        timestamp = _valid_timestamp(value.get(key))
        if timestamp:
            result[key] = timestamp
    if isinstance(value.get("present"), bool):
        result["present"] = value["present"]
    for key in ("source_domain", "device_id"):
        text = _clean_text(value.get(key), 255)
        if text:
            result[key] = text
    return result


def _normalize_investigation(investigation_id, value):
    if not isinstance(investigation_id, str) or not investigation_id or not isinstance(value, dict):
        return None
    status = value.get("status", "needs_review")
    if not isinstance(status, str) or status not in INVESTIGATION_STATUSES:
        return None
    entity_ids = value.get("entity_ids", [])
    if not isinstance(entity_ids, list):
        return None
    clean_ids = []
    for entity_id in entity_ids:
        if _valid_entity_id(entity_id) and entity_id not in clean_ids:
            clean_ids.append(entity_id)
    if not clean_ids:
        return None
    result = {
        "investigation_id": investigation_id[:255],
        "entity_ids": clean_ids[:MAX_OBSERVATIONS],
        "status": status,
    }
    for key in ("title", "reason", "user_note"):
        text = _clean_text(value.get(key), 1000)
        if text:
            result[key] = text
    for key in ("created_at", "updated_at", "next_reminder_at", "resolved_at"):
        timestamp = _valid_timestamp(value.get(key))
        if timestamp:
            result[key] = timestamp
    return result


def normalize_availability_data(data):
    """Return a bounded, sanitized representation of persisted observations."""
    if not isinstance(data, dict):
        data = {}
    observations = {}
    raw_observations = data.get("observations", {})
    if isinstance(raw_observations, dict):
        valid_records = []
        for entity_id, value in raw_observations.items():
            record = _normalize_observation(entity_id, value)
            if record:
                valid_records.append((entity_id, record))
        # Never evict an active unavailable observation merely because the
        # store reached its retention bound. Bound inactive history first.
        active_records = [
            item for item in valid_records if item[1].get("state") == "unavailable"
        ]
        inactive_records = [
            item for item in valid_records if item[1].get("state") != "unavailable"
        ]
        inactive_records.sort(
            key=lambda item: item[1].get("last_seen", ""),
            reverse=True,
        )
        remaining = max(0, MAX_OBSERVATIONS - len(active_records))
        observations = dict(active_records + inactive_records[:remaining])

    investigations = {}
    raw_investigations = data.get("investigations", {})
    if isinstance(raw_investigations, dict):
        for investigation_id, value in raw_investigations.items():
            record = _normalize_investigation(investigation_id, value)
            if record:
                investigations[record["investigation_id"]] = record
            if len(investigations) >= MAX_INVESTIGATIONS:
                break

    events = []
    raw_events = data.get("events", [])
    if isinstance(raw_events, list):
        for event in raw_events[-MAX_EVENTS:]:
            if not isinstance(event, dict):
                continue
            occurred_at = _valid_timestamp(event.get("occurred_at"))
            action = _clean_text(event.get("action"), 64)
            if not occurred_at or not action:
                continue
            entity_ids = event.get("entity_ids", [])
            if not isinstance(entity_ids, list):
                continue
            clean_ids = []
            for entity_id in entity_ids:
                if _valid_entity_id(entity_id) and entity_id not in clean_ids:
                    clean_ids.append(entity_id)
            events.append({
                "occurred_at": occurred_at,
                "action": action,
                "entity_ids": clean_ids[:MAX_OBSERVATIONS],
            })

    return {
        "schema_version": STORE_VERSION,
        "observations": observations,
        "investigations": investigations,
        "events": events,
    }
