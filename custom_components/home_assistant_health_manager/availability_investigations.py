"""Explicit user-managed history for unavailable-entity investigations."""
from datetime import datetime, timedelta, timezone

VALID_STATUSES = {"needs_review", "investigating", "waiting", "resolved", "expected"}


def _parse_now(value):
    if not isinstance(value, str):
        raise ValueError("now must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError("now must be an ISO 8601 timestamp") from err
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def start_investigation(investigations, group, now):
    """Create or refresh a record only in response to an explicit user action."""
    now_dt = _parse_now(now)
    if not isinstance(investigations, dict):
        investigations = {}
    if not isinstance(group, dict):
        raise ValueError("Choose a current unavailable entity group first.")
    group_id = group.get("group_id")
    entity_ids = group.get("entity_ids")
    if not isinstance(group_id, str) or not group_id or not isinstance(entity_ids, list) or not entity_ids:
        raise ValueError("The selected unavailable entity group is incomplete.")

    existing = investigations.get(group_id)
    if isinstance(existing, dict) and existing.get("status") in {"needs_review", "investigating", "waiting"}:
        updated = dict(existing)
        updated["entity_ids"] = sorted(set(entity_ids))
        updated["title"] = str(group.get("title") or existing.get("title") or "Unavailable entities")[:1000]
        updated["reason"] = "; ".join(group.get("evidence", []))[:1000]
        updated["confidence"] = group.get("confidence", "unassessed")
        updated["group_type"] = group.get("group_type", "entity")
        updated["updated_at"] = now_dt.isoformat()
        result = dict(investigations)
        result[group_id] = updated
        return result, group_id

    investigation_id = group_id
    if isinstance(existing, dict):
        investigation_id = f"{group_id}@{now_dt.strftime('%Y%m%dT%H%M%S')}"
    record = {
        "investigation_id": investigation_id,
        "group_id": group_id,
        "entity_ids": sorted(set(entity_ids)),
        "title": str(group.get("title") or "Unavailable entities")[:1000],
        "reason": "; ".join(group.get("evidence", []))[:1000],
        "confidence": group.get("confidence", "unassessed"),
        "group_type": group.get("group_type", "entity"),
        "cause_confirmed": False,
        "status": "needs_review",
        "created_at": now_dt.isoformat(),
        "updated_at": now_dt.isoformat(),
    }
    result = dict(investigations)
    result[investigation_id] = record
    return result, investigation_id


def set_investigation_status(investigations, investigation_id, status, now, reminder_days=7, user_note=None):
    """Persist an explicit user status; never changes entity classifications."""
    now_dt = _parse_now(now)
    if not isinstance(status, str) or status not in VALID_STATUSES:
        raise ValueError("Unsupported unavailable investigation status.")
    if not isinstance(investigations, dict) or not isinstance(investigations.get(investigation_id), dict):
        raise ValueError("No unavailable investigation exists with that ID.")
    result = dict(investigations)
    record = dict(result[investigation_id])
    record["status"] = status
    record["updated_at"] = now_dt.isoformat()
    record.pop("next_reminder_at", None)
    record.pop("resolved_at", None)
    if status == "waiting":
        try:
            days = min(30, max(1, int(reminder_days)))
        except (TypeError, ValueError):
            days = 7
        record["next_reminder_at"] = (now_dt + timedelta(days=days)).isoformat()
    if status == "resolved":
        record["resolved_at"] = now_dt.isoformat()
    if isinstance(user_note, str) and user_note.strip():
        record["user_note"] = user_note.strip()[:1000]
    result[investigation_id] = record
    return result


def summarize_investigations(investigations):
    """Return a bounded dashboard summary of saved user investigation records."""
    if not isinstance(investigations, dict):
        investigations = {}
    records = [
        dict(record) for record in investigations.values()
        if isinstance(record, dict) and record.get("status") in VALID_STATUSES
    ]
    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for record in records:
        counts[record["status"]] += 1
    return {
        "unavailable_investigations": records[:100],
        "unavailable_investigation_count": len(records),
        "unavailable_investigation_status_counts": counts,
        "unavailable_investigations_needing_review": sum(
            1 for record in records if record.get("status") == "needs_review"
        ),
    }
