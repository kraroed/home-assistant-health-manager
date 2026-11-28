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



def test_report_state_is_committed_only_after_report_write_and_transactional_store_save():
    coordinator_tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in coordinator_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_generate_report_locked"
    )
    method_calls = [
        node for node in ast.walk(method) if isinstance(node, ast.Call)
    ]
    assert any(isinstance(node.func, ast.Name) and node.func.id == "deepcopy" for node in method_calls)
    assert any(isinstance(node.func, ast.Name) and node.func.id == "write_report" for node in method_calls)
    transaction_call = next(
        node for node in method_calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "async_save_report_transaction"
    )
    report_write = next(
        node for node in method_calls
        if isinstance(node.func, ast.Name) and node.func.id == "write_report"
    )
    schedule_commit = next(
        node for node in ast.walk(method)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Attribute) and target.attr == "schedule"
                for target in node.targets)
    )
    marker_commit = next(
        node for node in method_calls
        if isinstance(node.func, ast.Name) and node.func.id == "async_commit_report"
    )
    assert report_write.lineno < transaction_call.lineno < schedule_commit.lineno < marker_commit.lineno

    report_tree = _parse(INTEGRATION / "report.py")
    helper = next(
        node for node in report_tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_save_report_transaction"
    )
    helper_calls = [node for node in ast.walk(helper) if isinstance(node, ast.Call)]
    assert any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "async_save"
        for node in helper_calls
    )
    assert any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "_reconcile_report_transactions_sync"
        for node in helper_calls
    )


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
    report_calls = [node for node in ast.walk(report) if isinstance(node, ast.Call)]
    assert any(
        isinstance(node.func, ast.Name) and node.func.id == "async_save_report_transaction"
        for node in report_calls
    )
    assert any(
        isinstance(node.func, ast.Name) and node.func.id == "async_commit_report"
        for node in report_calls
    )
    assert 'schedule["last_report_path"] = path' in ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), report
    )

    report_tree = _parse(INTEGRATION / "report.py")
    helper = next(
        node for node in report_tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_save_report_transaction"
    )
    save = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_save"
    )
    reconcile_dispatch = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "_reconcile_report_transactions_sync"
    )
    assert save.lineno < reconcile_dispatch.lineno


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
    transaction_call = next(
        node for node in ast.walk(report)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "async_save_report_transaction"
    )
    due_date_assignments = [
        node for node in ast.walk(report)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.slice, ast.Constant)
            and target.slice.value in {"next_monthly", "next_weekly"}
            for target in (
                node.targets if isinstance(node, ast.Assign)
                else [node.target]
            )
        )
    ]
    assert due_date_assignments
    assert max(node.lineno for node in due_date_assignments) < transaction_call.lineno



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
    assert "verify_focused_prompts" in source
    assert "summarize_investigations(verified_investigations)" in source



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
    store_save = next(
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_save"
    )
    schedule_commit = next(
        node for node in ast.walk(method)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "schedule"
            for target in node.targets
        )
    )
    marker_commit = next(
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "async_commit_focused_prompt"
    )
    assert store_save.lineno < schedule_commit.lineno < marker_commit.lineno


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



def test_focused_prompt_retention_uses_pretransaction_history_and_saves_before_live_commit():
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
    nodes = list(ast.walk(method))
    preserved = next(
        node for node in nodes
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "preserved_prompt_paths"
            for target in node.targets
        )
    )
    record = next(
        node for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_investigation"
    )
    save = next(
        node for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_save"
    )
    live_commit = next(
        node for node in nodes
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "schedule"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            for target in node.targets
        )
    )
    assert preserved.lineno < record.lineno < save.lineno < live_commit.lineno


def test_investigation_status_is_not_committed_to_live_schedule_before_store_save():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_set_investigation_status"
    )
    nodes = list(ast.walk(method))
    candidate_copy = next(
        node for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "deepcopy"
    )
    history_update = next(
        node for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_investigation_status"
    )
    store_save = next(
        node for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_save"
    )
    live_commit = next(
        node for node in nodes
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "schedule"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            for target in node.targets
        )
    )
    assert candidate_copy.lineno < history_update.lineno < store_save.lineno < live_commit.lineno
    assert any(
        isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Attribute)
            and item.context_expr.attr == "_state_lock"
            for item in node.items
        )
        for node in ast.walk(method)
    )


def test_startup_recovers_persisted_artifacts_before_registering_schedule():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_schedule"
    )
    calls = [
        node.func.attr if isinstance(node.func, ast.Attribute)
        else node.func.id if isinstance(node.func, ast.Name)
        else None
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
    ]
    for required in (
        "async_load",
        "normalize_schedule_data",
        "async_reconcile_report_transactions",
        "async_reconcile_focused_prompt_transactions",
        "async_save",
        "async_track_time_interval",
    ):
        assert required in calls

    def first_line(name):
        return min(
            node.lineno for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == name)
                or (isinstance(node.func, ast.Name) and node.func.id == name)
            )
        )

    assert first_line("async_load") < first_line("normalize_schedule_data")
    assert first_line("normalize_schedule_data") < first_line("async_reconcile_report_transactions")
    assert first_line("async_reconcile_report_transactions") < first_line("async_reconcile_focused_prompt_transactions")
    assert first_line("async_reconcile_focused_prompt_transactions") < first_line("async_save")
    assert first_line("async_save") < first_line("async_track_time_interval")


def test_snapshot_uses_supported_home_assistant_core_version_constant():
    collector = _parse(INTEGRATION / "collector.py")
    imports_core_version = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "homeassistant.const"
        and any(
            alias.name == "__version__"
            and alias.asname == "HOME_ASSISTANT_VERSION"
            for alias in node.names
        )
        for node in collector.body
    )
    assert imports_core_version
    assert "hass.config.version" not in (
        INTEGRATION / "collector.py"
    ).read_text(encoding="utf-8")
    snapshot = next(
        node for node in collector.body
        if isinstance(node, ast.FunctionDef) and node.name == "collect_snapshot"
    )
    assert any(
        isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant)
            and key.value == "home_assistant_version"
            for key in node.keys
        )
        and any(
            isinstance(value, ast.Name)
            and value.id == "HOME_ASSISTANT_VERSION"
            for value in node.values
        )
        for node in ast.walk(snapshot)
    )


def test_classification_management_has_native_text_and_button_platforms():
    const = (INTEGRATION / "const.py").read_text(encoding="utf-8")
    assert 'PLATFORMS = ["sensor", "select", "text", "button"]' in const
    text_tree = _parse(INTEGRATION / "text.py")
    button_tree = _parse(INTEGRATION / "button.py")
    assert any(isinstance(node, ast.ClassDef) and node.name == "EntityClassificationReasonText" for node in text_tree.body)
    assert any(isinstance(node, ast.ClassDef) and node.name == "EntityClassificationTargetText" for node in text_tree.body)
    button_classes = {node.name for node in button_tree.body if isinstance(node, ast.ClassDef)}
    assert {"ApplyEntityClassificationButton", "RemoveEntityClassificationButton"} <= button_classes
    apply_button = next(node for node in button_tree.body if isinstance(node, ast.ClassDef) and node.name == "ApplyEntityClassificationButton")
    press = next(node for node in apply_button.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_press")
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_set_entity_classifications"
        for node in ast.walk(press)
    )
    assert any(isinstance(node, ast.Attribute) and node.attr == "strip" for node in ast.walk(press))


def test_classification_selector_supports_explicit_value_and_review_cadence():
    tree = _parse(INTEGRATION / "select.py")
    names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "EntityClassificationValueSelect" in names
    assert "ClassificationReviewIntervalSelect" in names
    assert "EntityClassificationReviewSelect" in names
    assert "ConfirmEntityClassificationReviewSelect" in names

def test_consolidated_health_overview_sensor_exposes_live_summary_attributes():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '("health_overview", "Health Overview", None, None)' in source
    assert 'if self.key == "health_overview":' in source
    assert 'if self.key in {"status", "health_overview"}:' in source
    for attribute in (
        '"active_issues":',
        '"actionable_unavailable_entity_count":',
        '"actionable_unknown_entity_count":',
        '"failed_config_entry_count":',
        '"classification_review_due_count":',
        '"collection_coverage":',
        '"compatibility_assessment":',
    ):
        assert attribute in source


def test_dashboard_displays_consolidated_health_metrics_and_raw_context():
    dashboard = (ROOT / "docs" / "DASHBOARD.md").read_text(encoding="utf-8")
    assert "sensor.health_overview" in dashboard
    assert "sensor.actionable_unavailable_entities" in dashboard
    assert "sensor.unavailable_entities" in dashboard
    assert "sensor.actionable_unknown_entities" in dashboard
    assert "sensor.unknown_entities" in dashboard
    assert "sensor.classification_reviews_due" in dashboard
    assert "last_assessment" in dashboard
    assert "last_report" in dashboard


def test_unavailable_observations_use_an_isolated_store_and_refresh_cycle():
    tree = _parse(INTEGRATION / "coordinator.py")
    source = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    assert "f'{DOMAIN}_availability_investigations'" in source
    assert "normalize_availability_data" in source
    assert "observe_unavailable_entities" in source
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_update_availability_observations"
    )
    assert any(
        isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Attribute)
            and item.context_expr.attr == "_state_lock"
            for item in node.items
        )
        for node in ast.walk(method)
    )
    assert "async_update_availability_observations(current_states)" in source


def test_unavailable_persistence_threshold_is_configurable_and_exposed():
    config = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    const = (INTEGRATION / "const.py").read_text(encoding="utf-8")
    assert "unavailable_persistence_minutes" in config
    assert "DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES = 60" in const
    assert "vol.Range(min=5, max=1440)" in config


def test_health_overview_exposes_persistent_and_missing_unavailable_metrics():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    for metric in (
        '"persistent_unavailable_entity_count":',
        '"persistent_unavailable_entity_ids":',
        '"missing_tracked_entity_count":',
        '"missing_tracked_entity_ids":',
        '"tracked_unavailable_entity_count":',
    ):
        assert metric in source


def test_unavailable_investigation_grouping_is_evidence_gated_and_configurable():
    config = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    grouping = (INTEGRATION / "availability_grouping.py").read_text(encoding="utf-8")
    assert "group_related_unavailable_entities" in config
    assert "build_unavailable_groups" in coordinator
    assert "SIMULTANEOUS_WINDOW_MINUTES = 5" in grouping
    assert "requires_user_review" in grouping
    assert "cause_confirmed" in grouping


def test_health_overview_includes_unavailable_investigation_group_details():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '"unavailable_investigation_groups":' in source
    assert '"unavailable_investigation_group_count":' in source


def test_dashboard_documents_live_unavailable_investigation_metrics():
    dashboard = (ROOT / "docs" / "DASHBOARD.md").read_text(encoding="utf-8")
    for entity_id in (
        "sensor.tracked_unavailable_entities",
        "sensor.persistent_unavailable_entities",
        "sensor.missing_tracked_entities",
        "sensor.unavailable_investigation_groups",
    ):
        assert entity_id in dashboard
    assert "root cause" in dashboard


def test_automatic_unavailable_groups_are_filtered_by_persistence_threshold():
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    assert coordinator.count("persistent_entity_ids=self.availability_summary.get") >= 2


def test_unavailable_investigation_controls_are_registered_and_user_driven():
    select_source = (INTEGRATION / "select.py").read_text(encoding="utf-8")
    button_source = (INTEGRATION / "button.py").read_text(encoding="utf-8")
    coordinator_source = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    select_tree = _parse(INTEGRATION / "select.py")
    names = {node.name for node in select_tree.body if isinstance(node, ast.ClassDef)}
    assert {
        "UnavailableInvestigationGroupSelect",
        "UnavailableInvestigationHistorySelect",
        "UnavailableInvestigationStatusSelect",
    } <= names
    assert "async_start_unavailable_investigation" in coordinator_source
    assert "async_set_unavailable_investigation_status" in coordinator_source
    assert "StartUnavailableInvestigationButton" in button_source
    assert "UnavailableInvestigationGroupSelect(coordinator, entry)" in select_source

def test_unavailable_investigation_details_are_exposed_in_health_overview():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    for attribute in (
        '"unavailable_investigations":',
        '"unavailable_investigation_status_counts":',
        '"unavailable_investigations_needing_review":',
    ):
        assert attribute in source


def test_unavailable_investigation_workflow_has_native_controls_and_services():
    select_tree = _parse(INTEGRATION / "select.py")
    button_tree = _parse(INTEGRATION / "button.py")
    text_tree = _parse(INTEGRATION / "text.py")
    service_source = (INTEGRATION / "services.py").read_text(encoding="utf-8")
    init_source = (INTEGRATION / "__init__.py").read_text(encoding="utf-8")
    select_classes = {node.name for node in select_tree.body if isinstance(node, ast.ClassDef)}
    button_classes = {node.name for node in button_tree.body if isinstance(node, ast.ClassDef)}
    text_classes = {node.name for node in text_tree.body if isinstance(node, ast.ClassDef)}
    assert {
        "UnavailableInvestigationGroupSelect",
        "UnavailableInvestigationHistorySelect",
        "UnavailableInvestigationStatusSelect",
    } <= select_classes
    assert {
        "StartUnavailableInvestigationButton",
        "StartManualUnavailableInvestigationButton",
    } <= button_classes
    assert {
        "UnavailableInvestigationEntityText",
        "UnavailableInvestigationNoteText",
    } <= text_classes
    assert 'async_register(DOMAIN, "start_unavailable_investigation"' in service_source
    assert 'async_register(DOMAIN, "set_unavailable_investigation_status"' in service_source
    assert 'async_remove(DOMAIN, "start_unavailable_investigation")' in init_source
    assert 'async_remove(DOMAIN, "set_unavailable_investigation_status")' in init_source


def test_unavailable_investigation_options_include_notifications_and_reminders():
    config = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    translations = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))
    for option in (
        "unavailable_persistence_minutes",
        "group_related_unavailable_entities",
        "unavailable_investigation_notifications",
        "unavailable_investigation_reminder_days",
    ):
        assert option in config
        assert option in strings["options"]["step"]["init"]["data"]
        assert option in translations["options"]["step"]["init"]["data"]


def test_health_overview_exposes_unavailable_investigation_history():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    for attribute in (
        '"unavailable_investigations":',
        '"unavailable_investigation_status_counts":',
        '"unavailable_investigations_needing_review":',
    ):
        assert attribute in source


def test_unavailable_investigation_sensor_entities_use_scalar_states_and_unique_keys():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    sensors = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SENSORS" for target in node.targets)
    )
    keys = [
        element.elts[0].value
        for element in sensors.value.elts
        if isinstance(element, ast.Tuple) and isinstance(element.elts[0], ast.Constant)
    ]
    assert len(keys) == len(set(keys))
    assert "unavailable_investigation_count" in keys
    assert "unavailable_investigations" not in keys
    assert 'if self.key == "unavailable_investigations":' not in source
    assert 'if self.key == "selected_unavailable_investigation":' in source


def test_availability_observations_collect_device_registry_context():
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    observer = (INTEGRATION / "availability_observer.py").read_text(encoding="utf-8")
    assert "device_registry as dr" in coordinator
    assert "device_registry.async_get(device_id)" in coordinator
    for field in ("device_name", "device_manufacturer", "device_model"):
        assert f'"{field}"' in coordinator
        assert f'"{field}"' in observer


def test_overview_exposes_new_unavailable_and_investigation_status_counts():
    source = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    for key in (
        "newly_unavailable_entity_count",
        "unavailable_investigations_in_progress",
        "unavailable_investigations_waiting",
        "unavailable_investigations_expected",
        "unavailable_investigations_resolved",
    ):
        assert f'"{key}"' in source
    assert "newly_unavailable_entity_ids" in source


def test_unavailable_entity_history_events_are_exposed_as_bounded_sensor_attributes():
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    sensor = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    assert '"availability_observation_events": self.availability_data["events"][-100:]' in coordinator
    assert '("availability_observation_event_count", "Unavailable Entity History Events"' in sensor
    assert '"events": data.get("availability_observation_events", [])' in sensor
    assert '"retained_limit": 100' in sensor


def test_unavailable_investigation_dashboard_uses_generated_entity_ids():
    dashboard = (ROOT / "docs" / "DASHBOARD.md").read_text(encoding="utf-8")
    expected = (
        "sensor.unavailable_investigation_groups",
        "sensor.unavailable_investigations",
        "sensor.unavailable_entity_history_events",
        "select.unavailable_group_to_investigate",
        "button.start_unavailable_investigation",
        "text.unavailable_entity_to_investigate",
        "button.start_manual_unavailable_investigation",
        "select.unavailable_investigation_to_update",
        "select.unavailable_investigation_status",
        "text.unavailable_investigation_note",
    )
    for entity_id in expected:
        assert entity_id in dashboard
    assert "home_assistant_health_manager_unavailable_" not in dashboard


def test_unavailable_duration_uses_home_assistant_state_last_changed():
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    observer = (INTEGRATION / "availability_observer.py").read_text(encoding="utf-8")
    assert '"last_changed": state.last_changed.isoformat()' in coordinator
    assert 'state_changed_at = _timestamp(item.get("last_changed"))' in observer


def test_classification_missing_grace_period_is_configurable_and_used():
    config = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    const = (INTEGRATION / "const.py").read_text(encoding="utf-8")
    coordinator = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    translations = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))
    assert "DEFAULT_CLASSIFICATION_MISSING_GRACE_MINUTES = 20" in const
    assert "classification_missing_grace_minutes" in config
    assert "vol.Range(min=1, max=120)" in config
    assert "missing_grace_minutes=self.entry.options.get(" in coordinator
    assert "classification_missing_grace_minutes" in strings["options"]["step"]["init"]["data"]
    assert "classification_missing_grace_minutes" in translations["options"]["step"]["init"]["data"]


def test_classification_coordinator_persists_before_committing_live_state():
    tree = _parse(INTEGRATION / "coordinator.py")
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_set_entity_classifications"
    )
    calls = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ]
    save = next(node for node in calls if node.func.attr == "async_save")
    commit = next(
        node for node in ast.walk(method)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "entity_classifications"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            for target in node.targets
        )
    )
    assert save.lineno < commit.lineno
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_bulk_classification_targets"
        for node in ast.walk(method)
    )
