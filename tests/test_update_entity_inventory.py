from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "update_entity_inventory.py"
SPEC = spec_from_file_location("health_manager_update_entity_inventory", MODULE_PATH)
INVENTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class Registry:
    def __init__(self, entries):
        self.entries = entries

    def async_get(self, entity_id):
        return self.entries.get(entity_id)


class ConfigEntries:
    def __init__(self, entries):
        self.entries = entries

    def async_get_entry(self, entry_id):
        return self.entries.get(entry_id)


def _state(entity_id, state="on", **attributes):
    return SimpleNamespace(domain="update", entity_id=entity_id, state=state, attributes=attributes)


def test_maps_provider_domain_and_config_entry_domain_without_ids():
    registry = Registry({
        "update.hacs_example": SimpleNamespace(platform="hacs", config_entry_id="private-entry-id")
    })
    entries = ConfigEntries({"private-entry-id": SimpleNamespace(domain="hacs", title="Private account")})
    result = INVENTORY.collect_update_entity_inventory(
        [_state("update.hacs_example", title="Example Integration", installed_version="1.0", latest_version="2.0")],
        registry, entries,
    )
    record = result["update_entities"][0]
    assert record["provider_integration_domain"] == "hacs"
    assert record["config_entry_domain"] == "hacs"
    assert record["title"] == "Example Integration"
    assert record["update_available"] is True
    rendered = str(result)
    assert "private-entry-id" not in rendered
    assert "Private account" not in rendered
    assert "update.hacs_example" not in rendered
    assert "not necessarily" in result["scope_note"]


def test_unknown_registry_mapping_is_reported_as_unknown():
    result = INVENTORY.collect_update_entity_inventory(
        [_state("update.orphan", "off")], Registry({}), ConfigEntries({})
    )
    record = result["update_entities"][0]
    assert record["provider_integration_domain"] == "unknown"
    assert record["config_entry_domain"] == "unknown"
    assert record["update_available"] is False


def test_inventory_is_bounded_and_reports_omissions():
    states = [_state(f"update.item_{i}") for i in range(INVENTORY.MAX_UPDATE_ENTITIES + 2)]
    result = INVENTORY.collect_update_entity_inventory(states, Registry({}), ConfigEntries({}))
    assert result["update_entity_count"] == INVENTORY.MAX_UPDATE_ENTITIES + 2
    assert result["included_update_entity_count"] == INVENTORY.MAX_UPDATE_ENTITIES
    assert result["omitted_update_entity_count"] == 2
    assert result["inventory_truncated"] is True


def test_ignores_non_update_entities():
    state = SimpleNamespace(domain="sensor", entity_id="sensor.example", state="1", attributes={})
    result = INVENTORY.collect_update_entity_inventory([state], Registry({}), ConfigEntries({}))
    assert result["update_entity_count"] == 0
    assert result["update_entities"] == []
