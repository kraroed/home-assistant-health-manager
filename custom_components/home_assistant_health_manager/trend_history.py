"""Bounded aggregate diagnostic trends across generated reports."""

MAX_TREND_POINTS = 90


def _nonnegative_int(value):
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else None


def build_trend_point(snapshot, analysis, compatibility, timestamp):
    """Create a privacy-bounded scalar-only point; no identifiers or log text."""
    coverage = snapshot.get("collection_coverage", {})
    return {
        "timestamp": str(timestamp)[:40],
        "entity_count": _nonnegative_int(snapshot.get("entity_count")),
        "unavailable_entity_count": _nonnegative_int(snapshot.get("unavailable_entity_count")),
        "unknown_entity_count": _nonnegative_int(snapshot.get("unknown_entity_count")),
        "failed_config_entry_count": _nonnegative_int(snapshot.get("failed_config_entry_count")),
        "core_log_error_count": (
            _nonnegative_int(
                sum(
                    value for key, value in analysis.get("level_counts", {}).items()
                    if str(key).upper() in ("ERROR", "CRITICAL", "FATAL")
                    and isinstance(value, int) and not isinstance(value, bool)
                )
            )
            if analysis.get("available") is True else None
        ),
        "coverage_percent": (
            max(0, min(100, coverage["coverage_percent"]))
            if isinstance(coverage.get("coverage_percent"), int) else None
        ),
        "compatibility_status": str(compatibility.get("overall_status", "not_assessed"))[:64],
    }


def update_trend_history(existing, snapshot, analysis, compatibility, timestamp):
    """Append one report-time sample and summarize changes from the previous sample."""
    history = [
        dict(item) for item in (existing or [])
        if isinstance(item, dict) and isinstance(item.get("timestamp"), str)
    ][-MAX_TREND_POINTS:]
    point = build_trend_point(snapshot, analysis, compatibility, timestamp)
    if history and history[-1] == point:
        return history, summarize_trends(history)
    history.append(point)
    history = history[-MAX_TREND_POINTS:]
    return history, summarize_trends(history)


def summarize_trends(history):
    """Compare the latest report sample with the preceding report sample."""
    points = [item for item in (history or []) if isinstance(item, dict)]
    latest = points[-1] if points else {}
    previous = points[-2] if len(points) > 1 else {}
    metrics = {}
    for key in (
        "entity_count", "unavailable_entity_count", "unknown_entity_count",
        "failed_config_entry_count", "core_log_error_count", "coverage_percent",
    ):
        current = latest.get(key)
        prior = previous.get(key)
        if isinstance(current, int) and isinstance(prior, int):
            delta = current - prior
            # More entities and coverage are generally positive; issue counts are negative.
            if key == "entity_count":
                direction = "changed" if delta else "stable"
            elif key == "coverage_percent":
                direction = "improved" if delta > 0 else "declined" if delta < 0 else "stable"
            else:
                direction = "worsened" if delta > 0 else "improved" if delta < 0 else "stable"
            metrics[key] = {"current": current, "previous": prior, "delta": delta, "direction": direction}
        else:
            metrics[key] = {
                "current": current,
                "previous": prior,
                "delta": None,
                "direction": "insufficient_data",
            }
    directional_metrics = [value for key, value in metrics.items() if key != "entity_count"]
    comparable_count = sum(
        item["direction"] != "insufficient_data" for item in directional_metrics
    )
    worsening = sum(item["direction"] in ("worsened", "declined") for item in directional_metrics)
    improving = sum(item["direction"] == "improved" for item in directional_metrics)
    overall = (
        "insufficient_data" if len(points) < 2 or comparable_count == 0
        else "mixed" if worsening and improving
        else "worsening" if worsening
        else "improving" if improving
        else "stable"
    )
    current_compatibility = latest.get("compatibility_status")
    previous_compatibility = previous.get("compatibility_status")
    return {
        "sample_count": len(points),
        "latest_sample_at": latest.get("timestamp"),
        "previous_sample_at": previous.get("timestamp") if previous else None,
        "overall_direction": overall,
        "compatibility_status": {
            "current": current_compatibility,
            "previous": previous_compatibility,
            "changed": (
                current_compatibility != previous_compatibility
                if previous else None
            ),
        },
        "metrics": metrics,
        "scope_note": (
            "Compares aggregate values at generated-report times only. It is not a continuous "
            "monitor, causal analysis, or proof that a change was caused by a particular update. "
            "Entity and issue counts can change as the installation changes."
        ),
    }
