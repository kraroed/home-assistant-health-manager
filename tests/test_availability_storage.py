from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "availability_storage.py"
)
SPEC = spec_from_file_location("health_manager_availability_storage", MODULE_PATH)
STORAGE = module_from_spec(SPEC)
SPEC.loader.exec_module(STORAGE)


def test_empty_or_invalid_store_normalizes_to_isolated_empty_structure():
    assert STORAGE.normalize_availability_data(None) == {
        "schema_version": 1,
        "observations": {},
        "investigations": {},
        "events": [],
    }
    assert STORAGE.normalize_availability_data(["bad"])["observations"] == {}


def test_valid_observations_and_investigations_are_preserved():
    source = {
        "observations": {
            "sensor.garage_temperature": {
                "state": "unavailable",
                "first_seen": "2026-11-20T10:00:00+00:00",
                "last_seen": "2026-11-20T11:00:00+00:00",
                "unavailable_since": "2026-11-20T10:00:00+00:00",
                "source_domain": "mqtt",
                "device_id": "device-123",
            }
        },
        "investigations": {
            "device-device-123": {
                "entity_ids": ["sensor.garage_temperature", "binary_sensor.garage_door"],
                "status": "investigating",
                "title": "Garage device unavailable",
                "reason": "Several entities from one device are unavailable",
                "created_at": "2026-11-20T11:00:00+00:00",
            }
        },
        "events": [{
            "occurred_at": "2026-11-20T11:00:00+00:00",
            "action": "investigation_created",
            "entity_ids": ["sensor.garage_temperature"],
        }],
    }
    result = STORAGE.normalize_availability_data(source)
    assert result["observations"]["sensor.garage_temperature"]["device_id"] == "device-123"
    assert result["observations"]["sensor.garage_temperature"]["unavailable_since"] == "2026-11-20T10:00:00+00:00"
    assert result["investigations"]["device-device-123"]["status"] == "investigating"
    assert result["investigations"]["device-device-123"]["entity_ids"] == [
        "sensor.garage_temperature", "binary_sensor.garage_door"
    ]
    assert result["events"][0]["action"] == "investigation_created"


def test_missing_entity_is_not_rewritten_as_recovered():
    source = {
        "observations": {
            "sensor.garage_temperature": {
                "state": "unavailable",
                "unavailable_since": "2026-11-20T10:00:00+00:00",
            }
        }
    }
    result = STORAGE.normalize_availability_data(source)
    record = result["observations"]["sensor.garage_temperature"]
    assert record["state"] == "unavailable"
    assert record["unavailable_since"] == "2026-11-20T10:00:00+00:00"


def test_invalid_records_and_timestamps_are_discarded_without_losing_valid_data():
    result = STORAGE.normalize_availability_data({
        "observations": {
            "not-an-entity": {"state": "unavailable"},
            "sensor.bad_state": {"state": "offline"},
            "sensor.bad_time": {"state": "unavailable", "unavailable_since": "yesterday"},
            "sensor.good": {"state": "available"},
        },
        "investigations": {
            "bad_status": {"entity_ids": ["sensor.good"], "status": "auto_dismissed"},
            "empty": {"entity_ids": [], "status": "needs_review"},
            "good": {"entity_ids": ["sensor.good"], "status": "expected"},
        },
        "events": [
            {"occurred_at": "invalid", "action": "recovered", "entity_ids": ["sensor.good"]},
            {"occurred_at": "2026-11-20T11:00:00+00:00", "action": "recovered", "entity_ids": ["sensor.good"]},
        ],
    })
    assert set(result["observations"]) == {"sensor.good", "sensor.bad_time"}
    assert "unavailable_since" not in result["observations"]["sensor.bad_time"]
    assert set(result["investigations"]) == {"good"}
    assert len(result["events"]) == 1


def test_expected_is_an_explicit_user_status_not_a_suppression_or_classification():
    result = STORAGE.normalize_availability_data({
        "investigations": {
            "user-reviewed": {
                "entity_ids": ["sensor.legacy"],
                "status": "expected",
                "user_note": "The device is intentionally powered off seasonally.",
            }
        }
    })
    assert result["investigations"]["user-reviewed"]["status"] == "expected"
    assert "classifications" not in result
    assert "suppressed_entities" not in result


def test_storage_is_bounded_and_deduplicates_entity_ids():
    events = [
        {
            "occurred_at": "2026-11-20T11:00:00+00:00",
            "action": f"event_{index}",
            "entity_ids": ["sensor.one", "sensor.one"],
        }
        for index in range(STORAGE.MAX_EVENTS + 10)
    ]
    result = STORAGE.normalize_availability_data({
        "investigations": {
            "group": {
                "entity_ids": ["sensor.one", "sensor.one", "binary_sensor.two"],
                "status": "waiting",
            }
        },
        "events": events,
    })
    assert len(result["events"]) == STORAGE.MAX_EVENTS
    assert result["investigations"]["group"]["entity_ids"] == [
        "sensor.one", "binary_sensor.two"
    ]


def test_malformed_unhashable_investigation_status_is_discarded():
    result = STORAGE.normalize_availability_data({
        "investigations": {
            "list-status": {"entity_ids": ["sensor.one"], "status": ["resolved"]},
            "dict-status": {"entity_ids": ["sensor.two"], "status": {"resolved": True}},
            "valid": {"entity_ids": ["sensor.three"], "status": "waiting"},
        }
    })
    assert set(result["investigations"]) == {"valid"}


def test_presence_and_recovery_metadata_survive_store_normalization():
    result = STORAGE.normalize_availability_data({
        "observations": {
            "sensor.garage": {
                "state": "unavailable",
                "present": False,
                "missing_since": "2026-11-23T12:00:00+00:00",
                "unavailable_since": "2026-11-23T10:00:00+00:00",
                "last_unavailable_since": "2026-11-22T10:00:00+00:00",
                "last_recovered_at": "2026-11-22T12:00:00+00:00",
            }
        }
    })
    record = result["observations"]["sensor.garage"]
    assert record["present"] is False
    assert record["missing_since"] == "2026-11-23T12:00:00+00:00"
    assert record["unavailable_since"] == "2026-11-23T10:00:00+00:00"
    assert record["last_unavailable_since"] == "2026-11-22T10:00:00+00:00"
    assert record["last_recovered_at"] == "2026-11-22T12:00:00+00:00"


def test_store_retains_active_unavailable_records_before_inactive_history():
    observations = {
        f"sensor.old_{index}": {
            "state": "available",
            "last_seen": f"2026-11-{(index % 20) + 1:02d}T00:00:00+00:00",
        }
        for index in range(STORAGE.MAX_OBSERVATIONS)
    }
    observations["sensor.new_outage"] = {
        "state": "unavailable",
        "unavailable_since": "2026-11-23T10:00:00+00:00",
        "last_seen": "2026-11-23T10:00:00+00:00",
    }
    result = STORAGE.normalize_availability_data({"observations": observations})
    assert "sensor.new_outage" in result["observations"]
    assert len(result["observations"]) == STORAGE.MAX_OBSERVATIONS
