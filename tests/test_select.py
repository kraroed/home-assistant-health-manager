"""Behavioral tests for the native investigation selectors.

Home Assistant entity base classes are stubbed so these tests exercise the
integration's selector callbacks without requiring a running HA instance.
"""
import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest


PACKAGE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
)


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def async_write_ha_state(self):
        self.state_written = True


class FakeSelectEntity:
    pass


@pytest.fixture
def selector_module(monkeypatch):
    """Load select.py with minimal Home Assistant platform stubs."""
    package_name = "health_manager_selector_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PACKAGE_PATH)]
    monkeypatch.setitem(sys.modules, package_name, package)

    const = types.ModuleType(f"{package_name}.const")
    const.DOMAIN = "home_assistant_health_manager"
    monkeypatch.setitem(sys.modules, const.__name__, const)

    focused = types.ModuleType(f"{package_name}.focused_repair_prompt")
    focused.build_repair_plan_options = lambda items: {
        item["title"]: item["plan_id"] for item in items
    }
    monkeypatch.setitem(sys.modules, focused.__name__, focused)

    ha = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    select = types.ModuleType("homeassistant.components.select")
    select.SelectEntity = FakeSelectEntity
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.CoordinatorEntity = FakeCoordinatorEntity

    for name, module in (
        ("homeassistant", ha),
        ("homeassistant.components", components),
        ("homeassistant.components.select", select),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.update_coordinator", update_coordinator),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    history = importlib.import_module(f"{package_name}.investigation_history")
    module = importlib.import_module(f"{package_name}.select")
    try:
        yield module, history
    finally:
        for name in list(sys.modules):
            if name == package_name or name.startswith(f"{package_name}."):
                sys.modules.pop(name, None)


class FakeEntry:
    entry_id = "entry"


class FakeCoordinator:
    def __init__(self, investigations):
        self.data = {"investigations": investigations}
        self.selected_investigation_plan_id = None
        self.listener_updates = 0
        self.status_updates = []

    def async_update_listeners(self):
        self.listener_updates += 1

    async def async_set_investigation_status(self, plan_id, status):
        self.status_updates.append((plan_id, status))
        for record in self.data["investigations"]:
            if record["plan_id"] == plan_id:
                record["status"] = status
                return
        raise ValueError("No investigation history exists for that plan ID.")


def sample_history():
    return [
        {
            "plan_id": "mqtt",
            "title": "MQTT setup needs review",
            "status": "in_progress",
            "last_updated": "2026-11-15T12:00:00+00:00",
        },
        {
            "plan_id": "zha",
            "title": "ZHA unavailable entities",
            "status": "prompt_generated",
            "last_updated": "2026-11-15T11:00:00+00:00",
        },
    ]


def test_history_selector_exposes_readable_options_and_current_selection(selector_module):
    module, _ = selector_module
    coordinator = FakeCoordinator(sample_history())
    entity = module.InvestigationHistorySelect(coordinator, FakeEntry())

    assert len(entity.options) == 2
    mqtt_label = next(label for label in entity.options if "[mqtt]" in label)
    assert mqtt_label.startswith("In Progress · MQTT setup needs review")
    assert entity.current_option is None

    asyncio.run(entity.async_select_option(mqtt_label))
    assert coordinator.selected_investigation_plan_id == "mqtt"
    assert coordinator.listener_updates == 1
    assert entity.current_option == mqtt_label
    assert entity.extra_state_attributes["selected_plan_id"] == "mqtt"


def test_history_selector_rejects_stale_option_without_changing_selection(selector_module):
    module, _ = selector_module
    coordinator = FakeCoordinator(sample_history())
    coordinator.selected_investigation_plan_id = "zha"
    entity = module.InvestigationHistorySelect(coordinator, FakeEntry())

    with pytest.raises(ValueError, match="no longer in the retained history"):
        asyncio.run(entity.async_select_option("old option"))

    assert coordinator.selected_investigation_plan_id == "zha"
    assert coordinator.listener_updates == 0


def test_status_selector_requires_a_valid_selected_investigation(selector_module):
    module, _ = selector_module
    coordinator = FakeCoordinator(sample_history())
    entity = module.InvestigationStatusSelect(coordinator, FakeEntry())

    assert set(entity.options) == {
        "prompt_generated", "in_progress", "resolved",
        "needs_follow_up", "dismissed",
    }
    assert entity.current_option is None
    assert entity.extra_state_attributes["selection_required"] is True

    with pytest.raises(ValueError, match="Choose an investigation"):
        asyncio.run(entity.async_select_option("resolved"))
    with pytest.raises(ValueError, match="Unsupported"):
        asyncio.run(entity.async_select_option("fixed"))

    assert coordinator.status_updates == []


def test_status_selector_updates_only_selected_record_and_reflects_new_status(selector_module):
    module, _ = selector_module
    coordinator = FakeCoordinator(sample_history())
    coordinator.selected_investigation_plan_id = "mqtt"
    entity = module.InvestigationStatusSelect(coordinator, FakeEntry())

    assert entity.current_option == "in_progress"
    asyncio.run(entity.async_select_option("needs_follow_up"))

    assert coordinator.status_updates == [("mqtt", "needs_follow_up")]
    assert entity.current_option == "needs_follow_up"
    assert coordinator.data["investigations"][1]["status"] == "prompt_generated"


def test_status_selector_handles_selection_that_went_stale(selector_module):
    module, _ = selector_module
    coordinator = FakeCoordinator(sample_history())
    coordinator.selected_investigation_plan_id = "removed"
    entity = module.InvestigationStatusSelect(coordinator, FakeEntry())

    assert entity.current_option is None
    assert entity.extra_state_attributes["selection_required"] is True
    assert entity.extra_state_attributes["selection_stale"] is True
    with pytest.raises(ValueError, match="No investigation history"):
        asyncio.run(entity.async_select_option("resolved"))
