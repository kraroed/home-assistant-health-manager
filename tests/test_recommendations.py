from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "recommendations.py"
SPEC = spec_from_file_location("health_manager_recommendations", MODULE_PATH)
RECOMMENDATIONS = module_from_spec(SPEC)
SPEC.loader.exec_module(RECOMMENDATIONS)


def test_failed_integration_produces_approval_gated_recommendation():
    result = RECOMMENDATIONS.build_recommendations(
        {"failed_config_entry_count": 1, "unavailable_entity_count": 0, "unknown_entity_count": 0},
        {"level_counts": {}},
    )
    assert result[0]["id"] == "failed_config_entries"
    assert result[0]["requires_user_approval"] is True
    assert result[0]["automated_action_available"] is False


def test_clean_snapshot_is_not_claimed_to_be_issue_free():
    result = RECOMMENDATIONS.build_recommendations(
        {"failed_config_entry_count": 0, "unavailable_entity_count": 0, "unknown_entity_count": 0},
        {"level_counts": {}},
    )
    assert result[0]["id"] == "no_rule_triggered"
    assert "not a guarantee" in result[0]["detail"]
