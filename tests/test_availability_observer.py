from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "availability_observer.py"
)
SPEC = spec_from_file_location("health_manager_availability_observer", MODULE_PATH)
OBSERVER = module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


NOW = "2026-11-23T12:00:00+00:00"


def test_first_unavailable_observation_starts_duration_and_records_event():
    result = OBSERVER.observe_unavailable_entities(
        {}, [{"entity_id": "sensor.garage", "state": "unavailable", "source_domain": "mqtt"}],
        NOW, persistence_minutes=60,
    )
    record = result["observations"]["sensor.garage"]
    assert record["unavailable_since"] == NOW
    assert record["present"] is True
    assert result["persistent_entity_ids"] == []
    assert result["events"][0]["action"] == "became_unavailable"


def test_repeated_unavailable_refresh_preserves_original_start_time():
    started = "2026-11-23T10:00:00+00:00"
    data = {"observations": {"sensor.garage": {
        "entity_id": "sensor.garage", "state": "unavailable",
        "unavailable_since": started, "first_seen": started, "present": True,
    }}}
    result = OBSERVER.observe_unavailable_entities(
        data, [{"entity_id": "sensor.garage", "state": "unavailable"}],
        NOW, persistence_minutes=60,
    )
    assert result["observations"]["sensor.garage"]["unavailable_since"] == started
    assert result["persistent_entity_ids"] == ["sensor.garage"]
    assert result["events"] == []


def test_recovery_closes_active_outage_but_retains_recovery_context():
    started = "2026-11-23T10:00:00+00:00"
    data = {"observations": {"sensor.garage": {
        "entity_id": "sensor.garage", "state": "unavailable",
        "unavailable_since": started, "first_seen": started, "present": True,
    }}}
    result = OBSERVER.observe_unavailable_entities(
        data, [{"entity_id": "sensor.garage", "state": "on"}], NOW,
    )
    record = result["observations"]["sensor.garage"]
    assert record["state"] == "available"
    assert "unavailable_since" not in record
    assert record["last_unavailable_since"] == started
    assert record["last_recovered_at"] == NOW
    assert result["events"][-1]["action"] == "recovered"


def test_missing_entity_is_not_mistaken_for_recovery():
    started = "2026-11-23T10:00:00+00:00"
    data = {"observations": {"sensor.garage": {
        "entity_id": "sensor.garage", "state": "unavailable",
        "unavailable_since": started, "first_seen": started, "present": True,
    }}}
    result = OBSERVER.observe_unavailable_entities(data, [], NOW)
    record = result["observations"]["sensor.garage"]
    assert record["state"] == "unavailable"
    assert record["unavailable_since"] == started
    assert record["present"] is False
    assert record["missing_since"] == NOW
    assert result["persistent_entity_ids"] == []
    assert result["missing_entity_ids"] == ["sensor.garage"]
    assert result["events"][-1]["action"] == "entity_missing"


def test_transient_outage_does_not_cross_configured_threshold():
    started = "2026-11-23T11:45:00+00:00"
    data = {"observations": {"sensor.garage": {
        "entity_id": "sensor.garage", "state": "unavailable",
        "unavailable_since": started, "first_seen": started, "present": True,
    }}}
    result = OBSERVER.observe_unavailable_entities(
        data, [{"entity_id": "sensor.garage", "state": "unavailable"}],
        NOW, persistence_minutes=60,
    )
    assert result["persistent_entity_ids"] == []


def test_source_change_is_recorded_for_reassessment():
    data = {"observations": {"sensor.garage": {
        "entity_id": "sensor.garage", "state": "unavailable",
        "unavailable_since": NOW, "first_seen": NOW, "present": True,
        "source_domain": "mqtt", "device_id": "old-device",
    }}}
    result = OBSERVER.observe_unavailable_entities(
        data, [{
            "entity_id": "sensor.garage", "state": "unavailable",
            "source_domain": "zha", "device_id": "new-device",
        }], NOW,
    )
    assert result["events"][-1]["action"] == "source_changed"


def test_invalid_clock_is_rejected_and_malformed_items_are_ignored():
    try:
        OBSERVER.observe_unavailable_entities({}, [], "not-a-date")
    except ValueError as err:
        assert "ISO 8601" in str(err)
    else:
        raise AssertionError("Invalid observation time must be rejected")
    result = OBSERVER.observe_unavailable_entities(
        {}, [None, {"entity_id": "not-an-id", "state": "unavailable"}], NOW,
    )
    assert result["observations"] == {}
