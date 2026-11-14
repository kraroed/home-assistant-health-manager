import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "home_assistant_health_manager"


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def test_home_assistant_snapshot_collection_stays_on_event_loop():
    tree = _parse(INTEGRATION / "coordinator.py")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "async_add_executor_job":
            assert not any(
                isinstance(argument, ast.Name) and argument.id == "collect_snapshot"
                for argument in node.args
            )


def test_both_report_services_refresh_after_report_generation():
    tree = _parse(INTEGRATION / "services.py")
    service_functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    for name in ("run_diagnostics", "generate_report"):
        function = service_functions[name]
        calls = [
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        assert "async_generate_report" in calls
        assert "async_request_refresh" in calls
        statements = function.body
        report_index = next(
            index for index, statement in enumerate(statements)
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "async_generate_report"
                for node in ast.walk(statement)
            )
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_request_refresh"
            for statement in statements[report_index + 1:]
            for node in ast.walk(statement)
        )


def test_manifest_declares_calculated_iot_class():
    manifest = json.loads(
        (INTEGRATION / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["iot_class"] == "calculated"
    assert manifest["integration_type"] == "service"


def test_unknown_entity_sensor_and_domain_breakdowns_are_exposed():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '("unknown_entity_count", "Unknown Entities", "entities"' in source
    assert '"unknown_counts_by_domain": data.get("unknown_counts_by_domain", {})' in source
    assert '"unavailable_counts_by_domain": data.get("unavailable_counts_by_domain", {})' in source


def test_failed_integration_domains_and_entry_states_are_exposed():
    collector = (INTEGRATION / "collector.py").read_text(encoding="utf-8")
    sensor = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    report = (INTEGRATION / "report.py").read_text(encoding="utf-8")
    assert '"failed_config_entry_domains"' in collector
    assert '"config_entry_states"' in collector
    assert '"failed_config_entry_domains": data.get("failed_config_entry_domains", {})' in sensor
    assert '"config_entry_states": data.get("config_entry_states", {})' in sensor
    assert "Failed integration domains:" in report
    assert "Integration setup states:" in report
