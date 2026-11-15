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


def test_scheduled_report_uses_imported_timedelta_and_report_generation_is_serialized():
    tree = _parse(INTEGRATION / "coordinator.py")
    imported_datetime_names = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "datetime"
        for alias in node.names
    }
    assert "timedelta" in imported_datetime_names

    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    report_method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_generate_report"
    )
    assert any(
        isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Attribute)
            and item.context_expr.attr == "_report_lock"
            for item in node.items
        )
        for node in ast.walk(report_method)
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_async_generate_report_locked"
        for node in ast.walk(report_method)
    )



def test_report_state_is_committed_only_after_report_write_and_store_save():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_generate_report_locked"
    )
    calls = [
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "deepcopy" for node in ast.walk(method))
    assert "write_report" in calls
    assert "async_save" in calls
    save_index = next(
        index for index, statement in enumerate(method.body)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_save"
            for node in ast.walk(statement)
        )
    )
    state_commit_index = next(
        index for index, statement in enumerate(method.body)
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "schedule"
            for target in statement.targets
        )
    )
    assert save_index < state_commit_index


def test_focused_prompt_rejects_unknown_plan_before_writing():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_generate_focused_repair_prompt"
    )
    calls = [
        node.func.id if isinstance(node.func, ast.Name)
        else node.func.attr if isinstance(node.func, ast.Attribute)
        else None
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    ]
    assert calls.index("write_focused_repair_prompt") > calls.index("next")
    assert "ValueError" in [
        node.id for node in ast.walk(method) if isinstance(node, ast.Name)
    ]


def test_report_artifacts_are_staged_before_publication_and_retention():
    source = (INTEGRATION / "report.py").read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert "os.replace(staged_path, final_path)" in source
    assert source.index("os.replace(staged_path, final_path)") < source.index("cutoff = now - timedelta")
