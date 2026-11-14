from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "integration_inventory.py"
SPEC = spec_from_file_location("health_manager_integration_inventory", MODULE_PATH)
INVENTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


def _entry(domain, state):
    return SimpleNamespace(domain=domain, state=SimpleNamespace(value=state))


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
        {"domain": "mqtt", "config_entry_count": 1, "setup_states": {"loaded": 1}, "origin": "not_classified"},
        {"domain": "zha", "config_entry_count": 2, "setup_states": {"loaded": 1, "setup_error": 1}, "origin": "not_classified"},
    ]
    assert result["origin_classification"] == "not_attempted"


def test_inventory_excludes_entry_identity_and_configuration():
    entry = SimpleNamespace(
        domain="custom_example", state=SimpleNamespace(value="loaded"),
        entry_id="private-entry-id", title="Private account", data={"token": "secret"},
        options={"password": "secret"},
    )
    result = INVENTORY.collect_integration_inventory([entry])
    rendered = str(result)
    assert "private-entry-id" not in rendered
    assert "Private account" not in rendered
    assert "secret" not in rendered
    assert "custom_example" in rendered


def test_empty_inventory_is_explicit():
    result = INVENTORY.collect_integration_inventory([])
    assert result["integration_domain_count"] == 0
    assert result["config_entry_count"] == 0
    assert result["integrations"] == []
