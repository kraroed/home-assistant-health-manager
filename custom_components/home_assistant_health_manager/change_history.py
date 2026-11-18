"""Bounded, local history of meaningful diagnostic inventory changes."""

MAX_CHANGE_EVENTS = 12
MAX_DOMAINS = 250
MAX_UPDATE_SIGNATURES = 100


def _bounded_counts(values):
    if not isinstance(values, dict):
        return {}
    return {
        str(key)[:128]: max(0, value)
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))[:MAX_DOMAINS]
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _snapshot_signature(snapshot):
    """Build a bounded signature without entity IDs, entry IDs, or display titles."""
    inventory = snapshot.get("integration_inventory", {})
    integrations = inventory.get("integrations", [])
    domains = sorted({
        str(item.get("domain", ""))[:128]
        for item in integrations
        if isinstance(item, dict) and item.get("domain")
    })[:MAX_DOMAINS]
    setup_states = _bounded_counts(snapshot.get("config_entry_states", {}))
    platforms = {}
    raw_platforms = snapshot.get("platform_updates", {})
    if not isinstance(raw_platforms, dict):
        raw_platforms = {}
    for key, item in raw_platforms.items():
        if isinstance(item, dict):
            platforms[str(key)[:64]] = {
                "installed_version": _safe_value(item.get("installed_version")),
                "latest_version": _safe_value(item.get("latest_version")),
                "state": _safe_value(item.get("state")),
                "update_available": item.get("update_available")
                if isinstance(item.get("update_available"), bool) else None,
            }
    update_signatures = []
    update_inventory = snapshot.get("update_entity_inventory", {})
    update_entities = update_inventory.get("update_entities", []) if isinstance(update_inventory, dict) else []
    if not isinstance(update_entities, list):
        update_entities = []
    for item in update_entities[:MAX_UPDATE_SIGNATURES]:
        if not isinstance(item, dict):
            continue
        update_signatures.append("|".join(str(item.get(key) or "")[:128] for key in (
            "provider_integration_domain", "config_entry_domain", "installed_version", "latest_version"
        )))
    return {
        "integration_domains": domains,
        "setup_states": setup_states,
        "platforms": platforms,
        "update_entity_signatures": sorted(update_signatures),
        "entity_inventory": {
            "entity_count": max(0, snapshot.get("entity_count", 0)) if isinstance(snapshot.get("entity_count"), int) else 0,
            "unavailable_entity_count": max(0, snapshot.get("unavailable_entity_count", 0)) if isinstance(snapshot.get("unavailable_entity_count"), int) else 0,
            "unknown_entity_count": max(0, snapshot.get("unknown_entity_count", 0)) if isinstance(snapshot.get("unknown_entity_count"), int) else 0,
            "actionable_unknown_entity_count": max(0, snapshot.get("actionable_unknown_entity_count", snapshot.get("unknown_entity_count", 0))) if isinstance(snapshot.get("actionable_unknown_entity_count", snapshot.get("unknown_entity_count", 0)), int) else 0,
            "unavailable_by_domain": _bounded_counts(snapshot.get("unavailable_counts_by_domain", {})),
            "unknown_by_domain": _bounded_counts(snapshot.get("unknown_counts_by_domain", {})),
            "actionable_unknown_by_domain": _bounded_counts(snapshot.get("actionable_unknown_counts_by_domain", snapshot.get("unknown_counts_by_domain", {}))),
            "entity_counts_by_domain": _bounded_counts(snapshot.get("entity_counts_by_domain", {})),
        },
    }


def _safe_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return str(value)[:128] if value is not None else None
    return None


def update_change_history(existing, snapshot, timestamp):
    """Record a change event only when the privacy-bounded signature changes."""
    history = [item for item in (existing or []) if isinstance(item, dict)][-MAX_CHANGE_EVENTS:]
    current = _snapshot_signature(snapshot)
    if not history:
        history.append({"timestamp": timestamp, "signature": current, "change_count": 0, "changes": []})
        return history, {
            "baseline_established": True, "change_event_count": 0,
            "last_change_at": None, "latest_changes": [],
            "scope_note": _SCOPE_NOTE,
        }

    previous = history[-1].get("signature", {})
    if not isinstance(previous, dict):
        previous = {}
    changes = []
    old_domains = set(previous.get("integration_domains", []))
    new_domains = set(current["integration_domains"])
    if new_domains - old_domains:
        changes.append({"type": "integration_domains_added", "domains": sorted(new_domains - old_domains)})
    if old_domains - new_domains:
        changes.append({"type": "integration_domains_removed", "domains": sorted(old_domains - new_domains)})
    if previous.get("setup_states", {}) != current["setup_states"]:
        changes.append({
            "type": "config_entry_setup_state_counts_changed",
            "before": previous.get("setup_states", {}),
            "after": current["setup_states"],
        })
    old_platforms = previous.get("platforms", {})
    if not isinstance(old_platforms, dict):
        old_platforms = {}
    for platform in sorted(set(old_platforms) | set(current["platforms"])):
        before, after = old_platforms.get(platform), current["platforms"].get(platform)
        if before != after:
            changes.append({"type": "platform_update_signal_changed", "platform": platform, "before": before, "after": after})
    old_updates = set(previous.get("update_entity_signatures", []))
    new_updates = set(current["update_entity_signatures"])
    if old_updates != new_updates:
        changes.append({
            "type": "update_entity_inventory_changed",
            "added_count": len(new_updates - old_updates),
            "removed_count": len(old_updates - new_updates),
        })
    old_entity_inventory = previous.get("entity_inventory", {})
    old_entity_totals = {
        key: value for key, value in old_entity_inventory.items()
        if key != "entity_counts_by_domain"
    } if isinstance(old_entity_inventory, dict) else {}
    new_entity_inventory = current["entity_inventory"]
    new_entity_totals = {
        key: value for key, value in new_entity_inventory.items()
        if key != "entity_counts_by_domain"
    }
    if old_entity_totals != new_entity_totals:
        changes.append({
            "type": "entity_inventory_changed",
            "before": old_entity_totals,
            "after": new_entity_totals,
        })
    old_domain_counts = old_entity_inventory.get("entity_counts_by_domain", {}) if isinstance(old_entity_inventory, dict) else {}
    new_domain_counts = current["entity_inventory"]["entity_counts_by_domain"]
    if old_domain_counts != new_domain_counts:
        changes.append({
            "type": "entity_counts_by_domain_changed",
            "before": old_domain_counts,
            "after": new_domain_counts,
        })

    if changes:
        history.append({
            "timestamp": timestamp, "signature": current,
            "change_count": len(changes), "changes": changes,
        })
        history = history[-MAX_CHANGE_EVENTS:]
    latest = history[-1]
    summary = {
        "baseline_established": True,
        "change_event_count": sum(1 for item in history if item.get("change_count", 0)),
        "last_change_at": latest.get("timestamp") if latest.get("change_count", 0) else None,
        "latest_changes": latest.get("changes", []) if latest.get("change_count", 0) else [],
        "scope_note": _SCOPE_NOTE,
    }
    return history, summary


_SCOPE_NOTE = (
    "Tracks changes between collected diagnostic snapshots only. It records configured integration "
    "domain names, aggregate setup-state counts, platform update signals, bounded update-entity "
    "signatures, and aggregate entity availability/counts by domain. It does not prove when a change "
    "occurred, identify package sources, or guarantee "
    "compatibility. No entity IDs, config-entry IDs, titles, log text, or configuration are stored."
)
