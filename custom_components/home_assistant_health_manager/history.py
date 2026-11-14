"""Small, privacy-conscious persistence helpers for diagnostic issue history."""

from datetime import datetime, timezone

MAX_HISTORY_ITEMS = 100
NON_ISSUE_IDS = {"no_rule_triggered"}


def update_issue_history(existing, recommendations, now=None):
    """Update issue lifecycle metadata without storing entity IDs or log text."""
    timestamp = now or datetime.now(timezone.utc).isoformat()
    history = {
        key: dict(value)
        for key, value in (existing or {}).items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    active_ids = set()

    for item in recommendations:
        issue_id = item.get("id")
        if not isinstance(issue_id, str) or issue_id in NON_ISSUE_IDS:
            continue
        active_ids.add(issue_id)
        previous = history.get(issue_id, {})
        was_resolved = previous.get("status") == "resolved"
        history[issue_id] = {
            "title": str(item.get("title", issue_id))[:160],
            "severity": str(item.get("severity", "info"))[:16],
            "status": "active",
            "first_seen": previous.get("first_seen", timestamp),
            "last_seen": timestamp,
            "last_resolved_at": previous.get("last_resolved_at") or previous.get("resolved_at"),
            "resolved_at": None,
            "occurrences": max(0, int(previous.get("occurrences", 0))) + (1 if not previous or was_resolved else 0),
        }

    for issue_id, item in history.items():
        if issue_id not in active_ids and item.get("status") == "active":
            item["status"] = "resolved"
            item["resolved_at"] = timestamp
            item["last_resolved_at"] = timestamp

    ordered = sorted(
        history.items(),
        key=lambda pair: (pair[1].get("status") == "active", pair[1].get("last_seen", "")),
        reverse=True,
    )
    return dict(ordered[:MAX_HISTORY_ITEMS])


def summarize_issue_history(history):
    """Return counts suitable for sensors and report summaries."""
    items = (history or {}).values()
    active = sum(item.get("status") == "active" for item in items)
    total = len(history or {})
    return {"tracked_issue_count": total, "active_tracked_issue_count": active, "resolved_tracked_issue_count": total - active}
