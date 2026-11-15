from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "investigation_history.py"
SPEC = spec_from_file_location("health_manager_investigation_history", MODULE_PATH)
HISTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(HISTORY)


def test_prompt_generation_records_minimal_history_and_increments_existing_item():
    item = {"plan_id": "integration_mqtt", "title": "MQTT needs attention", "severity": "high"}
    history = HISTORY.record_investigation([], item, "/config/health_manager/reports/focused.md", "2026-11-15T10:00:00+00:00")
    assert len(history) == 1
    assert history[0]["status"] == "prompt_generated"
    assert history[0]["generation_count"] == 1
    assert "entity_id" not in history[0]
    history = HISTORY.record_investigation(history, item, "/config/health_manager/reports/focused2.md", "2026-11-16T10:00:00+00:00")
    assert len(history) == 1
    assert history[0]["generation_count"] == 2
    assert history[0]["first_generated_at"] == "2026-11-15T10:00:00+00:00"


def test_status_updates_are_explicit_and_unknown_items_rejected():
    history = HISTORY.record_investigation([], {"plan_id": "mqtt"}, "/tmp/prompt.md", "2026-11-15T10:00:00+00:00")
    updated = HISTORY.set_investigation_status(history, "mqtt", "in_progress", "2026-11-15T11:00:00+00:00")
    assert updated[0]["status"] == "in_progress"
    try:
        HISTORY.set_investigation_status(updated, "missing", "resolved", "2026-11-15T12:00:00+00:00")
    except ValueError as err:
        assert "No investigation history" in str(err)
    else:
        raise AssertionError("Unknown investigation must be rejected")


def test_status_validation_and_history_are_bounded():
    try:
        HISTORY.set_investigation_status([], "x", "fixed", "now")
    except ValueError as err:
        assert "Unsupported" in str(err)
    else:
        raise AssertionError("Unknown statuses must be rejected")
    records = [
        {"plan_id": f"issue_{index}", "status": "prompt_generated", "last_updated": str(index)}
        for index in range(60)
    ]
    summary = HISTORY.summarize_investigations(records)
    assert summary["investigation_count"] == 50
    assert len(summary["investigations"]) == 50
    assert summary["investigation_status_counts"]["prompt_generated"] == 50


def test_dashboard_investigation_options_are_readable_and_map_to_exact_ids():
    options = HISTORY.build_investigation_options([
        {"plan_id": "mqtt", "title": "MQTT setup needs review", "status": "in_progress", "last_updated": "2026-11-15T12:00:00+00:00"},
        {"plan_id": "zha", "title": "ZHA unavailable entities", "status": "needs_follow_up", "last_updated": "2026-11-15T11:00:00+00:00"},
    ])
    assert len(options) == 2
    assert set(options.values()) == {"mqtt", "zha"}
    assert any(label.startswith("In Progress · MQTT setup needs review") for label in options)


def test_selected_investigation_returns_matching_history_and_latest_finding():
    data = {
        "investigations": [
            {"plan_id": "integration_mqtt", "title": "MQTT needs attention", "status": "in_progress"},
            {"plan_id": "integration_zha", "title": "ZHA review", "status": "prompt_generated"},
        ],
        "repair_plan": {
            "items": [
                {"plan_id": "integration_mqtt", "evidence": [{"type": "integration_trend"}], "suggested_actions": ["Review MQTT logs"]},
                {"plan_id": "integration_zha"},
            ]
        },
    }
    selected = HISTORY.build_selected_investigation(data, "integration_mqtt")
    assert selected["selected"]["status"] == "in_progress"
    assert selected["finding"]["evidence"][0]["type"] == "integration_trend"
    assert selected["finding"]["suggested_actions"] == ["Review MQTT logs"]


def test_selected_investigation_handles_missing_or_stale_selection():
    assert HISTORY.build_selected_investigation({}, None) == {"selected": None, "finding": None}
    assert HISTORY.build_selected_investigation(
        {"investigations": [], "repair_plan": {"items": []}}, "stale"
    ) == {"selected": None, "finding": None}



def test_investigation_helpers_tolerate_malformed_stored_shapes():
    assert HISTORY.summarize_investigations(None)["investigation_count"] == 0
    assert HISTORY.build_investigation_options(None) == {}
    try:
        HISTORY.set_investigation_status(None, "missing", "resolved", "now")
    except ValueError as err:
        assert "No investigation history" in str(err)
    else:
        raise AssertionError("Malformed history must not produce a false successful update")
    assert HISTORY.record_investigation(
        None,
        {"plan_id": "mqtt", "title": "MQTT review"},
        "/config/health_manager/reports/focused.md",
        "2026-11-15T10:00:00+00:00",
    )[0]["plan_id"] == "mqtt"
    assert HISTORY.build_selected_investigation(
        {"investigations": "invalid", "repair_plan": None}, "mqtt"
    ) == {"selected": None, "finding": None}


def test_selected_investigation_tolerates_malformed_repair_plan_items():
    data = {
        "investigations": [{"plan_id": "mqtt", "title": "MQTT review"}],
        "repair_plan": {"items": None},
    }
    assert HISTORY.build_selected_investigation(data, "mqtt") == {
        "selected": {"plan_id": "mqtt", "title": "MQTT review"},
        "finding": None,
    }


def test_investigation_history_tolerates_malformed_sort_timestamps_and_generation_counts():
    history = [
        {"plan_id": "mqtt", "last_updated": None, "generation_count": "not-a-number"},
        {"plan_id": "zha", "last_updated": "2026-11-15T10:00:00+00:00", "generation_count": 2},
        {"plan_id": "zwave", "last_updated": 123, "generation_count": None},
    ]

    updated = HISTORY.record_investigation(
        history,
        {"plan_id": "mqtt", "title": "MQTT review"},
        "/config/health_manager/reports/mqtt.md",
        "2026-11-15T12:00:00+00:00",
    )
    assert updated[0]["plan_id"] == "mqtt"
    assert updated[0]["generation_count"] == 1
    assert updated[1]["plan_id"] == "zha"
    assert updated[2]["plan_id"] == "zwave"

    status_updated = HISTORY.set_investigation_status(
        [{"plan_id": "mqtt", "last_updated": None}, {"plan_id": "zha", "last_updated": 123}],
        "mqtt",
        "resolved",
        "2026-11-15T13:00:00+00:00",
    )
    assert status_updated[0]["plan_id"] == "mqtt"
    assert status_updated[0]["status"] == "resolved"


def test_investigation_helpers_tolerate_unhashable_persisted_status_values():
    summary = HISTORY.summarize_investigations([
        {"plan_id": "mqtt", "status": ["corrupt"]},
        {"plan_id": "zha", "status": {"unexpected": "shape"}},
        {"plan_id": "zwave", "status": "resolved"},
    ])
    assert summary["investigation_status_counts"]["resolved"] == 1
    assert sum(summary["investigation_status_counts"].values()) == 1

    try:
        HISTORY.set_investigation_status([], "mqtt", ["resolved"], "now")
    except ValueError as err:
        assert "Unsupported investigation status" in str(err)
    else:
        raise AssertionError("Non-string statuses must be rejected")
