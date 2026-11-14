from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "change_history.py"
SPEC = spec_from_file_location("health_manager_change_history", MODULE_PATH)
CHANGES = module_from_spec(SPEC)
SPEC.loader.exec_module(CHANGES)


def sample_snapshot():
    return {
        "integration_inventory": {
            "integrations": [{"domain": "mqtt"}, {"domain": "zha"}],
        },
        "config_entry_states": {"loaded": 2, "setup_error": 0},
        "entity_count": 500,
        "unavailable_entity_count": 3,
        "unknown_entity_count": 1,
        "unavailable_counts_by_domain": {"sensor": 2, "light": 1},
        "unknown_counts_by_domain": {"sensor": 1},
        "platform_updates": {
            "core": {"installed_version": "2026.11.0", "latest_version": "2026.11.0", "state": "off", "update_available": False}
        },
        "update_entity_inventory": {
            "update_entities": [{
                "provider_integration_domain": "hassio", "config_entry_domain": "hassio",
                "installed_version": "1.0", "latest_version": "1.0",
                "entity_id": "update.private_entity", "title": "Private title",
            }]
        },
    }


def test_first_snapshot_establishes_baseline_without_change_event():
    history, summary = CHANGES.update_change_history([], sample_snapshot(), "2026-11-14T00:00:00Z")
    assert len(history) == 1
    assert summary["baseline_established"] is True
    assert summary["change_event_count"] == 0
    assert summary["latest_changes"] == []


def test_identical_snapshot_does_not_create_duplicate_event():
    first, _ = CHANGES.update_change_history([], sample_snapshot(), "2026-11-14T00:00:00Z")
    second, summary = CHANGES.update_change_history(first, sample_snapshot(), "2026-11-14T00:15:00Z")
    assert second == first
    assert summary["change_event_count"] == 0


def test_detects_domains_setup_state_platform_update_and_entity_inventory_changes():
    first, _ = CHANGES.update_change_history([], sample_snapshot(), "2026-11-14T00:00:00Z")
    changed = sample_snapshot()
    changed["integration_inventory"]["integrations"].append({"domain": "z-wave"})
    changed["config_entry_states"] = {"loaded": 2, "setup_error": 1}
    changed["platform_updates"]["core"]["latest_version"] = "2026.12.0"
    changed["platform_updates"]["core"]["update_available"] = True
    changed["update_entity_inventory"]["update_entities"] = []
    changed["unavailable_entity_count"] = 4
    changed["unavailable_counts_by_domain"] = {"sensor": 3, "light": 1}
    history, summary = CHANGES.update_change_history(first, changed, "2026-11-14T01:00:00Z")
    kinds = {item["type"] for item in summary["latest_changes"]}
    assert kinds == {
        "integration_domains_added",
        "config_entry_setup_state_counts_changed",
        "platform_update_signal_changed",
        "update_entity_inventory_changed",
        "entity_inventory_changed",
    }
    entity_change = next(item for item in summary["latest_changes"] if item["type"] == "entity_inventory_changed")
    assert entity_change["before"]["unavailable_entity_count"] == 3
    assert entity_change["after"]["unavailable_entity_count"] == 4
    assert summary["change_event_count"] == 1
    assert history[-1]["timestamp"] == "2026-11-14T01:00:00Z"


def test_change_history_is_bounded():
    history = []
    snapshot = sample_snapshot()
    for index in range(20):
        snapshot["config_entry_states"] = {"loaded": index}
        history, _ = CHANGES.update_change_history(history, snapshot, f"2026-11-{index + 1:02d}T00:00:00Z")
    assert len(history) <= CHANGES.MAX_CHANGE_EVENTS


def test_persisted_signature_excludes_entity_ids_and_titles():
    history, _ = CHANGES.update_change_history([], sample_snapshot(), "2026-11-14T00:00:00Z")
    serialized = str(history)
    assert "update.private_entity" not in serialized
    assert "Private title" not in serialized
