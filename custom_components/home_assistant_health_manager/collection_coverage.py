"""Report which diagnostic sources were available for an assessment."""


def build_collection_coverage(snapshot, core_log_status="not_checked"):
    """Return transparent source coverage without implying unavailable means healthy."""
    checks = []

    def add(key, label, available, detail):
        checks.append({
            "source": key,
            "label": label,
            "status": "collected" if available else "unavailable",
            "detail": detail,
        })

    add(
        "entity_states", "Entity states", "entity_count" in snapshot,
        "Current entity totals and state counts were collected." if "entity_count" in snapshot
        else "Entity state inventory was not available.",
    )
    add(
        "config_entries", "Integration config entries", "config_entry_count" in snapshot,
        "Config-entry totals and lifecycle states were collected." if "config_entry_count" in snapshot
        else "Config-entry inventory was not available.",
    )
    add(
        "platform_updates", "Core, Supervisor, and OS update entities",
        "platform_updates" in snapshot,
        "Available official platform update entities were inspected; missing entities are reported separately."
        if "platform_updates" in snapshot else "Platform update inventory was not available.",
    )
    add(
        "update_entity_inventory", "Update entity inventory",
        "update_entity_inventory" in snapshot,
        "Update entities were inspected within the documented inventory limit."
        if "update_entity_inventory" in snapshot else "Update entity inventory was not available.",
    )
    add(
        "integration_inventory", "Integration setup inventory",
        "integration_inventory" in snapshot,
        "Configured integration domains and setup states were collected."
        if "integration_inventory" in snapshot else "Integration setup inventory was not available.",
    )

    if core_log_status not in ("not_checked", "not_enabled"):
        status = "collected" if core_log_status == "collected" else "unavailable"
        detail = (
            "A bounded Core log tail was read and sanitized."
            if status == "collected"
            else "Core log collection was attempted but the log was unavailable."
        )
    else:
        status = core_log_status
        detail = (
            "Core log collection was not part of this snapshot refresh."
            if status == "not_checked"
            else "Core log collection is disabled in integration options."
        )
    checks.append({
        "source": "core_log",
        "label": "Home Assistant Core log",
        "status": status,
        "detail": detail,
    })

    assessed = [item for item in checks if item["status"] not in ("not_checked", "not_enabled")]
    collected = sum(item["status"] == "collected" for item in assessed)
    total = len(assessed)
    unavailable = total - collected
    percentage = round(collected / total * 100) if total else None
    overall = "not_assessed" if not assessed else (
        "complete" if unavailable == 0 else "partial" if collected else "limited"
    )
    return {
        "overall_status": overall,
        "coverage_percent": percentage,
        "available_source_count": collected,
        "assessed_source_count": total,
        "unavailable_source_count": unavailable,
        "not_assessed_source_count": sum(
            item["status"] in ("not_checked", "not_enabled") for item in checks
        ),
        "sources": checks,
        "scope_note": (
            "Coverage describes whether selected diagnostic sources could be read. "
            "It does not measure system health or prove that every relevant source was inspected. "
            "A missing source is unknown, not evidence of a healthy system."
        ),
    }
