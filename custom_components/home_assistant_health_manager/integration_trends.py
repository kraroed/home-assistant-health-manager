"""Persistent, aggregate-only trends for provider integration domains."""

MAX_INTEGRATION_TREND_POINTS = 90
MAX_INTEGRATION_TREND_DOMAINS = 250
MAX_INTEGRATION_TREND_SUMMARIES = 20


def _count(value):
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _domain_sample(item):
    setup = item.get("setup_states", {})
    setup_errors = _count(setup.get("setup_error", 0))
    setup_retries = _count(setup.get("setup_retry", 0))
    unavailable = _count(item.get("unavailable_entity_count", 0))
    unknown = _count(item.get("unknown_entity_count", 0))
    signals = []
    if setup_errors:
        signals.append("setup_error")
    if setup_retries:
        signals.append("setup_retry")
    if unavailable:
        signals.append("unavailable_entities")
    if unknown:
        signals.append("unknown_entities")
    return {
        "domain": str(item.get("domain", ""))[:128],
        "config_entry_count": _count(item.get("config_entry_count", 0)),
        "setup_error_count": setup_errors,
        "setup_retry_count": setup_retries,
        "entity_count": _count(item.get("entity_count", 0)),
        "unavailable_entity_count": unavailable,
        "unknown_entity_count": unknown,
        "attention": bool(signals),
        "signals": signals,
    }


def build_integration_trend_point(inventory, timestamp):
    """Build a bounded sample without entity/config-entry identifiers."""
    domains = inventory.get("integrations", []) if isinstance(inventory, dict) else []
    samples = [
        _domain_sample(item) for item in domains
        if isinstance(item, dict) and isinstance(item.get("domain"), str)
    ]
    samples.sort(key=lambda item: item["domain"])
    return {
        "timestamp": str(timestamp)[:40],
        "inventory_truncated": bool(inventory.get("inventory_truncated", False)),
        "domain_count": _count(inventory.get("integration_domain_count", len(samples))),
        "domains": samples[:MAX_INTEGRATION_TREND_DOMAINS],
        "domains_truncated": len(samples) > MAX_INTEGRATION_TREND_DOMAINS,
    }


def update_integration_trend_history(existing, inventory, timestamp):
    """Append a report-time provider-domain sample and return its summary."""
    history = [
        dict(item) for item in (existing or [])
        if isinstance(item, dict) and isinstance(item.get("timestamp"), str)
    ][-MAX_INTEGRATION_TREND_POINTS:]
    history.append(build_integration_trend_point(inventory, timestamp))
    history = history[-MAX_INTEGRATION_TREND_POINTS:]
    return history, summarize_integration_trends(history)


def summarize_integration_trends(history):
    """Compare provider-domain signals and count distinct attention episodes."""
    points = [item for item in (history or []) if isinstance(item, dict)]
    latest = points[-1] if points else {}
    previous = points[-2] if len(points) > 1 else {}
    latest_domains = {
        item.get("domain"): item for item in latest.get("domains", [])
        if isinstance(item, dict) and isinstance(item.get("domain"), str)
    }
    previous_domains = {
        item.get("domain"): item for item in previous.get("domains", [])
        if isinstance(item, dict) and isinstance(item.get("domain"), str)
    }
    all_domains = set()
    attention_samples = {}
    for point in points:
        for item in point.get("domains", []):
            domain = item.get("domain")
            if not isinstance(domain, str):
                continue
            all_domains.add(domain)
            attention_samples.setdefault(domain, []).append(bool(item.get("attention")))

    summaries = []
    for domain in all_domains:
        samples = attention_samples[domain]
        episodes = sum(
            current and (index == 0 or not samples[index - 1])
            for index, current in enumerate(samples)
        )
        consecutive = 0
        for active in reversed(samples):
            if not active:
                break
            consecutive += 1
        current = latest_domains.get(domain)
        prior = previous_domains.get(domain)
        if current is None:
            status = "not_in_latest_inventory"
        else:
            status = "attention" if current.get("attention") else "clear"
        deltas = {}
        for metric in (
            "setup_error_count", "setup_retry_count",
            "unavailable_entity_count", "unknown_entity_count",
        ):
            if current is not None and prior is not None:
                deltas[metric] = current.get(metric, 0) - prior.get(metric, 0)
            else:
                deltas[metric] = None
        summaries.append({
            "domain": domain,
            "status": status,
            "current_signals": current.get("signals", []) if current else [],
            "current_counts": {
                metric: current.get(metric, 0)
                for metric in (
                    "config_entry_count", "setup_error_count", "setup_retry_count",
                    "entity_count", "unavailable_entity_count", "unknown_entity_count",
                )
            } if current else {},
            "deltas_from_previous_report": deltas,
            "attention_episodes": episodes,
            "consecutive_attention_reports": consecutive,
            "recurring_attention": episodes >= 2,
        })

    summaries.sort(key=lambda item: (
        item["status"] == "attention",
        item["recurring_attention"],
        item["attention_episodes"],
        item["domain"],
    ), reverse=True)
    active = [item for item in summaries if item["status"] == "attention"]
    recurring = [item for item in summaries if item["recurring_attention"]]
    return {
        "sample_count": len(points),
        "latest_sample_at": latest.get("timestamp"),
        "previous_sample_at": previous.get("timestamp") if previous else None,
        "tracked_domain_count": len(all_domains),
        "active_attention_domain_count": len(active),
        "recurring_attention_domain_count": len(recurring),
        "domains": summaries[:MAX_INTEGRATION_TREND_SUMMARIES],
        "domains_truncated": len(summaries) > MAX_INTEGRATION_TREND_SUMMARIES,
        "inventory_truncated": bool(latest.get("inventory_truncated") or latest.get("domains_truncated")),
        "scope_note": (
            "Compares aggregate provider-integration setup and registered-entity state counts "
            "at generated-report times. An attention episode begins when a domain changes from "
            "clear or unobserved to attention; consecutive reports in one active period count "
            "as one episode. Missing domains are not assumed to be resolved. Domain attribution "
            "does not prove a shared root cause. This is not continuous monitoring."
        ),
    }
