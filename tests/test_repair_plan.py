from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "repair_plan.py"
SPEC = spec_from_file_location("health_manager_repair_plan", MODULE_PATH)
PLAN = module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN)


def test_groups_only_explicit_same_domain_findings_and_attaches_evidence():
    result = PLAN.build_repair_plan(
        [
            {"id": "integration_domain_mqtt", "severity": "medium", "title": "Investigate MQTT", "suggested_action": "Inspect MQTT."},
            {"id": "integration_trend_domain_mqtt", "severity": "high", "title": "MQTT trend worsening", "suggested_action": "Compare MQTT trend."},
            {"id": "unavailable_entities", "severity": "medium", "title": "Unavailable entities", "suggested_action": "Inspect unavailable entities."},
        ],
        {"domains": [{"domain": "mqtt", "level_counts": {"error": 2, "warning": 1}}]},
        {"domains": [{"domain": "mqtt", "status": "attention", "attention_episodes": 2, "current_counts": {"unavailable_entity_count": 3}, "deltas_from_previous_report": {"unavailable_entity_count": 1}}]},
    )
    mqtt = next(item for item in result["items"] if item["plan_id"] == "integration_mqtt")
    assert mqtt["severity"] == "high"
    assert mqtt["recommendation_ids"] == ["integration_domain_mqtt", "integration_trend_domain_mqtt"]
    assert mqtt["evidence"][0]["attributed_entry_count"] == 3
    assert mqtt["evidence"][1]["attention_episodes"] == 2
    assert any(item["plan_id"] == "recommendation_unavailable_entities" for item in result["items"])


def test_recurring_finding_groups_only_with_exact_base_issue_identity():
    result = PLAN.build_repair_plan([
        {"id": "failed_config_entries", "severity": "high", "title": "Failed setup", "suggested_action": "Inspect setup."},
        {"id": "recurring_issue_failed_config_entries", "severity": "medium", "title": "Recurring failed setup", "suggested_action": "Compare recurrence."},
        {"id": "recurring_issue_unavailable_entities", "severity": "low", "title": "Recurring unavailable", "suggested_action": "Check history."},
    ])
    base = next(item for item in result["items"] if item["plan_id"] == "issue_failed_config_entries")
    assert base["recommendation_ids"] == ["failed_config_entries", "recurring_issue_failed_config_entries"]
    assert any(item["plan_id"] == "recommendation_recurring_issue_unavailable_entities" for item in result["items"])


def test_plan_is_severity_sorted_bounded_and_never_authorizes_automation():
    recommendations = [
        {"id": f"finding_{index}", "severity": "low", "title": f"Finding {index}"}
        for index in range(55)
    ]
    recommendations.append({"id": "urgent", "severity": "high", "title": "Urgent"})
    result = PLAN.build_repair_plan(recommendations)
    assert result["items"][0]["plan_id"] == "recommendation_urgent"
    assert len(result["items"]) == 50
    assert result["omitted_item_count"] == 6
    assert all(item["requires_user_approval"] for item in result["items"])
    assert all(item["automated_action_available"] is False for item in result["items"])
    assert "do not establish a shared cause" in result["deduplication_policy"]
