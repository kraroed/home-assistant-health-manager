"""Defensive normalization for persisted coordinator data."""

from datetime import datetime, timedelta, timezone


def normalize_schedule_data(value, now=None):
    """Return a safe schedule dictionary while preserving valid stored history."""
    if not isinstance(value, dict):
        value = {}
    else:
        value = dict(value)

    now = now or datetime.now(timezone.utc)
    value.setdefault("next_weekly", (now + timedelta(days=7)).isoformat())
    value.setdefault("next_monthly", (now + timedelta(days=30)).isoformat())

    if not isinstance(value.get("issue_history"), dict):
        value["issue_history"] = {}
    else:
        value["issue_history"] = {
            key: item
            for key, item in value["issue_history"].items()
            if isinstance(key, str) and isinstance(item, dict)
        }

    for key in (
        "change_history",
        "trend_history",
        "integration_trend_history",
        "investigation_history",
    ):
        stored_list = value.get(key)
        value[key] = (
            [item for item in stored_list if isinstance(item, dict)]
            if isinstance(stored_list, list)
            else []
        )

    if not isinstance(value.get("last_repair_plan"), dict):
        value["last_repair_plan"] = {}
    if not isinstance(value.get("last_compatibility"), dict):
        value["last_compatibility"] = {}

    report_count = value.get("report_count", 0)
    if isinstance(report_count, bool) or not isinstance(report_count, int) or report_count < 0:
        value["report_count"] = 0

    return value
