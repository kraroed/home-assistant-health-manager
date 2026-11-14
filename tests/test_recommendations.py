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


def test_provider_domain_finding_uses_bounded_inventory_evidence():
    result = RECOMMENDATIONS.build_recommendations(
        {
            "failed_config_entry_count": 0,
            "unavailable_entity_count": 2,
            "unknown_entity_count": 0,
            "integration_inventory": {
                "attention_domains": [{
                    "domain": "mqtt", "severity": "medium",
                    "signals": ["unavailable_entities"], "config_entry_count": 1,
                    "setup_states": {"loaded": 1}, "entity_count": 4,
                    "unavailable_entity_count": 2, "unknown_entity_count": 0,
                }]
            },
        },
        {"level_counts": {}},
    )
    finding = next(item for item in result if item["id"] == "integration_domain_mqtt")
    assert "2 unavailable registered entities" in finding["detail"]
    assert finding["integration_domain"] == "mqtt"
    assert finding["requires_user_approval"] is True
    assert finding["automated_action_available"] is False


def test_clean_snapshot_is_not_claimed_to_be_issue_free():
    result = RECOMMENDATIONS.build_recommendations(
        {"failed_config_entry_count": 0, "unavailable_entity_count": 0, "unknown_entity_count": 0},
        {"level_counts": {}},
    )
    assert result[0]["id"] == "no_rule_triggered"
    assert "not a guarantee" in result[0]["detail"]


def test_active_recurring_issue_adds_approval_gated_finding():
    result = RECOMMENDATIONS.add_recurring_issue_recommendations(
        [],
        {"recurring_issues": [{
            "issue_id": "failed_config_entries", "title": "Failed integrations",
            "severity": "high", "status": "active", "occurrences": 3,
            "first_seen": "2026-11-01T00:00:00Z", "last_seen": "2026-11-15T00:00:00Z",
            "last_resolved_at": "2026-11-10T00:00:00Z",
        }]},
    )
    finding = result[0]
    assert finding["id"] == "recurring_issue_failed_config_entries"
    assert "separate time(s)" in finding["detail"]
    assert finding["requires_user_approval"] is True
    assert finding["automated_action_available"] is False


def test_resolved_recurring_issue_is_reported_but_not_active_recommended():
    result = RECOMMENDATIONS.add_recurring_issue_recommendations(
        [],
        {"recurring_issues": [{
            "issue_id": "unavailable_entities", "title": "Unavailable entities",
            "severity": "medium", "status": "resolved", "occurrences": 2,
        }]},
    )
    assert result == []


def test_worsening_integration_trend_adds_approval_gated_finding():
    result = RECOMMENDATIONS.add_integration_trend_recommendations(
        [],
        {"domains": [{
            "domain": "mqtt", "status": "attention", "recurring_attention": False,
            "attention_episodes": 1,
            "deltas_from_previous_report": {"unavailable_entity_count": 2},
            "current_counts": {"setup_error_count": 0},
        }]},
    )
    finding = result[0]
    assert finding["id"] == "integration_trend_domain_mqtt"
    assert "increased" in finding["detail"]
    assert finding["requires_user_approval"] is True
    assert finding["automated_action_available"] is False


def test_recurring_integration_attention_adds_finding_even_without_new_increase():
    result = RECOMMENDATIONS.add_integration_trend_recommendations(
        [],
        {"domains": [{
            "domain": "zha", "status": "attention", "recurring_attention": True,
            "attention_episodes": 2, "deltas_from_previous_report": {},
            "current_counts": {"setup_error_count": 1},
        }]},
    )
    assert result[0]["severity"] == "high"
    assert "2 separate report periods" in result[0]["detail"]


def test_clear_integration_trend_does_not_create_active_recommendation():
    result = RECOMMENDATIONS.add_integration_trend_recommendations(
        [],
        {"domains": [{
            "domain": "mqtt", "status": "clear", "recurring_attention": True,
            "attention_episodes": 2, "deltas_from_previous_report": {},
            "current_counts": {},
        }]},
    )
    assert result == []
