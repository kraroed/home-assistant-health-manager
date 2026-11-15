from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "log_analyzer.py"
SPEC = spec_from_file_location("health_manager_log_analyzer", MODULE_PATH)
ANALYZER = module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def test_attributes_explicit_core_and_custom_component_logger_namespaces():
    result = ANALYZER.analyze_log(
        "2026-11-14 10:00:00.000 ERROR (MainThread) [homeassistant.components.mqtt] failed\n"
        "2026-11-14 10:00:01.000 WARNING (MainThread) [custom_components.my_sensor.coordinator] retry\n"
    )
    evidence = result["integration_log_evidence"]
    assert evidence["attributed_entry_count"] == 2
    assert evidence["unattributed_entry_count"] == 0
    assert evidence["domains"] == [
        {"domain": "mqtt", "level_counts": {"error": 1}},
        {"domain": "my_sensor", "level_counts": {"warning": 1}},
    ]


def test_generic_core_logger_and_message_mentions_remain_unattributed():
    result = ANALYZER.analyze_log(
        "2026-11-14 10:00:00.000 ERROR (MainThread) [homeassistant.config_entries] mqtt setup failed\n"
        "2026-11-14 10:00:01.000 ERROR (MainThread) Something mentions custom_components.fake\n"
        "2026-11-14 10:00:02.000 WARNING (MainThread) [homeassistant.components] broad logger\n"
    )
    evidence = result["integration_log_evidence"]
    assert evidence["attributed_entry_count"] == 0
    assert evidence["unattributed_entry_count"] == 3
    assert evidence["domains"] == []


def test_unrelated_logger_namespace_is_not_guessed_as_integration():
    result = ANALYZER.analyze_log(
        "2026-11-14 10:00:00.000 ERROR (MainThread) [urllib3.connectionpool] retrying mqtt request\n"
    )
    evidence = result["integration_log_evidence"]
    assert evidence["domains"] == []
    assert evidence["unattributed_entry_count"] == 1


def test_log_evidence_contains_counts_not_raw_log_text():
    result = ANALYZER.analyze_log(
        "2026-11-14 10:00:00.000 ERROR (MainThread) [custom_components.private_domain] password=hunter2\n"
    )
    evidence = result["integration_log_evidence"]
    assert "hunter2" not in str(evidence)
    assert "password" not in str(evidence)
    assert evidence["domains"][0]["domain"] == "private_domain"


def test_missing_log_reports_unavailable_evidence():
    result = ANALYZER.analyze_log(None)
    assert result["available"] is False
    assert result["integration_log_evidence"]["domains"] == []
    assert result["integration_log_evidence"]["attributed_entry_count"] == 0
