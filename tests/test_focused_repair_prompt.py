from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "focused_repair_prompt.py"
SPEC = spec_from_file_location("health_manager_focused_prompt", MODULE_PATH)
FOCUSED = module_from_spec(SPEC)
SPEC.loader.exec_module(FOCUSED)


def test_focused_prompt_contains_only_selected_item_and_related_domain_evidence():
    context = {
        "generated_at": "2026-11-15T10:00:00+00:00",
        "repair_plan": {"items": [
            {"plan_id": "integration_mqtt", "title": "Investigate MQTT", "severity": "high",
             "recommendation_ids": ["integration_domain_mqtt"], "evidence": [{"type": "integration_trend"}],
             "requires_user_approval": True, "automated_action_available": False},
            {"plan_id": "recommendation_unavailable_entities", "title": "Unavailable entities",
             "severity": "medium", "recommendation_ids": ["unavailable_entities"], "evidence": []},
        ]},
        "recommendations": [
            {"id": "integration_domain_mqtt", "title": "MQTT setup attention", "detail": "MQTT needs review."},
            {"id": "unavailable_entities", "title": "Unavailable entities", "detail": "Three entities unavailable."},
        ],
        "snapshot": {
            "home_assistant_version": "2026.11.1",
            "platform_updates": {"core": {"installed_version": "2026.11.1"}},
            "compatibility_assessment": {"overall_status": "existing_issues_require_review"},
            "collection_coverage": {"coverage_percent": 90},
            "integration_inventory": {
                "integrations": [{"domain": "mqtt", "entity_count": 10}],
                "attention_domains": [{"domain": "mqtt", "severity": "high"}],
            },
            "integration_trend_summary": {"domains": [
                {"domain": "mqtt", "attention_episodes": 2},
                {"domain": "zha", "attention_episodes": 4},
            ]},
            "issue_history_summary": {"recurring_issues": []},
        },
        "analysis": {"integration_log_evidence": {"domains": [
            {"domain": "mqtt", "level_counts": {"ERROR": 2}},
            {"domain": "zha", "level_counts": {"WARNING": 4}},
        ]}},
    }
    prompt = FOCUSED.build_focused_repair_prompt(context, "integration_mqtt")
    assert "Investigate MQTT" in prompt
    assert "MQTT setup attention" in prompt
    assert '"domain": "mqtt"' in prompt
    assert '"attention_episodes": 2' in prompt
    assert '"ERROR": 2' in prompt
    assert "Unavailable entities" not in prompt
    assert '"domain": "zha"' not in prompt
    assert "explicit user approval" in prompt
    assert "Do not propose a system change yet" in prompt


def test_unknown_or_stale_plan_id_is_rejected():
    try:
        FOCUSED.build_focused_repair_prompt({"repair_plan": {"items": []}}, "old_item")
    except ValueError as err:
        assert "not present in the latest report" in str(err)
    else:
        raise AssertionError("Unknown plan IDs must be rejected")



def test_repair_plan_select_options_are_readable_unique_and_keep_exact_ids():
    options = FOCUSED.build_repair_plan_options([
        {"plan_id": "integration_mqtt", "severity": "high", "title": "MQTT setup attention"},
        {"plan_id": "recommendation_unavailable_entities", "severity": "medium", "title": "Unavailable entities"},
        {"plan_id": "integration_zha", "severity": "low", "title": "MQTT setup attention"},
        {"plan_id": "", "severity": "low", "title": "Invalid"},
    ])
    assert len(options) == 3
    assert len(set(options)) == 3
    assert any(label.startswith("HIGH · MQTT setup attention") for label in options)
    assert set(options.values()) == {"integration_mqtt", "recommendation_unavailable_entities", "integration_zha"}
