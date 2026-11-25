"""Verify the canonical diagnostic ZIP before claiming report preservation."""

from __future__ import annotations

import json
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_REPORT_MEMBERS = (
    "health_report.json",
    "summary.txt",
    "ai_repair_prompt.md",
)


def verify_report(report_directory: str | Path, report_path: str | None) -> dict:
    """Return phone-friendly verification metadata for the latest report.

    Paths are constrained to the configured report directory. The ZIP is read
    and tested; merely storing a path never counts as preservation.
    """
    directory = Path(report_directory).resolve()
    result = {
        "status": "missing",
        "exists": False,
        "readable": False,
        "path": None,
        "size_bytes": None,
        "modified_at": None,
        "expected_members": list(EXPECTED_REPORT_MEMBERS),
        "verified_members": [],
        "missing_members": list(EXPECTED_REPORT_MEMBERS),
        "error": None,
    }
    if not isinstance(report_path, str) or not report_path.strip():
        result["error"] = "No report path is recorded."
        return result

    try:
        path = Path(report_path).resolve()
        if path.parent != directory:
            result.update(
                status="invalid_path",
                error="Report path is outside the configured report directory.",
            )
            return result
        result["path"] = str(path)
        if not path.exists():
            result["error"] = "The recorded report file does not exist."
            return result
        result["exists"] = True
        if not path.is_file():
            result.update(
                status="unreadable",
                error="The report path is not a regular file.",
            )
            return result

        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["modified_at"] = datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat()
        if not zipfile.is_zipfile(path):
            result.update(
                status="corrupt",
                error="The report is not a valid ZIP archive.",
            )
            return result

        with zipfile.ZipFile(path, "r") as archive:
            bad_member = archive.testzip()
            names = set(archive.namelist())
            verified = [
                name for name in EXPECTED_REPORT_MEMBERS if name in names
            ]
            missing = [
                name for name in EXPECTED_REPORT_MEMBERS if name not in names
            ]
            result["verified_members"] = verified
            result["missing_members"] = missing
            if bad_member:
                result.update(
                    status="corrupt",
                    error=f"ZIP integrity check failed for {bad_member}.",
                )
            elif missing:
                result.update(
                    status="incomplete",
                    error="One or more required report files are missing.",
                )
            else:
                report_data = json.loads(archive.read("health_report.json"))
                if (
                    not isinstance(report_data, dict)
                    or report_data.get("schema_version") != 1
                    or not isinstance(report_data.get("system"), dict)
                ):
                    result.update(
                        status="incomplete",
                        error=(
                            "The diagnostic JSON is missing its expected "
                            "schema or system snapshot."
                        ),
                    )
                else:
                    result.update(status="verified", readable=True, error=None)
        return result
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError,
            EOFError, zlib.error, NotImplementedError) as err:
        result.update(status="unreadable", error=f"Unable to verify report: {err}")
        return result



def verify_focused_prompt(report_directory: str | Path, prompt_path: str | None) -> dict:
    """Verify one focused Markdown prompt and expose compact UI metadata.

    The resolved file must be a regular file directly inside the configured
    report directory. A stored path alone never counts as preservation.
    """
    directory = Path(report_directory).resolve()
    result = {
        "status": "missing",
        "exists": False,
        "readable": False,
        "path": None,
        "size_bytes": None,
        "modified_at": None,
        "error": None,
    }
    if not isinstance(prompt_path, str) or not prompt_path.strip():
        result["error"] = "No focused prompt path is recorded."
        return result

    try:
        path = Path(prompt_path).resolve()
        if path.parent != directory:
            result.update(
                status="invalid_path",
                error="Focused prompt path is outside the configured report directory.",
            )
            return result
        result["path"] = str(path)
        if not path.exists():
            result["error"] = "The recorded focused prompt file does not exist."
            return result
        result["exists"] = True
        if not path.is_file():
            result.update(
                status="unreadable",
                error="The focused prompt path is not a regular file.",
            )
            return result

        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["modified_at"] = datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat()
        content = path.read_bytes()
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            result.update(
                status="unreadable",
                error="The focused prompt is not valid UTF-8 text.",
            )
            return result
        result["readable"] = True
        if not content:
            result.update(
                status="empty",
                error="The focused prompt file is empty.",
            )
            return result
        result.update(status="verified", error=None)
        return result
    except OSError as err:
        result.update(
            status="unreadable",
            error=f"Unable to verify focused prompt: {err}",
        )
        return result


def verify_focused_prompts(report_directory: str | Path, investigations) -> list[dict]:
    """Return investigation records with freshly verified prompt metadata."""
    records = investigations if isinstance(investigations, list) else []
    verified_records = []
    for item in records[:50]:
        if not isinstance(item, dict):
            continue
        record = dict(item)
        record["prompt_verification"] = verify_focused_prompt(
            report_directory, record.get("prompt_path")
        )
        verified_records.append(record)
    return verified_records
