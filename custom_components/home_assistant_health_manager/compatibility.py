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
    integration_inventory = snapshot.get("integration_inventory", {})
    integration_review_domains = []
    for integration in integration_inventory.get("integrations", []):
        states = integration.get("setup_states", {})
        retry_count = states.get("setup_retry", 0)
        error_count_for_domain = states.get("setup_error", 0)
        if retry_count or error_count_for_domain:
            integration_review_domains.append({
                "domain": integration.get("domain", "unknown"),
                "setup_error_count": error_count_for_domain,
                "setup_retry_count": retry_count,
            })
    integration_review_domains.sort(key=lambda item: item["domain"])
    update_inventory = snapshot.get("update_entity_inventory", {})
    health_signals = {
        "failed_config_entry_count": failed_entries,
        "failed_config_entry_domains": sorted(snapshot.get("failed_config_entry_domains", {})),
        "core_log_error_count": error_count,
        "configured_integration_domain_count": integration_inventory.get("integration_domain_count"),
        "integration_setup_state_totals": integration_inventory.get("setup_state_totals", {}),
        "integration_origin_classification": integration_inventory.get("origin_classification", "not_available"),
        "integration_domains_requiring_review": integration_review_domains,
        "integration_domain_review_count": len(integration_review_domains),
        "update_entity_count": update_inventory.get("update_entity_count", 0),
        "update_entity_inventory_truncated": update_inventory.get("inventory_truncated", False),
        "update_entities_with_available_updates": sum(
            1 for item in update_inventory.get("update_entities", [])
            if item.get("update_available") is True
        ),
    }
    if failed_entries or error_count or integration_review_domains:
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
