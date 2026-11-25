from importlib.util import module_from_spec, spec_from_file_location
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = (
    ROOT
    / "custom_components"
    / "home_assistant_health_manager"
    / "report_verification.py"
)
SPEC = spec_from_file_location("health_manager_prompt_verification", MODULE_PATH)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

verify_focused_prompt = MODULE.verify_focused_prompt
verify_focused_prompts = MODULE.verify_focused_prompts


def test_verifies_existing_readable_focused_prompt(tmp_path):
    path = tmp_path / "focused_repair_example.md"
    path.write_text("# Focused repair prompt\\nReview before sharing.\\n", encoding="utf-8")

    result = verify_focused_prompt(tmp_path, str(path))

    assert result["status"] == "verified"
    assert result["exists"] is True
    assert result["readable"] is True
    assert result["path"] == str(path)
    assert result["size_bytes"] == path.stat().st_size
    assert result["modified_at"]
    assert result["error"] is None


def test_missing_focused_prompt_is_not_preserved(tmp_path):
    result = verify_focused_prompt(tmp_path, str(tmp_path / "missing.md"))

    assert result["status"] == "missing"
    assert result["exists"] is False
    assert result["readable"] is False
    assert result["size_bytes"] is None


def test_missing_focused_prompt_path_is_reported(tmp_path):
    result = verify_focused_prompt(tmp_path, None)

    assert result["status"] == "missing"
    assert result["path"] is None
    assert "No focused prompt path" in result["error"]


def test_focused_prompt_outside_report_directory_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside_focused_prompt.md"
    outside.write_text("not in reports", encoding="utf-8")

    result = verify_focused_prompt(tmp_path, str(outside))

    assert result["status"] == "invalid_path"
    assert result["exists"] is False
    assert result["path"] is None


def test_directory_at_focused_prompt_path_is_unreadable(tmp_path):
    path = tmp_path / "not_a_prompt.md"
    path.mkdir()

    result = verify_focused_prompt(tmp_path, str(path))

    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False


def test_empty_focused_prompt_is_not_verified(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")

    result = verify_focused_prompt(tmp_path, str(path))

    assert result["status"] == "empty"
    assert result["exists"] is True
    assert result["readable"] is True
    assert result["size_bytes"] == 0


def test_non_utf8_focused_prompt_is_unreadable(tmp_path):
    path = tmp_path / "invalid_utf8.md"
    path.write_bytes(b"\\xff\\xfe")

    result = verify_focused_prompt(tmp_path, str(path))

    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False
    assert result["error"] == "The focused prompt is not valid UTF-8 text."


def test_focused_prompt_read_error_is_reported(tmp_path, monkeypatch):
    path = tmp_path / "unreadable.md"
    path.write_text("prompt", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def deny_read(self):
        if self == path:
            raise PermissionError("permission denied")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    result = verify_focused_prompt(tmp_path, str(path))

    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False
    assert "permission denied" in result["error"]


def test_batch_verification_attaches_metadata_without_mutating_history(tmp_path):
    path = tmp_path / "focused_repair_example.md"
    path.write_text("prompt", encoding="utf-8")
    history = [{"plan_id": "integration_example", "prompt_path": str(path)}]

    records = verify_focused_prompts(tmp_path, history)

    assert records[0]["prompt_verification"]["status"] == "verified"
    assert "prompt_verification" not in history[0]


def test_coordinator_verifies_investigations_off_event_loop_and_sensor_exposes_them():
    coordinator = (
        ROOT / "custom_components" / "home_assistant_health_manager" / "coordinator.py"
    ).read_text(encoding="utf-8")
    sensor = (
        ROOT / "custom_components" / "home_assistant_health_manager" / "sensor.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(coordinator)
    update_method = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_update_data"
    )
    calls = [
        node for node in ast.walk(update_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "async_add_executor_job"
    ]
    assert any(
        any(
            isinstance(argument, ast.Name)
            and argument.id == "verify_focused_prompts"
            for argument in call.args
        )
        for call in calls
    )
    assert "summarize_investigations(verified_investigations)" in coordinator
    assert '"investigations": data.get("investigations", [])' in sensor
