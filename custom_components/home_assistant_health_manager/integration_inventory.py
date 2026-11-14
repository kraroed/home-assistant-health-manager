"""Build a privacy-bounded inventory of configured integration domains."""

from collections import Counter, defaultdict


def collect_integration_inventory(entries):
    """Summarize config-entry setup states per domain without entry details."""
    grouped = defaultdict(Counter)
    for entry in entries:
        domain = getattr(entry, "domain", None)
        if not isinstance(domain, str) or not domain:
            continue
        state = getattr(entry, "state", None)
        state_value = getattr(state, "value", state)
        grouped[domain][str(state_value or "unknown")] += 1

    integrations = []
    for domain in sorted(grouped):
        states = dict(sorted(grouped[domain].items()))
        integrations.append({
            "domain": domain,
            "config_entry_count": sum(states.values()),
            "setup_states": states,
            "origin": "not_classified",
        })

    totals = Counter()
    for item in integrations:
        totals.update(item["setup_states"])
    return {
        "integration_domain_count": len(integrations),
        "config_entry_count": sum(totals.values()),
        "setup_state_totals": dict(sorted(totals.items())),
        "origin_classification": "not_attempted",
        "integrations": integrations,
        "scope_note": (
            "Lists configured integration domains and config-entry lifecycle states. "
            "It does not identify whether a domain came from Home Assistant Core, "
            "HACS, or a manually installed custom integration, and it does not "
            "collect integration versions, entry titles, IDs, data, or options."
        ),
    }
