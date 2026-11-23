from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "availability_investigations.py"
)
SPEC = spec_from_file_location("health_manager_availability_investigations", MODULE_PATH)
INVESTIGATIONS = module_from_spec(SPEC)
SPEC.loader.exec_module(INVESTIGATIONS)

NOW = "2026-11-23T12:00:00+00:00"


def _group():
    return {
        "group_id": "device:abc123",
        "group_type": "device",
        "title": "2 entities on one device",
        "entity_ids": ["sensor.one", "binary_sensor.two"],
        "confidence": "strong",
        "evidence": ["Multiple unavailable entities share the same registered device."],
        "cause_confirmed": False,
        "source_domains": ["mqtt"],
    }


def test_start_requires_explicit_group_and_creates_investigating_record():
    records, investigation_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    record = records[investigation_id]
    assert record["status"] == "investigating"
    assert record["entity_ids"] == ["binary_sensor.two", "sensor.one"]
    assert record["cause_confirmed"] is False
    assert record["source_domains"] == ["mqtt"]
    assert record["created_at"] == NOW
    assert "classifications" not in record


def test_restarting_open_group_refreshes_context_without_resetting_user_status():
    records, investigation_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    records = INVESTIGATIONS.set_investigation_status(
        records, investigation_id, "investigating", NOW,
    )
    changed = _group()
    changed["entity_ids"].append("sensor.three")
    updated, same_id = INVESTIGATIONS.start_investigation(records, changed, "2026-11-23T13:00:00+00:00")
    assert same_id == investigation_id
    assert updated[investigation_id]["status"] == "investigating"
    assert "sensor.three" in updated[investigation_id]["entity_ids"]


def test_starting_previously_closed_group_creates_new_history_record():
    records, first_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    records = INVESTIGATIONS.set_investigation_status(records, first_id, "resolved", NOW)
    records, second_id = INVESTIGATIONS.start_investigation(
        records, _group(), "2026-11-23T13:00:00+00:00",
    )
    assert second_id != first_id
    assert records[first_id]["status"] == "resolved"
    assert records[second_id]["status"] == "investigating"


def test_waiting_status_sets_configurable_reminder_and_resolved_records_timestamp():
    records, investigation_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    waiting = INVESTIGATIONS.set_investigation_status(
        records, investigation_id, "waiting", NOW, reminder_days=3,
    )
    assert waiting[investigation_id]["next_reminder_at"] == "2026-11-26T12:00:00+00:00"
    resolved = INVESTIGATIONS.set_investigation_status(
        waiting, investigation_id, "resolved", "2026-11-27T12:00:00+00:00",
    )
    assert resolved[investigation_id]["resolved_at"] == "2026-11-27T12:00:00+00:00"
    assert "next_reminder_at" not in resolved[investigation_id]


def test_expected_status_is_a_user_note_not_automatic_entity_suppression():
    records, investigation_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    expected = INVESTIGATIONS.set_investigation_status(
        records, investigation_id, "expected", NOW,
        user_note="Seasonal equipment is intentionally offline.",
    )
    assert expected[investigation_id]["status"] == "expected"
    assert expected[investigation_id]["user_note"].startswith("Seasonal")
    assert "suppressed_entities" not in expected


def test_invalid_status_and_unknown_investigation_are_rejected():
    try:
        INVESTIGATIONS.set_investigation_status({}, "missing", "resolved", NOW)
    except ValueError as err:
        assert "No unavailable investigation" in str(err)
    else:
        raise AssertionError("Unknown investigation must be rejected")
    records, investigation_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    try:
        INVESTIGATIONS.set_investigation_status(records, investigation_id, "dismissed", NOW)
    except ValueError as err:
        assert "Unsupported" in str(err)
    else:
        raise AssertionError("Unsupported status must be rejected")


def test_summary_counts_statuses_and_bounds_display_records():
    records = {}
    for index in range(110):
        group = _group()
        group["group_id"] = f"device:{index}"
        updated, _ = INVESTIGATIONS.start_investigation(records, group, NOW)
        records = updated
    summary = INVESTIGATIONS.summarize_investigations(records)
    assert summary["unavailable_investigation_count"] == 110
    assert len(summary["unavailable_investigations"]) == 100
    assert summary["unavailable_investigation_status_counts"]["investigating"] == 110


def test_current_investigation_finds_latest_reopened_record_for_group():
    records, first_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    records = INVESTIGATIONS.set_investigation_status(records, first_id, "resolved", NOW)
    records, second_id = INVESTIGATIONS.start_investigation(
        records, _group(), "2026-11-23T13:00:00+00:00",
    )
    current = INVESTIGATIONS.find_current_investigation(records, _group()["group_id"])
    assert second_id != first_id
    assert current["investigation_id"] == second_id
    assert current["status"] == "needs_review"


def test_current_investigation_returns_latest_closed_record_when_group_is_resolved():
    records, first_id = INVESTIGATIONS.start_investigation({}, _group(), NOW)
    records = INVESTIGATIONS.set_investigation_status(records, first_id, "resolved", NOW)
    current = INVESTIGATIONS.find_current_investigation(records, _group()["group_id"])
    assert current["investigation_id"] == first_id
    assert current["status"] == "resolved"


def test_investigation_records_outage_cycle_for_later_reassessment():
    group = _group()
    group["earliest_unavailable_since"] = "2026-11-23T10:00:00+00:00"
    records, investigation_id = INVESTIGATIONS.start_investigation({}, group, NOW)
    assert records[investigation_id]["outage_started_at"] == "2026-11-23T10:00:00+00:00"
