from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "history.py"
SPEC = spec_from_file_location("health_manager_history", MODULE_PATH)
HISTORY = module_from_spec(SPEC)
SPEC.loader.exec_module(HISTORY)


def test_issue_first_detection_and_repeated_observation():
    first = HISTORY.update_issue_history(
        {}, [{"id": "unavailable_entities", "title": "Unavailable entities", "severity": "medium"}],
        "2026-11-01T00:00:00+00:00",
    )
    second = HISTORY.update_issue_history(
        first, [{"id": "unavailable_entities", "title": "Unavailable entities", "severity": "medium"}],
        "2026-11-08T00:00:00+00:00",
    )
    item = second["unavailable_entities"]
    assert item["first_seen"] == "2026-11-01T00:00:00+00:00"
    assert item["last_seen"] == "2026-11-08T00:00:00+00:00"
    assert item["occurrences"] == 1
    assert item["status"] == "active"


def test_issue_resolution_and_recurrence():
    active = HISTORY.update_issue_history(
        {}, [{"id": "failed_config_entries", "title": "Failed integration", "severity": "high"}],
        "2026-11-01T00:00:00+00:00",
    )
    resolved = HISTORY.update_issue_history(active, [], "2026-11-02T00:00:00+00:00")
    assert resolved["failed_config_entries"]["status"] == "resolved"
    assert resolved["failed_config_entries"]["resolved_at"] == "2026-11-02T00:00:00+00:00"
    returned = HISTORY.update_issue_history(
        resolved, [{"id": "failed_config_entries", "title": "Failed integration", "severity": "high"}],
        "2026-11-03T00:00:00+00:00",
    )
    assert returned["failed_config_entries"]["occurrences"] == 2
    assert returned["failed_config_entries"]["first_seen"] == "2026-11-01T00:00:00+00:00"
    assert returned["failed_config_entries"]["last_resolved_at"] == "2026-11-02T00:00:00+00:00"


def test_no_rule_triggered_is_not_saved_as_an_issue():
    result = HISTORY.update_issue_history(
        {}, [{"id": "no_rule_triggered", "title": "No issues", "severity": "info"}],
        "2026-11-01T00:00:00+00:00",
    )
    assert result == {}


def test_history_is_bounded_and_summarized():
    history = {
        f"issue_{index}": {"status": "active" if index % 2 else "resolved", "last_seen": f"2026-11-{index + 1:02d}"}
        for index in range(125)
    }
    updated = HISTORY.update_issue_history(history, [], "2026-11-30T00:00:00+00:00")
    assert len(updated) == 100
    summary = HISTORY.summarize_issue_history(updated)
    assert summary["tracked_issue_count"] == 100
    assert summary["active_tracked_issue_count"] == 0
    assert summary["resolved_tracked_issue_count"] == 100



def test_summary_identifies_active_and_resolved_recurring_issues():
    active = HISTORY.update_issue_history(
        {}, [{"id": "failed_config_entries", "title": "Failed integrations", "severity": "high"}],
        "2026-11-01T00:00:00+00:00",
    )
    resolved = HISTORY.update_issue_history(active, [], "2026-11-02T00:00:00+00:00")
    returned = HISTORY.update_issue_history(
        resolved, [{"id": "failed_config_entries", "title": "Failed integrations", "severity": "high"}],
        "2026-11-03T00:00:00+00:00",
    )
    summary = HISTORY.summarize_issue_history(returned)
    assert summary["recurring_issue_count"] == 1
    assert summary["active_recurring_issue_count"] == 1
    assert summary["recurring_issues"][0]["issue_id"] == "failed_config_entries"
    assert summary["recurring_issues"][0]["occurrences"] == 2
    resolved_again = HISTORY.update_issue_history(returned, [], "2026-11-04T00:00:00+00:00")
    resolved_summary = HISTORY.summarize_issue_history(resolved_again)
    assert resolved_summary["recurring_issue_count"] == 1
    assert resolved_summary["active_recurring_issue_count"] == 0
