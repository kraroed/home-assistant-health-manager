"""Inventory update entities and their registry-backed provider domains."""

MAX_UPDATE_ENTITIES = 100


def collect_update_entity_inventory(states, entity_registry, config_entries):
    """Summarize update entities without persisting entity or config-entry IDs.

    The registry platform is the integration that provides the update entity;
    it is not necessarily the integration/package being updated.
    """
    records = []
    total = 0
    for state in states:
        if getattr(state, "domain", None) != "update":
            continue
        total += 1
        if len(records) >= MAX_UPDATE_ENTITIES:
            continue
        entity_id = getattr(state, "entity_id", None)
        registry_entry = entity_registry.async_get(entity_id) if entity_id else None
        provider_domain = getattr(registry_entry, "platform", None)
        config_entry_domain = None
        config_entry_id = getattr(registry_entry, "config_entry_id", None)
        if config_entry_id:
            config_entry = config_entries.async_get_entry(config_entry_id)
            if config_entry is not None:
                config_entry_domain = getattr(config_entry, "domain", None)
        attributes = getattr(state, "attributes", {}) or {}
        records.append({
            "provider_integration_domain": provider_domain or "unknown",
            "config_entry_domain": config_entry_domain or "unknown",
            "state": getattr(state, "state", "unknown"),
            "title": _bounded_text(attributes.get("title"), 120),
            "installed_version": _bounded_text(attributes.get("installed_version"), 80),
            "latest_version": _bounded_text(attributes.get("latest_version"), 80),
            "update_available": (
                True if getattr(state, "state", None) == "on"
                else False if getattr(state, "state", None) == "off"
                else None
            ),
            "in_progress": attributes.get("in_progress") if isinstance(attributes.get("in_progress"), bool) else None,
            "release_summary": _bounded_text(attributes.get("release_summary"), 300),
            "release_url": _bounded_text(attributes.get("release_url"), 500),
        })
    return {
        "update_entity_count": total,
        "included_update_entity_count": len(records),
        "omitted_update_entity_count": max(0, total - len(records)),
        "inventory_truncated": total > MAX_UPDATE_ENTITIES,
        "update_entities": records,
        "scope_note": (
            "Provider integration domain comes from the entity registry. It identifies "
            "the integration that provides the update entity, not necessarily the "
            "integration or package being updated. Config-entry domain is included "
            "only when the registry links the entity to a resolvable config entry."
        ),
    }


def _bounded_text(value, limit):
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] or None
