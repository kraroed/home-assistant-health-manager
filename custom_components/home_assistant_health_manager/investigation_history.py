"""Bounded local history for focused repair-prompt investigations."""

MAX_INVESTIGATIONS = 50
VALID_STATUSES = {"prompt_generated", "in_progress", "resolved", "needs_follow_up", "dismissed"}


def record_investigation(history, plan_item, prompt_path, now):
    """Record prompt creation without retaining diagnostic evidence."""
    records = [dict(item) for item in history if isinstance(item, dict)]
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
        existing["generation_count"] = int(existing.get("generation_count", 0)) + 1
        if existing.get("status") in {"resolved", "dismissed"}:
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
    records.sort(key=lambda item: item.get("last_updated", ""), reverse=True)
    return records[:MAX_INVESTIGATIONS]


def set_investigation_status(history, plan_id, status, now):
    """Update a user's tracking label for an existing investigation."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported investigation status: {status}")
    records = [dict(item) for item in history if isinstance(item, dict)]
    for item in records:
        if item.get("plan_id") == plan_id:
            item["status"] = status
            item["last_updated"] = now
            records.sort(key=lambda record: record.get("last_updated", ""), reverse=True)
            return records[:MAX_INVESTIGATIONS]
    raise ValueError("No investigation history exists for that plan ID.")


def summarize_investigations(history):
    """Return bounded counts and records for dashboard/report presentation."""
    records = [dict(item) for item in history if isinstance(item, dict)][:MAX_INVESTIGATIONS]
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for item in records:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return {
        "investigation_count": len(records),
        "investigation_status_counts": counts,
        "investigations": records,
    }
