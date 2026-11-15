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
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "write_report" for node in ast.walk(method))
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



def test_all_schedule_writers_use_shared_state_lock():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method_names = {
        "_async_update_data",
        "async_generate_report",
        "async_generate_focused_repair_prompt",
        "async_set_investigation_status",
    }
    for method in (node for node in coordinator.body
                   if isinstance(node, ast.AsyncFunctionDef) and node.name in method_names):
        lock_blocks = [
            node for node in ast.walk(method)
            if isinstance(node, ast.AsyncWith)
            and any(
                isinstance(item.context_expr, ast.Attribute)
                and item.context_expr.attr == "_state_lock"
                for item in node.items
            )
        ]
        assert lock_blocks, f"{method.name} must serialize schedule mutations"


def test_diagnostic_history_store_failure_does_not_mutate_live_schedule():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_update_data"
    )
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert "schedule = deepcopy(self.schedule)" in source
    assert "await self.store.async_save(schedule)" in source
    assert "self.schedule = schedule" in source



def test_report_transaction_is_reconciled_at_startup_and_committed_after_store_save():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    setup = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_schedule"
    )
    setup_calls = [
        node.func.id if isinstance(node.func, ast.Name)
        else node.func.attr if isinstance(node.func, ast.Attribute)
        else None
        for node in ast.walk(setup)
        if isinstance(node, ast.Call)
    ]
    assert "async_reconcile_report_transactions" in setup_calls

    report = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_generate_report_locked"
    )
    report_source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), report
    )
    assert 'schedule["last_report_path"] = path' in report_source
    assert report_source.index("await self.store.async_save(schedule)") < report_source.index("await async_commit_report")


def test_report_module_uses_pending_and_complete_transaction_markers():
    source = (INTEGRATION / "report.py").read_text(encoding="utf-8")
    assert 'marker_path.touch()' in source
    assert 'f".{base}.pending"' in source
    assert 'f".{base}.complete"' in source
    assert "async_reconcile_report_transactions" in source
    assert "committed_report_path" in source



def test_focused_prompt_transaction_is_reconciled_and_committed_after_store_save():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    setup = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_schedule"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "async_reconcile_focused_prompt_transactions"
        for node in ast.walk(setup)
    )

    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_generate_focused_repair_prompt"
    )
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert source.index("await self.store.async_save(schedule)") < source.index("await async_commit_focused_prompt")



def test_scheduled_report_advances_due_date_in_same_store_transaction():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    scheduled = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_scheduled_check"
    )
    scheduled_source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), scheduled
    )
    assert 'scheduled_period="next_monthly"' in scheduled_source
    assert 'scheduled_period="next_weekly"' in scheduled_source
    assert "self.store.async_save" not in scheduled_source

    report = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_generate_report_locked"
    )
    report_source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), report
    )
    assert 'schedule["next_monthly"]' in report_source
    assert 'schedule["next_weekly"]' in report_source
    assert report_source.index('schedule["next_weekly"]') < report_source.index("await self.store.async_save(schedule)")



def test_coordinator_refresh_uses_one_locked_schedule_snapshot():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_update_data"
    )
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert "schedule_snapshot = deepcopy(self.schedule)" in source
    assert '"last_report_path": schedule_snapshot.get("last_report_path")' in source
    assert 'summarize_investigations(schedule_snapshot.get("investigation_history", []))' in source



def test_scheduled_check_delegates_due_date_mutation_to_locked_report_transaction():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_scheduled_check"
    )
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert 'scheduled_period="next_monthly"' in source
    assert 'scheduled_period="next_weekly"' in source
    assert "self.schedule[" not in source



def test_scheduled_report_rechecks_due_state_after_serialization_lock():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_generate_report_locked"
    )
    statements = method.body
    guard_index = next(
        index for index, statement in enumerate(statements)
        if isinstance(statement, ast.If)
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_is_due"
            for node in ast.walk(statement)
        )
    )
    collection_index = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "collect_snapshot"
            for node in ast.walk(statement)
        )
    )
    assert guard_index < collection_index


def test_startup_recovery_and_store_save_complete_before_scheduled_callback_registration():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    setup = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_schedule"
    )
    statements = setup.body
    report_recovery = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "async_reconcile_report_transactions"
            for node in ast.walk(statement)
        )
    )
    prompt_recovery = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "async_reconcile_focused_prompt_transactions"
            for node in ast.walk(statement)
        )
    )
    store_save = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_save"
            for node in ast.walk(statement)
        )
    )
    callback_registration = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "async_track_time_interval"
            for node in ast.walk(statement)
        )
    )
    assert report_recovery < store_save < callback_registration
    assert prompt_recovery < store_save < callback_registration


def test_focused_prompt_live_schedule_is_committed_only_after_store_save():
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
    statements = method.body
    store_save = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_save"
            for node in ast.walk(statement)
        )
    )
    schedule_commit = next(
        index for index, statement in enumerate(statements)
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "schedule"
            for target in statement.targets
        )
    )
    marker_commit = next(
        index for index, statement in enumerate(statements)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "async_commit_focused_prompt"
            for node in ast.walk(statement)
        )
    )
    assert store_save < schedule_commit < marker_commit


def test_coordinator_shutdown_unregisters_scheduled_callback():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    shutdown = next(
        node for node in coordinator.body
        if isinstance(node, ast.FunctionDef) and node.name == "async_shutdown"
    )
    calls = [
        node.func.attr
        for node in ast.walk(shutdown)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "self._schedule_unsub" in ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), shutdown
    )
    assert "_schedule_unsub" in calls
    assert "self._schedule_unsub()" in ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), shutdown
    )
    assert "self._schedule_unsub = None" in ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), shutdown
    )
