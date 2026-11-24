"""Regression coverage for every sensor's Recorder attribute payload."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
PACKAGE_NAME = "custom_components.home_assistant_health_manager"
PACKAGE_PATH = ROOT / "custom_components" / "home_assistant_health_manager"


def _load_sensor_module():
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PACKAGE_PATH)]
    sys.modules[PACKAGE_NAME] = package

    sensor_module = types.ModuleType("homeassistant.components.sensor")
    sensor_module.SensorEntity = type("SensorEntity", (), {})
    sensor_module.SensorStateClass = types.SimpleNamespace(
        MEASUREMENT="measurement",
        TOTAL_INCREASING="total_increasing",
    )
    helpers_module = types.ModuleType("homeassistant.helpers.update_coordinator")
    helpers_module.CoordinatorEntity = type(
        "CoordinatorEntity",
        (),
        {"__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator)},
    )
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    helpers = types.ModuleType("homeassistant.helpers")
    sys.modules.update({
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor_module,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": helpers_module,
    })

    for name in ("const", "investigation_history", "recorder_sizing"):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE_NAME}.{name}", PACKAGE_PATH / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.sensor", PACKAGE_PATH / "sensor.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SENSOR_MODULE = _load_sensor_module()
json_attribute_size = sys.modules[f"{PACKAGE_NAME}.recorder_sizing"].json_attribute_size


class Coordinator:
    def __init__(self, data):
        self.data = data
        self.selected_unavailable_investigation_id = None
        self.selected_investigation_plan_id = None


def large_synthetic_data():
    entities = [
        {
            "entity_id": f"sensor.synthetic_{index}",
            "reason": "A detailed diagnostic explanation " * 12,
            "attributes": {"source": "test", "evidence": ["same device", "same integration"]},
        }
        for index in range(500)
    ]
    return {
        "status": "attention",
        "last_assessment": "2026-11-23T12:00:00Z",
        "last_report": "2026-11-23T12:00:00Z",
        "last_report_path": "/config/health_manager/reports/health_report_test.zip",
        "report_verification": {
            "status": "verified",
            "exists": True,
            "readable": True,
            "path": "/config/health_manager/reports/health_report_test.zip",
            "size_bytes": 2048,
            "modified_at": "2026-11-23T12:00:00+00:00",
        },
        "report_count": 4,
        "active_issues": 500,
        "unavailable_entity_count": 500,
        "newly_unavailable_entity_ids": [item["entity_id"] for item in entities],
        "persistent_unavailable_entity_ids": [item["entity_id"] for item in entities],
        "missing_tracked_entity_ids": [item["entity_id"] for item in entities],
        "unavailable_investigation_groups": [
            {"title": f"Group {i}", "entity_ids": [item["entity_id"] for item in entities[i:i+20]], "evidence": entities[i:i+20]}
            for i in range(0, 500, 20)
        ],
        "unknown_entity_count": 500,
        "classification_review_due_entities": entities,
        "entity_classification_counts": {"expected": 100, "setup_in_progress": 20},
        "unknown_counts_by_domain": {f"domain_{i}": i for i in range(200)},
        "integration_inventory": {"attention_domains": [f"domain_{i}" for i in range(500)], "inventory": entities},
        "failed_config_entry_domains": {f"domain_{i}": i for i in range(500)},
        "config_entry_states": {f"entry_{i}": "setup_error" for i in range(500)},
        "integration_trend_summary": {"domains": entities},
        "unavailable_investigations": [
            {"investigation_id": f"inv_{i}", "title": f"Investigation {i}", "evidence": entities[i]}
            for i in range(500)
        ],
        "unavailable_investigation_count": 500,
        "unavailable_investigation_status_counts": {"investigating": 500},
        "platform_updates": {"core": {"state": "on"}, "supervisor": {"state": "off"}},
        "compatibility_assessment": {"overall_status": "review", "findings": entities},
        "diagnostic_change_history": {"events": entities},
        "collection_coverage": {"coverage_percent": 99, "uncovered": entities},
        "diagnostic_trend": {"overall_direction": "worsening", "events": entities},
        "investigations": entities,
        "investigation_status_counts": {"in_progress": 500},
        "recurring_issues": entities,
        "entity_count": 5000,
        "entity_counts_by_domain": {f"domain_{i}": i for i in range(500)},
        "unavailable_counts_by_domain": {f"domain_{i}": i for i in range(500)},
        "actionable_unknown_counts_by_domain": {f"domain_{i}": i for i in range(500)},
        "repair_plan": {"items": entities, "item_count": 500, "priority_order": ["critical", "high"]},
        "availability_observation_event_count": 500,
        "availability_observation_events": entities,
    }


def test_every_sensor_attribute_payload_is_recorder_safe_for_large_dataset():
    data = large_synthetic_data()
    coordinator = Coordinator(data)
    overflowed = []

    for key, _name, _unit, _state_class in SENSOR_MODULE.SENSORS:
        entity = SENSOR_MODULE.HealthManagerSensor.__new__(SENSOR_MODULE.HealthManagerSensor)
        entity.coordinator = coordinator
        entity.key = key
        attributes = entity.extra_state_attributes
        size = json_attribute_size(attributes)
        assert size <= 12_000, f"{key} emitted {size} bytes"
        if attributes.get("recorder_attribute_overflow"):
            overflowed.append(key)
            assert attributes["details_preserved_in_report"] is True
            assert attributes["full_details_report"] == data["last_report_path"]

    assert "health_overview" not in overflowed
    assert "status" not in overflowed
    assert overflowed, "Synthetic large data should exercise the explicit overflow guard"



def test_dynamic_detail_pages_preserve_large_lists_and_mappings():
    data = large_synthetic_data()
    collections = SENSOR_MODULE.PAGED_COLLECTIONS
    for collection_key in (
        "classification_review_due_entities",
        "unavailable_investigation_groups",
        "unavailable_investigations",
        "availability_observation_events",
    ):
        pages = SENSOR_MODULE._page_records(data, collection_key)
        original = SENSOR_MODULE._collection_records(data, collection_key)
        flattened = [record for page in pages for record in page]
        assert flattened == original
        assert all(
            json_attribute_size({
                "collection_key": collection_key,
                "record_kind": collections[collection_key][1],
                "records": page,
            }) <= 12_000
            for page in pages
        )

    data["unknown_counts_by_domain"] = {f"domain_{i}": i for i in range(2_000)}
    pages = SENSOR_MODULE._page_records(data, "unknown_counts_by_domain")
    flattened = [record for page in pages for record in page]
    assert {item["key"]: item["value"] for item in flattened} == data["unknown_counts_by_domain"]
    assert len(pages) > 1


def test_detail_page_sensor_exposes_page_metadata_and_records():
    data = large_synthetic_data()
    coordinator = Coordinator(data)
    entity = SENSOR_MODULE.HealthManagerDetailPageSensor(
        coordinator, types.SimpleNamespace(entry_id="test-entry"),
        "classification_review_due_entities", 1
    )
    attributes = entity.extra_state_attributes
    assert attributes["collection_key"] == "classification_review_due_entities"
    assert attributes["page"] == 1
    assert attributes["page_count"] > 1
    assert attributes["records"]
    assert json_attribute_size(attributes) <= 12_000



def test_all_registered_paged_collections_preserve_every_record_within_budget():
    data = large_synthetic_data()
    data["unknown_counts_by_domain"] = {f"domain_{i}": i for i in range(2_000)}
    for collection_key, (_path, kind) in SENSOR_MODULE.PAGED_COLLECTIONS.items():
        records = SENSOR_MODULE._collection_records(data, collection_key)
        pages = SENSOR_MODULE._page_records(data, collection_key)
        flattened = [record for page in pages for record in page]
        assert flattened == records, collection_key
        assert all(
            json_attribute_size({
                "collection_key": collection_key,
                "record_kind": kind,
                "records": page,
            }) <= 12_000
            for page in pages
        ), collection_key


def test_setup_adds_detail_pages_and_adds_more_when_collection_grows():
    import asyncio

    class ListeningCoordinator(Coordinator):
        def __init__(self, data):
            super().__init__(data)
            self.listeners = []

        def async_add_listener(self, listener):
            self.listeners.append(listener)
            return lambda: self.listeners.remove(listener)

    class Entry:
        entry_id = "test-entry"

        def async_on_unload(self, callback):
            self.unload_callback = callback

    data = large_synthetic_data()
    coordinator = ListeningCoordinator(data)
    entry = Entry()
    hass = types.SimpleNamespace(
        data={SENSOR_MODULE.DOMAIN: {entry.entry_id: coordinator}}
    )
    added = []

    def async_add_entities(entities):
        added.extend(list(entities))

    asyncio.run(SENSOR_MODULE.async_setup_entry(hass, entry, async_add_entities))
    initial_page_keys = {
        entity.key for entity in added
        if entity.key.startswith("detail_page_")
    }
    assert any(
        key.startswith("detail_page_classification_review_due_entities_")
        for key in initial_page_keys
    )
    assert coordinator.listeners

    data["classification_review_due_entities"].extend([
        {"entity_id": f"sensor.extra_{index}", "reason": "more evidence " * 30}
        for index in range(1_000)
    ])
    coordinator.listeners[0]()
    updated_page_keys = {
        entity.key for entity in added
        if entity.key.startswith("detail_page_classification_review_due_entities_")
    }
    assert len(updated_page_keys) > len({
        key for key in initial_page_keys
        if key.startswith("detail_page_classification_review_due_entities_")
    })
