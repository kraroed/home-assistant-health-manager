"""Build a privacy-bounded inventory of configured integration domains."""

from collections import Counter, defaultdict

MAX_INTEGRATION_DOMAINS = 250
MAX_ATTENTION_DOMAINS = 20


def collect_integration_inventory(entries, entity_registry=None, states=()):
    """Summarize setup and entity health by providing integration domain.

    Entity IDs and config-entry identities are used only for in-memory matching;
    neither is included in the returned inventory.
    """
    grouped = defaultdict(Counter)
    entity_counts = defaultdict(Counter)

    for entry in entries:
        domain = getattr(entry, "domain", None)
        if not isinstance(domain, str) or not domain:
            continue
        state = getattr(entry, "state", None)
        state_value = getattr(state, "value", state)
        grouped[domain][str(state_value or "unknown")] += 1

    states_by_id = {
        getattr(state, "entity_id", None): (
            getattr(state, "state", None),
            getattr(state, "domain", None),
        )
        for state in states
        if isinstance(getattr(state, "entity_id", None), str)
    }
    registry_entities = getattr(entity_registry, "entities", {}) if entity_registry else {}
    for registry_entry in getattr(registry_entities, "values", lambda: [])():
        domain = getattr(registry_entry, "platform", None)
        entity_id = getattr(registry_entry, "entity_id", None)
        if not isinstance(domain, str) or not domain or entity_id not in states_by_id:
            continue
        entity_counts[domain]["entity_count"] += 1
        state, entity_domain = states_by_id[entity_id]
        if state == "unavailable":
            entity_counts[domain]["unavailable_entity_count"] += 1
        elif state == "unknown":
            entity_counts[domain]["raw_unknown_entity_count"] += 1
            # The entity domain, not its provider integration, determines
            # whether an unknown state is expected for a stateless action.
            if entity_domain != "button":
                entity_counts[domain]["actionable_unknown_entity_count"] += 1

    all_domains = sorted(set(grouped) | set(entity_counts))
    included_domains = all_domains[:MAX_INTEGRATION_DOMAINS]
    integrations = []
    for domain in included_domains:
        setup_states = dict(sorted(grouped[domain].items()))
        entity_summary = entity_counts[domain]
        integrations.append({
            "domain": domain,
            "config_entry_count": sum(setup_states.values()),
            "setup_states": setup_states,
            "entity_count": entity_summary.get("entity_count", 0),
            "unavailable_entity_count": entity_summary.get("unavailable_entity_count", 0),
            "unknown_entity_count": entity_summary.get("raw_unknown_entity_count", 0),
            "actionable_unknown_entity_count": entity_summary.get("actionable_unknown_entity_count", 0),
            "origin": "not_classified",
        })

    totals = Counter()
    for item in integrations:
        totals.update(item["setup_states"])

    attention_domains = []
    for item in integrations:
        signals = []
        setup_states = item["setup_states"]
        if setup_states.get("setup_error", 0):
            signals.append("setup_error")
        if setup_states.get("setup_retry", 0):
            signals.append("setup_retry")
        if item["unavailable_entity_count"]:
            signals.append("unavailable_entities")
        if item["actionable_unknown_entity_count"]:
            signals.append("unknown_entities")
        if not signals:
            continue
        severity = (
            "high" if "setup_error" in signals
            else "medium" if "setup_retry" in signals or "unavailable_entities" in signals
            else "low"
        )
        attention_domains.append({
            "domain": item["domain"],
            "severity": severity,
            "signals": signals,
            "config_entry_count": item["config_entry_count"],
            "setup_states": setup_states,
            "entity_count": item["entity_count"],
            "unavailable_entity_count": item["unavailable_entity_count"],
            "unknown_entity_count": item["unknown_entity_count"],
            "actionable_unknown_entity_count": item["actionable_unknown_entity_count"],
        })
    attention_domains.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3),
            -(item["unavailable_entity_count"] + item["actionable_unknown_entity_count"]),
            item["domain"],
        )
    )

    return {
        "integration_domain_count": len(all_domains),
        "included_integration_domain_count": len(integrations),
        "omitted_integration_domain_count": max(0, len(all_domains) - len(integrations)),
        "inventory_truncated": len(all_domains) > MAX_INTEGRATION_DOMAINS,
        "config_entry_count": sum(totals.values()),
        "setup_state_totals": dict(sorted(totals.items())),
        "attention_domain_count": len(attention_domains),
        "attention_domains": attention_domains[:MAX_ATTENTION_DOMAINS],
        "attention_domains_truncated": len(attention_domains) > MAX_ATTENTION_DOMAINS,
        "origin_classification": "not_attempted",
        "integrations": integrations,
        "scope_note": (
            "Groups config-entry setup states and registered entity state counts by "
            "the integration platform that provides each entity. Entity IDs and "
            "config-entry identities are used only for in-memory matching and are "
            "not retained. Domains are not classified as Core, HACS, or manually "
            "installed, and integration versions, entry titles, data, and options "
            "are not collected. Entity counts include only registered entities "
            "with a current state."
        ),
    }
