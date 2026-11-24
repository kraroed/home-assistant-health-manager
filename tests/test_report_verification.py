import json
import zipfile

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "report_verification.py"
)
SPEC = spec_from_file_location("health_manager_report_verification", MODULE_PATH)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
verify_report = MODULE.verify_report


def _make_report(path, members=None):
    if members is None:
        members = {
            "health_report.json": json.dumps(
                {"schema_version": 1, "system": {"entity_count": 1}}
            ),
            "summary.txt": "summary",
            "ai_repair_prompt.md": "prompt",
        }
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_verifies_complete_readable_report(tmp_path):
    path = tmp_path / "health_report_test.zip"
    _make_report(path)
    result = verify_report(tmp_path, str(path))
    assert result["status"] == "verified"
    assert result["exists"] is True
    assert result["readable"] is True
    assert result["size_bytes"] > 0
    assert result["modified_at"]
    assert result["missing_members"] == []


def test_missing_report_is_not_preserved(tmp_path):
    result = verify_report(tmp_path, str(tmp_path / "missing.zip"))
    assert result["status"] == "missing"
    assert result["exists"] is False
    assert result["readable"] is False


def test_path_outside_report_directory_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside.zip"
    _make_report(outside)
    result = verify_report(tmp_path, str(outside))
    assert result["status"] == "invalid_path"
    assert result["exists"] is False


def test_incomplete_report_is_not_verified(tmp_path):
    path = tmp_path / "partial.zip"
    _make_report(path, {"health_report.json": json.dumps({"schema_version": 1})})
    result = verify_report(tmp_path, str(path))
    assert result["status"] == "incomplete"
    assert result["readable"] is False
    assert set(result["missing_members"]) == {"summary.txt", "ai_repair_prompt.md"}


def test_invalid_json_report_is_not_verified(tmp_path):
    path = tmp_path / "invalid_json.zip"
    _make_report(
        path,
        {
            "health_report.json": "{not valid JSON",
            "summary.txt": "summary",
            "ai_repair_prompt.md": "prompt",
        },
    )
    result = verify_report(tmp_path, str(path))
    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False


def test_corrupt_archive_is_not_verified(tmp_path):
    path = tmp_path / "corrupt.zip"
    path.write_text("not a zip", encoding="utf-8")
    result = verify_report(tmp_path, str(path))
    assert result["status"] == "corrupt"
    assert result["exists"] is True
    assert result["readable"] is False


def test_missing_path_is_not_verified(tmp_path):
    result = verify_report(tmp_path, None)
    assert result["status"] == "missing"
    assert result["path"] is None


def test_directory_at_report_path_is_unreadable(tmp_path):
    report_dir = tmp_path / "not_a_file.zip"
    report_dir.mkdir()
    result = verify_report(tmp_path, str(report_dir))
    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False


def test_permission_error_is_reported_as_unreadable(tmp_path, monkeypatch):
    path = tmp_path / "permission_denied.zip"
    _make_report(path)

    def raise_permission_error(_path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(MODULE.zipfile, "is_zipfile", raise_permission_error)
    result = verify_report(tmp_path, str(path))
    assert result["status"] == "unreadable"
    assert result["exists"] is True
    assert result["readable"] is False
    assert "permission denied" in result["error"]
