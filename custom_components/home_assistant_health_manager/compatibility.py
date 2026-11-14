"""Conservative compatibility triage based on locally observed platform/update signals."""


def assess_compatibility(snapshot, analysis):
    """Flag upgrade review needs without claiming that integrations are compatible."""
    platforms = snapshot.get("platform_updates", {})
    platform_results = []
    update_available = False
    unknown_platforms = []
    for key, label in (
        ("core", "Home Assistant Core"),
        ("supervisor", "Home Assistant Supervisor"),
        ("operating_system", "Home Assistant OS"),
    ):
        update = platforms.get(key, {})
        if not update.get("entity_present"):
            status = "not_detected"
            unknown_platforms.append(label)
        elif update.get("update_available") is True:
            status = "review_required"
            update_available = True
        elif update.get("state") == "off":
            status = "no_update_reported"
        else:
            status = "status_unknown"
            unknown_platforms.append(label)
        platform_results.append({
            "platform": label,
            "status": status,
            "installed_version": update.get("installed_version"),
            "latest_version": update.get("latest_version"),
            "release_url": update.get("release_url"),
        })

    levels = analysis.get("level_counts", {})
    error_count = sum(levels.get(level, 0) for level in ("ERROR", "CRITICAL", "FATAL"))
    failed_entries = snapshot.get("failed_config_entry_count", 0)
    health_signals = {
        "failed_config_entry_count": failed_entries,
        "failed_config_entry_domains": sorted(snapshot.get("failed_config_entry_domains", {})),
        "core_log_error_count": error_count,
    }
    if failed_entries or error_count:
        overall = "existing_issues_require_review"
    elif update_available:
        overall = "platform_update_review_required"
    elif unknown_platforms:
        overall = "insufficient_platform_data"
    else:
        overall = "no_platform_update_reported"

    return {
        "overall_status": overall,
        "platforms": platform_results,
        "health_signals": health_signals,
        "confidence": "limited",
        "scope_note": (
            "This is local triage, not a compatibility guarantee. It does not inspect every "
            "custom integration, HACS repository, add-on, dependency, or breaking change. "
            "Verify current official release notes and the affected projects before upgrading."
        ),
    }
