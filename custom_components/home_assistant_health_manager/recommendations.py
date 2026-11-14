def build_recommendations(snapshot, analysis):
    """Return evidence-based, non-executing remediation suggestions."""
    items = []
    failed = snapshot.get("failed_config_entry_count", 0)
    failed_domains = snapshot.get("failed_config_entry_domains", {})
    unavailable = snapshot.get("unavailable_entity_count", 0)
    unknown = snapshot.get("unknown_entity_count", 0)
    levels = analysis.get("level_counts", {})
    errors = levels.get("ERROR", 0) + levels.get("CRITICAL", 0) + levels.get("FATAL", 0)
    warnings = levels.get("WARNING", 0)

    platform_updates = snapshot.get("platform_updates", {})
    for key, label in (
        ("core", "Home Assistant Core"),
        ("supervisor", "Home Assistant Supervisor"),
        ("operating_system", "Home Assistant Operating System"),
    ):
        update = platform_updates.get(key, {})
        if update.get("update_available") is True:
            installed = update.get("installed_version") or "unknown"
            latest = update.get("latest_version") or "unknown"
            release_note = update.get("release_summary")
            detail = f"{label} update available: installed {installed}; latest {latest}."
            if release_note:
                detail += f" Release summary: {release_note}"
            items.append({
                "id": f"{key}_update_available",
                "severity": "medium",
                "title": f"{label} update available",
                "detail": detail,
                "suggested_action": "Review the linked release notes and current Home Assistant upgrade guidance, confirm custom integrations and apps are compatible, create and verify a full backup, then schedule the update and restart during a maintenance window. Install only after reviewing the changes.",
                "release_url": update.get("release_url"),
                "requires_user_approval": True,
                "automated_action_available": False,
            })
        elif update.get("entity_present") and update.get("state") in ("unknown", "unavailable"):
            items.append({
                "id": f"{key}_update_status_unknown",
                "severity": "low",
                "title": f"{label} update status is {update.get('state')}",
                "detail": "The official update entity is present, but its current update status cannot be confirmed.",
                "suggested_action": "Check the Home Assistant Supervisor integration and its update entity availability before planning a platform upgrade.",
                "requires_user_approval": True,
                "automated_action_available": False,
            })

    if failed:
        domain_detail = (
            f" Affected integration domains: {', '.join(sorted(failed_domains))}."
            if failed_domains else ""
        )
        items.append({
            "id": "failed_config_entries",
            "severity": "high",
            "title": "One or more integrations failed to set up",
            "detail": f"The diagnostic snapshot found {failed} config entries in setup-error state.{domain_detail}",
            "suggested_action": "Review the corresponding integration setup errors in the Home Assistant log, then consult the integration documentation before attempting a reload or reconfiguration.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    if unavailable:
        items.append({
            "id": "unavailable_entities",
            "severity": "medium",
            "title": "Unavailable entities detected",
            "detail": f"The snapshot found {unavailable} unavailable entities across one or more domains.",
            "suggested_action": "Check device power, network connectivity, and the relevant integration logs. Avoid deleting entities until the underlying cause is understood.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    if unknown:
        items.append({
            "id": "unknown_entities",
            "severity": "low",
            "title": "Entities with unknown state detected",
            "detail": f"The snapshot found {unknown} entities in an unknown state.",
            "suggested_action": "Determine whether these entities are expected to have a value at this time and inspect their integration diagnostics.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    if errors:
        items.append({
            "id": "core_log_errors",
            "severity": "high" if errors >= 10 else "medium",
            "title": "Errors found in the Core log",
            "detail": f"The sanitized log analysis counted {errors} error, critical, or fatal entries in the collected log window.",
            "suggested_action": "Review the repeated error patterns and identify the responsible integration or component. Back up Home Assistant before making configuration changes.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    if warnings >= 20:
        items.append({
            "id": "repeated_warnings",
            "severity": "low",
            "title": "A high volume of warnings was recorded",
            "detail": f"The collected log window contained {warnings} warning entries.",
            "suggested_action": "Group repeated warnings by integration and investigate persistent warnings before they become errors.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    if not items:
        items.append({
            "id": "no_rule_triggered",
            "severity": "info",
            "title": "No initial diagnostic rules were triggered",
            "detail": "The limited first-release checks did not detect the conditions covered by the current rules. This is not a guarantee that the system is issue-free.",
            "suggested_action": "Continue routine monitoring and review the monthly report.",
            "requires_user_approval": True,
            "automated_action_available": False,
        })
    return items
