from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "availability_grouping.py"
)
SPEC = spec_from_file_location("health_manager_availability_grouping", MODULE_PATH)
GROUPING = module_from_spec(SPEC)
SPEC.loader.exec_module(GROUPING)

NOW = "2026-11-23T12:00:00+00:00"


def _record(entity_id, device_id=None, source_domain=None, since="2026-11-23T11:00:00+00:00", present=True):
    return {
        "entity_id": entity_id,
        "state": "unavailable",
        "present": present,
        "device_id": device_id,
        "source_domain": source_domain,
        "unavailable_since": since,
    }


def test_multiple_unavailable_entities_on_same_device_form_strong_group():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", device_id="device-1"),
        "binary_sensor.two": _record("binary_sensor.two", device_id="device-1"),
        "sensor.other": _record("sensor.other", device_id="device-2"),
    }, now=NOW)
    device = next(group for group in groups if group["group_type"] == "device")
    assert device["confidence"] == "strong"
    assert device["entity_ids"] == ["binary_sensor.two", "sensor.one"]
    assert device["requires_user_review"] is True
    assert len(groups) == 2


def test_same_integration_entities_are_not_grouped_without_shared_evidence():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", source_domain="mqtt", since="2026-11-23T10:00:00+00:00"),
        "sensor.two": _record("sensor.two", source_domain="mqtt", since="2026-11-23T11:00:00+00:00"),
    }, now=NOW)
    assert len(groups) == 2
    assert all(group["group_type"] == "entity" for group in groups)


def test_simultaneous_integration_outage_forms_possible_group():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", source_domain="mqtt", since="2026-11-23T11:58:00+00:00"),
        "sensor.two": _record("sensor.two", source_domain="mqtt", since="2026-11-23T11:59:00+00:00"),
    }, now=NOW)
    assert len(groups) == 1
    assert groups[0]["group_type"] == "integration"
    assert groups[0]["confidence"] == "possible"
    assert any("began within" in evidence for evidence in groups[0]["evidence"])


def test_integration_setup_error_supports_group_even_when_outages_are_not_simultaneous():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", source_domain="mqtt", since="2026-11-23T09:00:00+00:00"),
        "sensor.two": _record("sensor.two", source_domain="mqtt", since="2026-11-23T11:00:00+00:00"),
    }, integration_inventory={
        "integrations": [{
            "domain": "mqtt", "setup_states": {"setup_error": 1},
        }]
    }, now=NOW)
    assert len(groups) == 1
    assert groups[0]["confidence"] == "strong"
    assert "The integration has a config-entry setup error." in groups[0]["evidence"]


def test_missing_and_recovered_entities_are_not_in_active_unavailable_groups():
    groups = GROUPING.build_unavailable_groups({
        "sensor.missing": _record("sensor.missing", device_id="device-1", present=False),
        "sensor.recovered": {
            "entity_id": "sensor.recovered", "state": "available", "present": True,
        },
        "sensor.active": _record("sensor.active"),
    }, now=NOW)
    assert len(groups) == 1
    assert groups[0]["entity_ids"] == ["sensor.active"]


def test_grouping_can_be_disabled_without_losing_entities():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", device_id="device-1"),
        "sensor.two": _record("sensor.two", device_id="device-1"),
    }, now=NOW, group_related=False)
    assert len(groups) == 2
    assert all(group["group_type"] == "entity" for group in groups)


def test_invalid_clock_is_rejected():
    try:
        GROUPING.build_unavailable_groups({}, now="invalid")
    except ValueError as err:
        assert "ISO 8601" in str(err)
    else:
        raise AssertionError("Invalid grouping time must be rejected")


def test_group_output_does_not_expose_raw_device_registry_identifier():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": _record("sensor.one", device_id="private-device-registry-id"),
        "sensor.two": _record("sensor.two", device_id="private-device-registry-id"),
    }, now=NOW)
    rendered = str(groups)
    assert "private-device-registry-id" not in rendered
    assert groups[0]["cause_confirmed"] is False
    assert "root cause is not confirmed" in groups[0]["confidence_scope"]


def test_automatic_grouping_includes_only_entities_past_persistence_threshold():
    groups = GROUPING.build_unavailable_groups({
        "sensor.persistent": _record("sensor.persistent", device_id="device-1"),
        "sensor.transient": _record("sensor.transient", device_id="device-1"),
    }, now=NOW, persistent_entity_ids=["sensor.persistent"])
    assert len(groups) == 1
    assert groups[0]["entity_ids"] == ["sensor.persistent"]
    assert groups[0]["group_type"] == "entity"


def test_group_exposes_latest_entity_return_time_for_reassessment():
    returned_at = "2026-11-23T11:30:00+00:00"
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": {
            **_record("sensor.one", device_id="device-1"),
            "last_returned_at": returned_at,
        },
        "sensor.two": _record("sensor.two", device_id="device-1"),
    }, now=NOW)
    device = next(group for group in groups if group["group_type"] == "device")
    assert device["latest_entity_returned_at"] == returned_at


def test_device_group_includes_friendly_device_context_without_registry_id():
    groups = GROUPING.build_unavailable_groups({
        "sensor.one": {
            **_record("sensor.one", device_id="secret-id"),
            "device_name": "Garage Controller",
            "device_manufacturer": "Acme",
            "device_model": "GX-2",
        },
        "sensor.two": {
            **_record("sensor.two", device_id="secret-id"),
            "device_name": "Garage Controller",
            "device_manufacturer": "Acme",
            "device_model": "GX-2",
        },
    }, now=NOW)
    group = next(item for item in groups if item["group_type"] == "device")
    assert group["title"] == "2 entities on Garage Controller"
    assert group["device_name"] == "Garage Controller"
    assert group["device_manufacturer"] == "Acme"
    assert group["device_model"] == "GX-2"
    assert "secret-id" not in str(group)
