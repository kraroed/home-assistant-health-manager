"""Evidence-based grouping for related unavailable entities."""
from datetime import datetime, timezone
import hashlib

DEVICE_GROUP_MINIMUM = 2
INTEGRATION_GROUP_MINIMUM = 2
SIMULTANEOUS_WINDOW_MINUTES = 5


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _integration_signals(integration_inventory):
    result = {}
    integrations = integration_inventory.get("integrations", []) if isinstance(integration_inventory, dict) else []
    if not isinstance(integrations, list):
        return result
    for item in integrations:
        if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
            continue
        states = item.get("setup_states", {})
        if isinstance(states, dict):
            result[item["domain"]] = {
                "setup_error": bool(states.get("setup_error")),
                "setup_retry": bool(states.get("setup_retry")),
            }
    return result


def _make_group(group_id, group_type, records, now, confidence, evidence):
    entity_ids = sorted(record["entity_id"] for record in records)
    times = [_parse_time(record.get("unavailable_since")) for record in records]
    times = [value for value in times if value is not None]
    earliest = min(times) if times else None
    duration = max(0, int((now - earliest).total_seconds() // 60)) if earliest else None
    returned_times = [_parse_time(record.get("last_returned_at")) for record in records]
    returned_times = [value for value in returned_times if value is not None]
    latest_returned = max(returned_times).isoformat() if returned_times else None
    device_name = next((record.get("device_name") for record in records if record.get("device_name")), None)
    device_manufacturer = next((record.get("device_manufacturer") for record in records if record.get("device_manufacturer")), None)
    device_model = next((record.get("device_model") for record in records if record.get("device_model")), None)
    domains = sorted({
        record["source_domain"] for record in records
        if isinstance(record.get("source_domain"), str) and record.get("source_domain")
    })
    return {
        "group_id": group_id,
        "group_type": group_type,
        "title": (
            f"{len(entity_ids)} entities on {device_name}" if device_name else f"{len(entity_ids)} entities on one device"
            if group_type == "device"
            else f"{len(entity_ids)} entities from {domains[0]}"
            if group_type == "integration" and domains
            else f"{len(entity_ids)} unavailable entities"
        ),
        "entity_ids": entity_ids,
        "source_domains": domains,
        "device_name": device_name,
        "device_manufacturer": device_manufacturer,
        "device_model": device_model,
        "confidence": confidence,
        "evidence": evidence,
        "earliest_unavailable_since": earliest.isoformat() if earliest else None,
        "latest_entity_returned_at": latest_returned,
        "duration_minutes": duration,
        "requires_user_review": True,
        "cause_confirmed": False,
        "confidence_scope": "association evidence only; root cause is not confirmed",
    }


def build_unavailable_groups(
    observations,
    integration_inventory=None,
    now=None,
    group_related=True,
    simultaneous_window_minutes=SIMULTANEOUS_WINDOW_MINUTES,
    persistent_entity_ids=None,
):
    """Group only entities with concrete shared-device or integration evidence."""
    now = _parse_time(now) if now else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("now must be an ISO 8601 timestamp")
    if not isinstance(observations, dict):
        observations = {}
    active = [
        record for record in observations.values()
        if isinstance(record, dict)
        and record.get("state") == "unavailable"
        and record.get("present", True) is True
        and isinstance(record.get("entity_id"), str)
    ]
    if persistent_entity_ids is not None:
        persistent_ids = set(persistent_entity_ids)
        active = [record for record in active if record["entity_id"] in persistent_ids]
    active.sort(key=lambda record: record["entity_id"])
    if not group_related:
        return [
            _make_group(
                f"entity:{record['entity_id']}", "entity", [record], now,
                "unassessed", ["Individual unavailable entity; no grouping applied."],
            )
            for record in active
        ]

    groups = []
    assigned = set()
    by_device = {}
    for record in active:
        device_id = record.get("device_id")
        if isinstance(device_id, str) and device_id:
            by_device.setdefault(device_id, []).append(record)
    for device_id, records in sorted(by_device.items()):
        if len(records) < DEVICE_GROUP_MINIMUM:
            continue
        groups.append(_make_group(
            f"device:{hashlib.sha256(device_id.encode()).hexdigest()[:12]}", "device", records, now, "strong",
            ["Multiple unavailable entities share the same registered device."],
        ))
        assigned.update(record["entity_id"] for record in records)

    signals = _integration_signals(integration_inventory)
    by_integration = {}
    for record in active:
        if record["entity_id"] in assigned:
            continue
        domain = record.get("source_domain")
        if isinstance(domain, str) and domain:
            by_integration.setdefault(domain, []).append(record)

    window = max(0, int(simultaneous_window_minutes))
    for domain, records in sorted(by_integration.items()):
        if len(records) < INTEGRATION_GROUP_MINIMUM:
            continue
        integration_signal = signals.get(domain, {})
        starts = [_parse_time(record.get("unavailable_since")) for record in records]
        starts = [value for value in starts if value is not None]
        simultaneous = (
            len(starts) == len(records)
            and (max(starts) - min(starts)).total_seconds() <= window * 60
        )
        setup_failure = integration_signal.get("setup_error", False)
        setup_retry = integration_signal.get("setup_retry", False)
        if not (setup_failure or setup_retry or simultaneous):
            continue
        evidence = []
        if setup_failure:
            evidence.append("The integration has a config-entry setup error.")
        if setup_retry:
            evidence.append("The integration has a config-entry retry state.")
        if simultaneous:
            evidence.append(
                f"Unavailable states began within {window} minutes of one another."
            )
        confidence = "strong" if setup_failure else "possible"
        groups.append(_make_group(
            f"integration:{domain}", "integration", records, now, confidence, evidence,
        ))
        assigned.update(record["entity_id"] for record in records)

    for record in active:
        if record["entity_id"] in assigned:
            continue
        groups.append(_make_group(
            f"entity:{record['entity_id']}", "entity", [record], now,
            "unassessed", ["No shared-device or shared-integration evidence was found."],
        ))
    groups.sort(key=lambda group: (
        {"strong": 0, "possible": 1, "unassessed": 2}.get(group["confidence"], 3),
        -(group["duration_minutes"] or 0),
        group["group_id"],
    ))
    return groups
