from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "entity_classifications.py"
)
SPEC = spec_from_file_location("health_manager_entity_classifications", MODULE_PATH)
CLASSIFICATIONS = module_from_spec(SPEC)
SPEC.loader.exec_module(CLASSIFICATIONS)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def test_normalize_initializes_empty_store():
    result = CLASSIFICATIONS.normalize_classifications(None)
    assert result["schema_version"] == 1
    assert result["entities"] == {}
    assert result["review_interval"] == "90"


def test_set_classification_records_reason_and_audit_timestamps():
    result = CLASSIFICATIONS.set_entity_classification(
        {},
        "sensor.example",
        "expected",
        "The source is intentionally disabled.",
        now=NOW,
        entity_domain="sensor",
        source_domain="example",
        source_unique_id="device-1",
    )
    record = result["entities"]["sensor.example"]
    assert record["classification"] == "expected"
    assert record["reason"] == "The source is intentionally disabled."
    assert record["created_at"] == NOW.isoformat()
    assert record["updated_at"] == NOW.isoformat()
    assert record["last_reviewed"] == NOW.isoformat()
    assert record["source_domain"] == "example"


def test_update_preserves_original_creation_time_and_unknown_metadata():
    first = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "setup_in_progress", "Still configuring.", now=NOW
    )
    first["entities"]["sensor.example"]["custom_metadata"] = "keep"
    later = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    result = CLASSIFICATIONS.set_entity_classification(
        first, "sensor.example", "actionable", "Needs investigation.", now=later
    )
    record = result["entities"]["sensor.example"]
    assert record["created_at"] == NOW.isoformat()
    assert record["updated_at"] == later.isoformat()
    assert record["custom_metadata"] == "keep"


def test_invalid_records_are_ignored_but_valid_records_and_future_keys_survive():
    source = {
        "future_setting": {"enabled": True},
        "entities": {
            "sensor.good": {
                "classification": "seasonal",
                "reason": "Winter shutdown.",
                "custom": 7,
            },
            "sensor.bad": {"classification": "unknown", "reason": "Bad value."},
            "sensor.no_reason": {"classification": "expected", "reason": "  "},
            "broken": "not a record",
        },
    }
    result = CLASSIFICATIONS.normalize_classifications(source)
    assert list(result["entities"]) == ["sensor.good"]
    assert result["entities"]["sensor.good"]["custom"] == 7
    assert result["future_setting"] == {"enabled": True}


def test_missing_entities_are_retained_and_restored_when_seen_again():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Seasonal device.", now=NOW
    )
    absent = CLASSIFICATIONS.mark_entity_observations(stored, set(), now=NOW)
    record = absent["entities"]["sensor.example"]
    assert record["entity_missing"] is True
    assert record["missing_since"] == NOW.isoformat()

    later = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    restored = CLASSIFICATIONS.mark_entity_observations(
        absent, {"sensor.example"}, now=later
    )
    record = restored["entities"]["sensor.example"]
    assert record["entity_missing"] is False
    assert record["last_seen"] == later.isoformat()
    assert record["returned_at"] == later.isoformat()
    assert record["review_due"] is True
    assert record["review_due_reason"] == "entity_returned"
    assert record["reason"] == "Seasonal device."


def test_remove_requires_an_explicit_entity_id_and_removes_only_that_record():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.one", "expected", "Reason one.", now=NOW
    )
    stored = CLASSIFICATIONS.set_entity_classification(
        stored, "sensor.two", "actionable", "Reason two.", now=NOW
    )
    result = CLASSIFICATIONS.remove_entity_classification(stored, "sensor.one")
    assert set(result["entities"]) == {"sensor.two"}


def test_invalid_classification_and_blank_reason_are_rejected():
    try:
        CLASSIFICATIONS.set_entity_classification(
            {}, "sensor.example", "silenced", "Reason.", now=NOW
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid classification should be rejected")

    try:
        CLASSIFICATIONS.set_entity_classification(
            {}, "sensor.example", "expected", "  ", now=NOW
        )
    except ValueError:
        pass
    else:
        raise AssertionError("blank reason should be rejected")


def test_review_interval_is_validated_and_persisted():
    result = CLASSIFICATIONS.set_review_interval({}, "30")
    assert result["review_interval"] == "30"
    try:
        CLASSIFICATIONS.set_review_interval(result, "14")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported review interval should be rejected")


def test_review_due_respects_interval_and_manual_setting():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Intentionally inactive.", now=NOW
    )
    after_30_days = datetime(2026, 12, 19, 12, 0, tzinfo=timezone.utc)
    assert CLASSIFICATIONS.get_review_due_entities(stored, now=after_30_days) == ["sensor.example"]
    manual = CLASSIFICATIONS.set_review_interval(stored, "manual")
    assert CLASSIFICATIONS.get_review_due_entities(manual, now=after_30_days) == []


def test_entity_return_triggers_review_without_changing_classification():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "setup_in_progress", "Still being configured.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(stored, set(), now=NOW)
    returned = CLASSIFICATIONS.mark_entity_observations(
        missing, {"sensor.example"},
        now=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
    )
    record = returned["entities"]["sensor.example"]
    assert record["classification"] == "setup_in_progress"
    assert record["reason"] == "Still being configured."
    assert record["review_due"] is True
    assert CLASSIFICATIONS.get_review_due_entities(returned) == ["sensor.example"]


def test_source_and_availability_changes_trigger_review_without_reclassification():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Intentionally inactive.",
        now=NOW, source_domain="demo", source_unique_id="old-id"
    )
    baseline = CLASSIFICATIONS.mark_entity_observations(
        stored, {"sensor.example"},
        entity_sources={"sensor.example": {"source_domain": "demo", "source_unique_id": "old-id"}},
        entity_states={"sensor.example": "off"}, now=NOW
    )
    changed = CLASSIFICATIONS.mark_entity_observations(
        baseline, {"sensor.example"},
        entity_sources={"sensor.example": {"source_domain": "new_demo", "source_unique_id": "new-id"}},
        entity_states={"sensor.example": "unavailable"},
        now=datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc),
    )
    record = changed["entities"]["sensor.example"]
    assert record["classification"] == "expected"
    assert record["reason"] == "Intentionally inactive."
    assert record["review_due"] is True
    assert record["review_due_reason"] == "availability_changed"
    assert record["previous_source_domain"] == "demo"
    assert record["source_domain"] == "new_demo"
    assert record["previous_source_unique_id"] == "old-id"
    assert record["source_unique_id"] == "new-id"



def test_manual_interval_still_allows_event_triggered_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Seasonal source.", now=NOW
    )
    manual = CLASSIFICATIONS.set_review_interval(stored, "manual")
    due = CLASSIFICATIONS.mark_entity_observations(manual, set(), now=NOW)
    assert CLASSIFICATIONS.get_review_due_entities(due, now=NOW) == ["sensor.example"]
