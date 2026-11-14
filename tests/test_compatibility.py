from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "compatibility.py"
SPEC = spec_from_file_location("health_manager_compatibility", MODULE_PATH)
COMPATIBILITY = module_from_spec(SPEC)
SPEC.loader.exec_module(COMPATIBILITY)


def test_available_platform_update_requires_compatibility_review():
    result = COMPATIBILITY.assess_compatibility(
        {
            "platform_updates": {
                "core": {
                    "entity_present": True, "state": "on", "update_available": True,
                    "installed_version": "2026.10.0", "latest_version": "2026.11.0",
                }
            },
            "failed_config_entry_count": 0,
            "failed_config_entry_domains": {},
        },
        {"level_counts": {}},
    )
    assert result["overall_status"] == "platform_update_review_required"
    assert result["platforms"][0]["status"] == "review_required"
    assert result["confidence"] == "limited"
    assert "not a compatibility guarantee" in result["scope_note"]


def test_existing_failures_take_priority_over_update_status():
    result = COMPATIBILITY.assess_compatibility(
        {
            "platform_updates": {
                "core": {"entity_present": True, "state": "on", "update_available": True}
            },
            "failed_config_entry_count": 1,
            "failed_config_entry_domains": {"custom_example": 1},
        },
        {"level_counts": {"ERROR": 2}},
    )
    assert result["overall_status"] == "existing_issues_require_review"
    assert result["health_signals"]["core_log_error_count"] == 2


def test_missing_update_entities_are_not_treated_as_up_to_date():
    result = COMPATIBILITY.assess_compatibility(
        {"platform_updates": {}, "failed_config_entry_count": 0, "failed_config_entry_domains": {}},
        {"level_counts": {}},
    )
    assert result["overall_status"] == "insufficient_platform_data"
    assert all(item["status"] == "not_detected" for item in result["platforms"])
