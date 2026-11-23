"""Track unavailable-entity transitions without treating disappearance as recovery."""
from datetime import datetime, timezone

MAX_OBSERVATIONS = 2000
MAX_EVENTS = 1000


def _valid_entity_id(value):
    if not isinstance(value, str) or "." not in value:
        return False
    domain, object_id = value.split(".", 1)
    return bool(domain and object_id and len(value) <= 255)


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _append_event(events, now, action, entity_id):
    events.append({
        "occurred_at": now,
        "action": action,
        "entity_ids": [entity_id],
    })


def observe_unavailable_entities(data, current_entities, now, persistence_minutes=60):
    """Update observations from a current HA entity snapshot.

    Only unavailable entities and entities previously observed unavailable are
    retained. An entity missing from the current snapshot is marked missing;
    its outage timestamp is preserved and it is never marked recovered.
    """
    now_dt = _timestamp(now)
    if now_dt is None:
        raise ValueError("now must be an ISO 8601 timestamp")
    try:
        threshold = max(0, int(persistence_minutes))
    except (TypeError, ValueError):
        threshold = 60

    observations = dict(data.get("observations", {})) if isinstance(data, dict) else {}
    events = list(data.get("events", [])) if isinstance(data, dict) else []
    seen = set()

    for item in current_entities if isinstance(current_entities, list) else []:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        raw_state = item.get("state")
        if not _valid_entity_id(entity_id) or not isinstance(raw_state, str):
            continue
        previous = observations.get(entity_id, {})
        previous_state = previous.get("state") if isinstance(previous, dict) else None
        state = "unavailable" if raw_state == "unavailable" else (
            "unknown" if raw_state == "unknown" else "available"
        )
        if state != "unavailable" and entity_id not in observations:
            continue

        seen.add(entity_id)
        source_domain = item.get("source_domain")
        device_id = item.get("device_id")
        record = {
            "entity_id": entity_id,
            "state": state,
            "first_seen": previous.get("first_seen", now),
            "last_seen": now,
            "present": True,
        }
        if isinstance(source_domain, str) and source_domain:
            record["source_domain"] = source_domain[:255]
        elif isinstance(previous, dict) and previous.get("source_domain"):
            record["source_domain"] = previous["source_domain"]
        if isinstance(device_id, str) and device_id:
            record["device_id"] = device_id[:255]
        elif isinstance(previous, dict) and previous.get("device_id"):
            record["device_id"] = previous["device_id"]
        if isinstance(previous, dict):
            for key in ("last_missing_since", "last_returned_at"):
                if previous.get(key):
                    record[key] = previous[key]
        if isinstance(previous, dict) and previous.get("present") is False:
            if previous.get("missing_since"):
                record["last_missing_since"] = previous["missing_since"]
            record["last_returned_at"] = now
            _append_event(events, now, "entity_returned", entity_id)

        if state == "unavailable":
            since = previous.get("unavailable_since") if previous_state == "unavailable" else None
            record["unavailable_since"] = since or now
            if previous_state != "unavailable":
                _append_event(events, now, "became_unavailable", entity_id)
        else:
            if previous_state == "unavailable":
                record["last_unavailable_since"] = previous.get("unavailable_since")
                record["last_recovered_at"] = now
                _append_event(
                    events, now,
                    "recovered" if state == "available" else "availability_changed_to_unknown",
                    entity_id,
                )

        if isinstance(previous, dict):
            old_source = previous.get("source_domain")
            old_device = previous.get("device_id")
            if ((old_source and record.get("source_domain") and old_source != record["source_domain"])
                    or (old_device and record.get("device_id") and old_device != record["device_id"])):
                _append_event(events, now, "source_changed", entity_id)
        observations[entity_id] = record

    missing_entity_ids = []
    for entity_id, previous in list(observations.items()):
        if entity_id in seen or not isinstance(previous, dict):
            continue
        if previous.get("present", True):
            updated = dict(previous)
            updated["present"] = False
            updated["missing_since"] = now
            observations[entity_id] = updated
            missing_entity_ids.append(entity_id)
            _append_event(events, now, "entity_missing", entity_id)
        elif previous.get("state") == "unavailable":
            missing_entity_ids.append(entity_id)

    persistent_entity_ids = []
    for entity_id, record in observations.items():
        if not isinstance(record, dict) or record.get("state") != "unavailable":
            continue
        if record.get("present") is not True:
            continue
        since = _timestamp(record.get("unavailable_since"))
        if since is not None and (now_dt - since).total_seconds() >= threshold * 60:
            persistent_entity_ids.append(entity_id)

    return {
        "schema_version": 1,
        "observations": observations,
        "events": events[-MAX_EVENTS:],
        "persistent_entity_ids": sorted(persistent_entity_ids),
        "missing_entity_ids": sorted(missing_entity_ids),
    }
