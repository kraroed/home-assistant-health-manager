from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "integration_inventory.py"
SPEC = spec_from_file_location("health_manager_integration_inventory", MODULE_PATH)
INVENTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


def _entry(domain, state):
    return SimpleNamespace(domain=domain, state=SimpleNamespace(value=state))


def _registry_entry(entity_id, platform):
    return SimpleNamespace(entity_id=entity_id, platform=platform)


def _state(entity_id, state):
    return SimpleNamespace(
        entity_id=entity_id, state=state, domain=entity_id.split(".", 1)[0]
    )


def test_groups_config_entry_states_by_integration_domain():
    result = INVENTORY.collect_integration_inventory([
        _entry("zha", "loaded"), _entry("zha", "setup_error"), _entry("mqtt", "loaded"),
    ])
    assert result["integration_domain_count"] == 2
    assert result["included_integration_domain_count"] == 2
    assert result["inventory_truncated"] is False
    assert result["config_entry_count"] == 3
    assert result["setup_state_totals"] == {"loaded": 2, "setup_error": 1}
    assert result["integrations"] == [
        {"domain": "mqtt", "config_entry_count": 1, "setup_states": {"loaded": 1},
         "entity_count": 0, "unavailable_entity_count": 0, "unknown_entity_count": 0,
         "actionable_unknown_entity_count": 0, "origin": "not_classified"},
        {"domain": "zha", "config_entry_count": 2, "setup_states": {"loaded": 1, "setup_error": 1},
         "entity_count": 0, "unavailable_entity_count": 0, "unknown_entity_count": 0,
         "actionable_unknown_entity_count": 0, "origin": "not_classified"},
    ]
    assert result["origin_classification"] == "not_attempted"


def test_attributes_registered_entity_states_to_provider_integration():
    registry = SimpleNamespace(entities={
        "one": _registry_entry("sensor.kitchen", "mqtt"),
        "two": _registry_entry("binary_sensor.door", "zha"),
        "three": _registry_entry("sensor.disabled", "mqtt"),
    })
    states = [
        _state("sensor.kitchen", "unavailable"),
        _state("binary_sensor.door", "unknown"),
    ]
    result = INVENTORY.collect_integration_inventory([], registry, states)
    assert result["integrations"] == [
        {"domain": "mqtt", "config_entry_count": 0, "setup_states": {},
         "entity_count": 1, "unavailable_entity_count": 1, "unknown_entity_count": 0,
         "actionable_unknown_entity_count": 0, "origin": "not_classified"},
        {"domain": "zha", "config_entry_count": 0, "setup_states": {},
         "entity_count": 1, "unavailable_entity_count": 0, "unknown_entity_count": 1,
         "actionable_unknown_entity_count": 1, "origin": "not_classified"},
    ]
    assert result["attention_domains"][0]["domain"] == "mqtt"
    assert result["attention_domains"][1]["domain"] == "zha"


def test_button_domain_is_the_only_expected_unknown_domain():
    assert INVENTORY.is_actionable_unknown_domain("sensor") is True
    assert INVENTORY.is_actionable_unknown_domain("binary_sensor") is True
    assert INVENTORY.is_actionable_unknown_domain("button") is False


def test_unknown_stateless_buttons_are_raw_but_not_actionable():
    registry = SimpleNamespace(entities={
        "button": _registry_entry("button.mark_complete", "home_maintenance_manager"),
        "sensor": _registry_entry("sensor.task_status", "home_maintenance_manager"),
    })
    states = [
        _state("button.mark_complete", "unknown"),
        _state("sensor.task_status", "unknown"),
    ]
    result = INVENTORY.collect_integration_inventory([], registry, states)
    integration = result["integrations"][0]
    assert integration["unknown_entity_count"] == 2
    assert integration["actionable_unknown_entity_count"] == 1
    attention = result["attention_domains"][0]
    assert attention["signals"] == ["unknown_entities"]
    assert attention["actionable_unknown_entity_count"] == 1


def test_only_unknown_stateless_buttons_do_not_create_attention():
    registry = SimpleNamespace(entities={
        "button": _registry_entry("button.mark_complete", "home_maintenance_manager"),
    })
    result = INVENTORY.collect_integration_inventory(
        [], registry, [_state("button.mark_complete", "unknown")]
    )
    assert result["integrations"][0]["unknown_entity_count"] == 1
    assert result["integrations"][0]["actionable_unknown_entity_count"] == 0
    assert result["attention_domains"] == []


def test_attention_domain_prioritizes_setup_errors_and_bounds_results():
    entries = [_entry(f"integration_{index:03}", "setup_error") for index in range(25)]
    result = INVENTORY.collect_integration_inventory(entries)
    assert result["attention_domain_count"] == 25
    assert len(result["attention_domains"]) == INVENTORY.MAX_ATTENTION_DOMAINS
    assert result["attention_domains_truncated"] is True
    assert result["attention_domains"][0]["severity"] == "high"


def test_inventory_excludes_entry_identity_and_configuration():
    entry = SimpleNamespace(
        domain="custom_example", state=SimpleNamespace(value="loaded"),
        entry_id="private-entry-id", title="Private account", data={"token": "secret"},
        options={"password": "secret"},
    )
    registry = SimpleNamespace(entities={
        "private": _registry_entry("sensor.private_account", "custom_example"),
    })
    result = INVENTORY.collect_integration_inventory(
        [entry], registry, [_state("sensor.private_account", "unavailable")]
    )
    rendered = str(result)
    assert "private-entry-id" not in rendered
    assert "Private account" not in rendered
    assert "secret" not in rendered
    assert "sensor.private_account" not in rendered
    assert "custom_example" in rendered


def test_empty_inventory_is_explicit():
    result = INVENTORY.collect_integration_inventory([])
    assert result["integration_domain_count"] == 0
    assert result["config_entry_count"] == 0
    assert result["integrations"] == []
    assert result["attention_domains"] == []
