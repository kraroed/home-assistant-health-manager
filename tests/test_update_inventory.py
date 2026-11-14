from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "update_inventory.py"
SPEC = spec_from_file_location("health_manager_update_inventory", MODULE_PATH)
INVENTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


def _state(entity_id, title, state):
    return SimpleNamespace(
        domain="update", entity_id=entity_id, state=state,
        attributes={"title": title, "installed_version": "2026.10.0",
                    "latest_version": "2026.11.0", "release_summary": "Important fixes",
                    "release_url": "https://example.com/release", "in_progress": False},
    )


def test_collects_core_and_supervisor_updates():
    result = INVENTORY.collect_platform_updates([
        _state("update.home_assistant_core_update", "Home Assistant Core", "on"),
        _state("update.home_assistant_supervisor_update", "Home Assistant Supervisor", "off"),
    ])
    assert result["core"]["update_available"] is True
    assert result["core"]["installed_version"] == "2026.10.0"
    assert result["core"]["latest_version"] == "2026.11.0"
    assert result["supervisor"]["update_available"] is False
    assert result["operating_system"]["state"] == "missing"


def test_collects_operating_system_update():
    result = INVENTORY.collect_platform_updates([
        _state("update.home_assistant_operating_system_update", "Home Assistant Operating System", "on"),
    ])
    assert result["operating_system"]["update_available"] is True


def test_ignores_unrelated_update_entities():
    result = INVENTORY.collect_platform_updates([
        _state("update.router_firmware", "Router firmware", "on"),
    ])
    assert all(not item["entity_present"] for item in result.values())


def test_platform_update_recommendation_requires_approval():
    path = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "recommendations.py"
    spec = spec_from_file_location("health_manager_recommendations_update_test", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.build_recommendations({
        "platform_updates": {"core": {
            "entity_present": True, "state": "on", "update_available": True,
            "installed_version": "2026.10.0", "latest_version": "2026.11.0",
            "release_summary": "Important fixes", "release_url": "https://example.com/release",
        }},
        "failed_config_entry_count": 0, "unavailable_entity_count": 0, "unknown_entity_count": 0,
    }, {"level_counts": {}})
    item = next(item for item in result if item["id"] == "core_update_available")
    assert "2026.10.0" in item["detail"] and "2026.11.0" in item["detail"]
    assert item["release_url"] == "https://example.com/release"
    assert item["requires_user_approval"] is True
    assert item["automated_action_available"] is False
