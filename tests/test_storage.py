from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from datetime import datetime, timezone

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "storage.py"
SPEC = spec_from_file_location("health_manager_storage", MODULE_PATH)
STORAGE = module_from_spec(SPEC)
SPEC.loader.exec_module(STORAGE)


def test_schedule_normalization_initializes_missing_fields_deterministically():
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    result = STORAGE.normalize_schedule_data({}, now)
    assert result["next_weekly"] == "2026-11-22T00:00:00+00:00"
    assert result["next_monthly"] == "2026-12-15T00:00:00+00:00"
    assert result["issue_history"] == {}
    assert result["investigation_history"] == []
    assert result["report_count"] == 0


def test_schedule_normalization_recovers_from_invalid_top_level_data():
    result = STORAGE.normalize_schedule_data(["unexpected", "stored", "shape"])
    assert isinstance(result, dict)
    assert result["issue_history"] == {}
    assert result["change_history"] == []
    assert result["trend_history"] == []


def test_schedule_normalization_repairs_malformed_fields_and_preserves_valid_history():
    valid_issue = {"status": "active", "occurrences": 2}
    valid_investigation = {"plan_id": "mqtt", "status": "in_progress"}
    source = {
        "issue_history": {"mqtt": valid_issue, "broken": "not-a-record"},
        "change_history": None,
        "trend_history": [{"sample": 1}, "corrupt-record"],
        "integration_trend_history": {},
        "investigation_history": [valid_investigation, None],
        "last_repair_plan": None,
        "last_compatibility": [],
        "report_count": -3,
        "custom_future_key": "preserved",
    }
    result = STORAGE.normalize_schedule_data(source)
    assert result["issue_history"] == {"mqtt": valid_issue}
    assert result["change_history"] == []
    assert result["trend_history"] == [{"sample": 1}]
    assert result["integration_trend_history"] == []
    assert result["investigation_history"] == [valid_investigation]
    assert result["last_repair_plan"] == {}
    assert result["last_compatibility"] == {}
    assert result["report_count"] == 0
    assert result["custom_future_key"] == "preserved"


def test_schedule_normalization_rejects_boolean_report_count():
    result = STORAGE.normalize_schedule_data({"report_count": True})
    assert result["report_count"] == 0
