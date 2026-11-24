import json
import zipfile

from custom_components.home_assistant_health_manager.report_verification import verify_report


def _make_report(path, members=None):
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in (members or {
            "health_report.json": json.dumps({"schema_version": 1}),
            "summary.txt": "summary",
            "ai_repair_prompt.md": "prompt",
        }).items():
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
