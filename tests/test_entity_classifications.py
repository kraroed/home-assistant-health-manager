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
    stored = CLASSIFICATIONS.set_review_interval(stored, "30")
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
    assert set(record["review_due_reasons"]) == {"source_changed", "availability_changed"}
    assert record["previous_source_domain"] == "demo"
    assert record["source_domain"] == "new_demo"
    assert record["previous_source_unique_id"] == "old-id"
    assert record["source_unique_id"] == "new-id"



def test_manual_interval_still_allows_event_triggered_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Seasonal source.", now=NOW
    )
    manual = CLASSIFICATIONS.set_review_interval(stored, "manual")
    missing = CLASSIFICATIONS.mark_entity_observations(manual, set(), now=NOW)
    after_grace = datetime(2026, 11, 18, 12, 16, tzinfo=timezone.utc)
    due = CLASSIFICATIONS.mark_entity_observations(
        missing, set(), now=after_grace
    )
    assert CLASSIFICATIONS.get_review_due_entities(due, now=after_grace) == ["sensor.example"]


def test_bulk_review_confirmation_clears_due_without_changing_classification_or_reason():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Intentionally inactive.", now=NOW
    )
    due = CLASSIFICATIONS.mark_entity_observations(stored, set(), now=NOW)
    later = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    reviewed = CLASSIFICATIONS.mark_classifications_reviewed(
        due, ["sensor.example", "sensor.not_classified"], now=later
    )
    record = reviewed["entities"]["sensor.example"]
    assert record["classification"] == "expected"
    assert record["reason"] == "Intentionally inactive."
    assert record["review_due"] is False
    assert record["last_reviewed"] == later.isoformat()
    assert CLASSIFICATIONS.get_review_due_entities(reviewed, now=later) == []


def test_explicit_classification_update_clears_outstanding_review_triggers():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Seasonal device.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(stored, set(), now=NOW)
    flagged = CLASSIFICATIONS.mark_entity_observations(
        missing, set(),
        now=datetime(2026, 11, 18, 12, 16, tzinfo=timezone.utc),
    )
    assert flagged["entities"]["sensor.example"]["review_due"] is True
    updated = CLASSIFICATIONS.set_entity_classification(
        flagged, "sensor.example", "actionable", "Now needs attention.", now=NOW
    )
    record = updated["entities"]["sensor.example"]
    assert record["review_due"] is False
    assert "review_due_reason" not in record
    assert "review_due_reasons" not in record
    assert "review_due_at" not in record


def test_malformed_unhashable_values_in_persisted_store_are_ignored_safely():
    source = {
        "review_interval": ["not", "an", "interval"],
        "entities": {
            "sensor.bad_class": {
                "classification": ["expected"],
                "reason": "Malformed classification value.",
            },
            "sensor.good": {
                "classification": "expected",
                "reason": "Preserve valid record.",
            },
        },
    }
    result = CLASSIFICATIONS.normalize_classifications(source)
    assert result["review_interval"] == "90"
    assert set(result["entities"]) == {"sensor.good"}

    try:
        CLASSIFICATIONS.set_entity_classification(
            {}, "sensor.example", ["expected"], "Reason.", now=NOW
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unhashable classification should be rejected")

    try:
        CLASSIFICATIONS.set_review_interval({}, ["30"])
    except ValueError:
        pass
    else:
        raise AssertionError("unhashable review interval should be rejected")



def test_short_missing_and_return_during_restart_grace_does_not_trigger_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Restored after restart.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=15
    )
    assert missing["entities"]["sensor.example"]["entity_missing"] is True
    assert missing["entities"]["sensor.example"]["review_due"] is False
    returned_at = datetime(2026, 11, 18, 12, 5, tzinfo=timezone.utc)
    returned = CLASSIFICATIONS.mark_entity_observations(
        missing, {"sensor.example"}, now=returned_at, missing_grace_minutes=15
    )
    record = returned["entities"]["sensor.example"]
    assert record["entity_missing"] is False
    assert record["review_due"] is False
    assert record["last_presence_recovery"] == "within_grace_period"
    assert record["last_missing_duration_seconds"] == 300.0
    assert CLASSIFICATIONS.get_review_due_entities(returned, now=returned_at) == []


def test_entity_still_missing_after_grace_period_triggers_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Should return after restart.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=10
    )
    still_missing_at = datetime(2026, 11, 18, 12, 11, tzinfo=timezone.utc)
    due = CLASSIFICATIONS.mark_entity_observations(
        missing, set(), now=still_missing_at, missing_grace_minutes=10
    )
    record = due["entities"]["sensor.example"]
    assert record["entity_missing"] is True
    assert record["review_due"] is True
    assert record["review_due_reason"] == "entity_missing"


def test_return_after_grace_period_triggers_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Unexpectedly absent.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=10
    )
    returned_at = datetime(2026, 11, 18, 12, 11, tzinfo=timezone.utc)
    returned = CLASSIFICATIONS.mark_entity_observations(
        missing, {"sensor.example"}, now=returned_at, missing_grace_minutes=10
    )
    record = returned["entities"]["sensor.example"]
    assert record["entity_missing"] is False
    assert record["review_due"] is True
    assert record["review_due_reason"] == "entity_returned"


def test_legacy_brief_restart_missing_return_flags_are_reconciled_without_reclassification():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Expected during restart.", now=NOW
    )
    record = stored["entities"]["sensor.example"]
    record.update({
        "review_due": True,
        "review_due_reason": "entity_returned",
        "review_due_reasons": ["entity_missing", "entity_returned"],
        "review_due_at": datetime(2026, 11, 18, 12, 5, tzinfo=timezone.utc).isoformat(),
        "entity_missing": False,
        "missing_since": NOW.isoformat(),
        "returned_at": datetime(2026, 11, 18, 12, 5, tzinfo=timezone.utc).isoformat(),
    })
    current = datetime(2026, 11, 18, 12, 6, tzinfo=timezone.utc)
    result = CLASSIFICATIONS.mark_entity_observations(
        stored, {"sensor.example"}, now=current, missing_grace_minutes=15
    )
    updated = result["entities"]["sensor.example"]
    assert updated["review_due"] is False
    assert updated["classification"] == "expected"
    assert updated["reason"] == "Expected during restart."
    assert updated["last_presence_recovery"] == "within_grace_period"
    assert updated["last_missing_duration_seconds"] == 300.0


def test_legacy_restart_reconciliation_preserves_other_review_triggers():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Keep source changes reviewable.", now=NOW
    )
    record = stored["entities"]["sensor.example"]
    record.update({
        "review_due": True,
        "review_due_reason": "source_changed",
        "review_due_reasons": ["entity_missing", "entity_returned", "source_changed"],
        "entity_missing": False,
        "missing_since": NOW.isoformat(),
        "returned_at": datetime(2026, 11, 18, 12, 5, tzinfo=timezone.utc).isoformat(),
    })
    result = CLASSIFICATIONS.mark_entity_observations(
        stored, {"sensor.example"},
        now=datetime(2026, 11, 18, 12, 6, tzinfo=timezone.utc),
        missing_grace_minutes=15,
    )
    updated = result["entities"]["sensor.example"]
    assert updated["review_due"] is True
    assert "source_changed" in updated["review_due_reasons"]



def test_exact_grace_boundary_and_later_returns_require_review():
    for seconds in (900, 907, 1800):
        stored = CLASSIFICATIONS.set_entity_classification(
            {}, "sensor.example", "expected", "Restart test.", now=NOW
        )
        missing = CLASSIFICATIONS.mark_entity_observations(
            stored, set(), now=NOW, missing_grace_minutes=15
        )
        returned_at = datetime.fromtimestamp(NOW.timestamp() + seconds, timezone.utc)
        returned = CLASSIFICATIONS.mark_entity_observations(
            missing, {"sensor.example"}, now=returned_at, missing_grace_minutes=15
        )
        record = returned["entities"]["sensor.example"]
        assert record["review_due"] is True
        assert record["review_due_reason"] == "entity_returned"
        assert record["last_presence_recovery"] == "after_grace_period"
        assert record["last_missing_duration_seconds"] == float(seconds)


def test_just_under_grace_boundary_does_not_require_review():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Restart test.", now=NOW
    )
    missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=15
    )
    returned_at = datetime.fromtimestamp(NOW.timestamp() + 899, timezone.utc)
    returned = CLASSIFICATIONS.mark_entity_observations(
        missing, {"sensor.example"}, now=returned_at, missing_grace_minutes=15
    )
    record = returned["entities"]["sensor.example"]
    assert record["review_due"] is False
    assert record["last_presence_recovery"] == "within_grace_period"
    assert record["last_missing_duration_seconds"] == 899.0


def test_new_missing_episode_clears_stale_recovery_metadata():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Restart test.", now=NOW
    )
    first_missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=15
    )
    first_return = datetime.fromtimestamp(NOW.timestamp() + 300, timezone.utc)
    recovered = CLASSIFICATIONS.mark_entity_observations(
        first_missing, {"sensor.example"}, now=first_return, missing_grace_minutes=15
    )
    second_missing_at = datetime.fromtimestamp(NOW.timestamp() + 600, timezone.utc)
    second_missing = CLASSIFICATIONS.mark_entity_observations(
        recovered, set(), now=second_missing_at, missing_grace_minutes=15
    )
    record = second_missing["entities"]["sensor.example"]
    assert record["entity_missing"] is True
    assert record["missing_since"] == second_missing_at.isoformat()
    assert "returned_at" not in record
    assert "last_missing_duration_seconds" not in record
    assert "last_presence_recovery" not in record
    assert "last_presence_recovery_at" not in record


def test_long_outage_review_is_not_cleared_by_a_later_short_restart():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Keep genuine outage review.", now=NOW
    )
    first_missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=15
    )
    long_return_at = datetime.fromtimestamp(NOW.timestamp() + 901, timezone.utc)
    long_return = CLASSIFICATIONS.mark_entity_observations(
        first_missing, {"sensor.example"}, now=long_return_at, missing_grace_minutes=15
    )
    assert long_return["entities"]["sensor.example"]["review_due"] is True

    second_missing_at = datetime.fromtimestamp(NOW.timestamp() + 1200, timezone.utc)
    second_missing = CLASSIFICATIONS.mark_entity_observations(
        long_return, set(), now=second_missing_at, missing_grace_minutes=15
    )
    short_return_at = datetime.fromtimestamp(NOW.timestamp() + 1500, timezone.utc)
    second_return = CLASSIFICATIONS.mark_entity_observations(
        second_missing, {"sensor.example"}, now=short_return_at, missing_grace_minutes=15
    )
    record = second_return["entities"]["sensor.example"]
    assert record["review_due"] is True
    assert "entity_returned" in record["review_due_reasons"]
    assert record["last_presence_recovery"] == "within_grace_period"


def test_repeated_short_restart_cycles_do_not_accumulate_review_flags():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Normal restart gaps.", now=NOW
    )
    for offset in (0, 600, 1200, 1800):
        missing_at = datetime.fromtimestamp(NOW.timestamp() + offset, timezone.utc)
        returned_at = datetime.fromtimestamp(NOW.timestamp() + offset + 300, timezone.utc)
        missing = CLASSIFICATIONS.mark_entity_observations(
            stored, set(), now=missing_at, missing_grace_minutes=15
        )
        stored = CLASSIFICATIONS.mark_entity_observations(
            missing, {"sensor.example"}, now=returned_at, missing_grace_minutes=15
        )
    record = stored["entities"]["sensor.example"]
    assert record["review_due"] is False
    assert record["last_presence_recovery"] == "within_grace_period"
    assert record["last_missing_duration_seconds"] == 300.0


def test_prolonged_missing_flag_survives_a_later_short_restart_cycle():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.example", "expected", "Keep prolonged outage review.", now=NOW
    )
    first_missing = CLASSIFICATIONS.mark_entity_observations(
        stored, set(), now=NOW, missing_grace_minutes=15
    )
    overdue_at = datetime.fromtimestamp(NOW.timestamp() + 901, timezone.utc)
    overdue = CLASSIFICATIONS.mark_entity_observations(
        first_missing, set(), now=overdue_at, missing_grace_minutes=15
    )
    assert overdue["entities"]["sensor.example"]["review_due"] is True
    long_return_at = datetime.fromtimestamp(NOW.timestamp() + 1000, timezone.utc)
    long_return = CLASSIFICATIONS.mark_entity_observations(
        overdue, {"sensor.example"}, now=long_return_at, missing_grace_minutes=15
    )

    second_missing_at = datetime.fromtimestamp(NOW.timestamp() + 1200, timezone.utc)
    second_missing = CLASSIFICATIONS.mark_entity_observations(
        long_return, set(), now=second_missing_at, missing_grace_minutes=15
    )
    short_return_at = datetime.fromtimestamp(NOW.timestamp() + 1500, timezone.utc)
    second_return = CLASSIFICATIONS.mark_entity_observations(
        second_missing, {"sensor.example"}, now=short_return_at, missing_grace_minutes=15
    )
    record = second_return["entities"]["sensor.example"]
    assert record["review_due"] is True
    assert {"entity_missing", "entity_returned"}.issubset(
        set(record["review_due_reasons"])
    )
