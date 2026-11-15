"""Conservative analysis of Home Assistant Core log levels and logger attribution."""

import re
from collections import Counter

LEVEL_RE = re.compile(r"\\b(CRITICAL|FATAL|ERROR|WARNING|WARN)\\b", re.I)
TIMESTAMP_PREFIX = re.compile(r"^\\s*\\S+\\s+\\S+\\s+")
LOGGER_RE = re.compile(r"\\([^)]*\\)\\s+\\[([A-Za-z_][A-Za-z0-9_.]*)\\]")
CORE_COMPONENT_RE = re.compile(r"^homeassistant\\.components\\.([a-z0-9_]+)(?:\\.|$)")
CUSTOM_COMPONENT_RE = re.compile(r"^custom_components\\.([a-z0-9_]+)(?:\\.|$)")


def _attributed_domain(line):
    """Return a domain only for explicit canonical component logger namespaces."""
    match = LOGGER_RE.search(line)
    if not match:
        return None
    logger_name = match.group(1)
    for pattern in (CORE_COMPONENT_RE, CUSTOM_COMPONENT_RE):
        domain_match = pattern.match(logger_name)
        if domain_match:
            return domain_match.group(1)
    return None


def analyze_log(log_text):
    if not log_text:
        return {
            "available": False,
            "line_count": 0,
            "level_counts": {},
            "top_messages": [],
            "integration_log_evidence": {
                "attribution_method": "explicit_component_logger_namespace",
                "attributed_entry_count": 0,
                "unattributed_entry_count": 0,
                "domains": [],
                "scope_note": "Only explicit homeassistant.components.<domain> and custom_components.<domain> logger namespaces are attributed. Other entries remain unattributed.",
            },
        }

    counts = Counter()
    messages = Counter()
    domain_counts = Counter()
    attributed = 0
    unattributed = 0
    for line in log_text.splitlines():
        match = LEVEL_RE.search(line)
        if not match:
            continue
        level = match.group(1).upper()
        level = "WARNING" if level == "WARN" else level
        counts[level] += 1
        normalized = TIMESTAMP_PREFIX.sub("", line)
        normalized = LEVEL_RE.sub("<LEVEL>", normalized, count=1)
        messages[normalized[:240]] += 1
        domain = _attributed_domain(line)
        if domain:
            domain_counts[(domain, level)] += 1
            attributed += 1
        else:
            unattributed += 1

    domains = {}
    for (domain, level), count in domain_counts.items():
        domains.setdefault(domain, {})[level.lower()] = count
    return {
        "available": True,
        "line_count": len(log_text.splitlines()),
        "level_counts": dict(counts),
        "top_messages": [
            {"message": message, "count": count}
            for message, count in messages.most_common(20)
        ],
        "integration_log_evidence": {
            "attribution_method": "explicit_component_logger_namespace",
            "attributed_entry_count": attributed,
            "unattributed_entry_count": unattributed,
            "domains": [
                {"domain": domain, "level_counts": levels}
                for domain, levels in sorted(domains.items())
            ],
            "scope_note": "Only explicit homeassistant.components.<domain> and custom_components.<domain> logger namespaces are attributed. Other entries remain unattributed. Attribution identifies the logger namespace, not necessarily the root cause.",
        },
    }
