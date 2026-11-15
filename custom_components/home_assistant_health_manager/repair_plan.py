"""Build a conservative, deduplicated, evidence-linked repair plan."""

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
MAX_PLAN_ITEMS = 50


def build_repair_plan(recommendations, integration_log_evidence=None, integration_trend_summary=None):
    """Group only recommendations with an explicit shared issue/domain identity.

    General counts are deliberately not merged with provider findings: overlapping
    counts do not prove that the findings share a cause.
    """
    recommendations = [
        item for item in recommendations
        if isinstance(item, dict) and item.get("id") != "no_rule_triggered"
    ]
    by_id = {item.get("id"): item for item in recommendations if isinstance(item.get("id"), str)}
    grouped = {}

    def group_key(item):
        issue_id = item.get("id", "")
        if issue_id.startswith("integration_domain_"):
            return ("integration", issue_id.removeprefix("integration_domain_"))
        if issue_id.startswith("integration_trend_domain_"):
            return ("integration", issue_id.removeprefix("integration_trend_domain_"))
        if issue_id.startswith("recurring_issue_"):
            base_id = issue_id.removeprefix("recurring_issue_")
            if base_id in by_id:
                return ("issue", base_id)
        return ("recommendation", issue_id)

    for item in recommendations:
        key = group_key(item)
        entry = grouped.setdefault(key, {
            "plan_id": f"{key[0]}_{key[1]}",
            "title": item.get("title", "Review diagnostic finding"),
            "severity": item.get("severity", "info"),
            "recommendation_ids": [],
            "evidence": [],
            "suggested_actions": [],
            "requires_user_approval": True,
            "automated_action_available": False,
        })
        entry["recommendation_ids"].append(item["id"])
        if item.get("suggested_action") and item["suggested_action"] not in entry["suggested_actions"]:
            entry["suggested_actions"].append(item["suggested_action"])
        if SEVERITY_ORDER.get(item.get("severity"), 4) < SEVERITY_ORDER.get(entry["severity"], 4):
            entry["severity"] = item["severity"]
            entry["title"] = item.get("title", entry["title"])

    log_domains = {
        item.get("domain"): item
        for item in (integration_log_evidence or {}).get("domains", [])
        if isinstance(item, dict) and isinstance(item.get("domain"), str)
    }
    trend_domains = {
        item.get("domain"): item
        for item in (integration_trend_summary or {}).get("domains", [])
        if isinstance(item, dict) and isinstance(item.get("domain"), str)
    }

    plan_items = []
    for (kind, identity), item in grouped.items():
        if kind == "integration":
            log_item = log_domains.get(identity)
            trend_item = trend_domains.get(identity)
            if log_item:
                item["evidence"].append({
                    "type": "explicit_component_logger",
                    "attributed_entry_count": log_item.get("entry_count", log_item.get("total_count")),
                    "severity_counts": log_item.get("level_counts", log_item.get("severity_counts", {})),
                    "interpretation": "Logger namespace identifies the emitting component, not necessarily the root cause.",
                })
            if trend_item:
                item["evidence"].append({
                    "type": "integration_trend",
                    "status": trend_item.get("status"),
                    "attention_episodes": trend_item.get("attention_episodes"),
                    "current_counts": trend_item.get("current_counts", {}),
                    "deltas_from_previous_report": trend_item.get("deltas_from_previous_report", {}),
                    "interpretation": "Trend correlation supports prioritization but does not establish causation.",
                })
        item["recommendation_ids"].sort()
        plan_items.append(item)

    plan_items.sort(key=lambda item: (
        SEVERITY_ORDER.get(item.get("severity"), 4),
        item.get("title", "").casefold(),
        item.get("plan_id", ""),
    ))
    omitted = max(0, len(plan_items) - MAX_PLAN_ITEMS)
    return {
        "items": plan_items[:MAX_PLAN_ITEMS],
        "item_count": len(plan_items),
        "omitted_item_count": omitted,
        "priority_order": ["critical", "high", "medium", "low", "info"],
        "deduplication_policy": (
            "Only exact shared provider-domain identities and explicit recurring-issue/base-issue "
            "identities are grouped. General aggregate findings remain separate because overlapping "
            "counts do not establish a shared cause."
        ),
        "scope_note": (
            "This is an advisory triage order, not a root-cause determination or an instruction "
            "to change the system. Every repair requires explicit user approval."
        ),
    }
