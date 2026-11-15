"""Bounded local history for focused repair-prompt investigations."""

MAX_INVESTIGATIONS = 50
VALID_STATUSES = {"prompt_generated", "in_progress", "resolved", "needs_follow_up", "dismissed"}


def _sort_timestamp(item):
    """Return a comparable timestamp even when persisted history is malformed."""
    value = item.get("last_updated")
    return value if isinstance(value, str) else ""


def _generation_count(item):
    """Normalize an untrusted persisted generation counter."""
    value = item.get("generation_count", 0)
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def record_investigation(history, plan_item, prompt_path, now):
    """Record prompt creation without retaining diagnostic evidence."""
    records = [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    plan_id = plan_item.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValueError("A valid repair plan ID is required.")
    existing = next((item for item in records if item.get("plan_id") == plan_id), None)
    if existing:
        existing["title"] = str(plan_item.get("title", plan_id))[:160]
        existing["severity"] = str(plan_item.get("severity", "unknown"))[:20]
        existing["last_generated_at"] = now
        existing["last_updated"] = now
        existing["prompt_path"] = prompt_path
        existing["generation_count"] = _generation_count(existing) + 1
        if existing.get("status") in ("resolved", "dismissed"):
            existing["status"] = "prompt_generated"
    else:
        records.append({
            "plan_id": plan_id,
            "title": str(plan_item.get("title", plan_id))[:160],
            "severity": str(plan_item.get("severity", "unknown"))[:20],
            "status": "prompt_generated",
            "first_generated_at": now,
            "last_generated_at": now,
            "last_updated": now,
            "generation_count": 1,
            "prompt_path": prompt_path,
        })
    records.sort(key=_sort_timestamp, reverse=True)
    return records[:MAX_INVESTIGATIONS]


def set_investigation_status(history, plan_id, status, now):
    """Update a user's tracking label for an existing investigation."""
    if not isinstance(status, str) or status not in VALID_STATUSES:
        raise ValueError(f"Unsupported investigation status: {status}")
    records = [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    for item in records:
        if item.get("plan_id") == plan_id:
            item["status"] = status
            item["last_updated"] = now
            records.sort(key=_sort_timestamp, reverse=True)
            return records[:MAX_INVESTIGATIONS]
    raise ValueError("No investigation history exists for that plan ID.")


def summarize_investigations(history):
    """Return bounded counts and records for dashboard/report presentation."""
    records = [dict(item) for item in history if isinstance(item, dict)][:MAX_INVESTIGATIONS] if isinstance(history, list) else []
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for item in records:
        status = item.get("status")
        if isinstance(status, str) and status in counts:
            counts[status] += 1
    return {
        "investigation_count": len(records),
        "investigation_status_counts": counts,
        "investigations": records,
    }


def build_investigation_options(history):
    """Build readable dashboard choices mapped to stored investigation IDs."""
    options = {}
    records = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    records.sort(key=_sort_timestamp, reverse=True)
    for item in records[:MAX_INVESTIGATIONS]:
        plan_id = item.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            continue
        status = str(item.get("status", "unknown")).replace("_", " ").title()
        title = " ".join(str(item.get("title", plan_id)).split())
        label = f"{status} · {title[:130]} [{plan_id}]"
        options[label[:250]] = plan_id
    return options


def build_selected_investigation(data, selected_plan_id):
    """Return the selected history record and matching latest repair-plan finding."""
    if not isinstance(data, dict) or not isinstance(selected_plan_id, str):
        return {"selected": None, "finding": None}
    history = data.get("investigations", [])
    if not isinstance(history, list):
        history = []
    selected = next(
        (dict(item) for item in history if isinstance(item, dict) and item.get("plan_id") == selected_plan_id),
        None,
    )
    if selected is None:
        return {"selected": None, "finding": None}
    repair_plan = data.get("repair_plan")
    if not isinstance(repair_plan, dict):
        repair_plan = {}
    plan_items = repair_plan.get("items", [])
    if not isinstance(plan_items, list):
        plan_items = []
    finding = next(
        (dict(item) for item in plan_items if isinstance(item, dict) and item.get("plan_id") == selected_plan_id),
        None,
    )
    return {"selected": selected, "finding": finding}
