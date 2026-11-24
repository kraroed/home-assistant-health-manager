"""Verify the canonical diagnostic ZIP before claiming report preservation."""

from __future__ import annotations

import os
import zipfile
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
            result.update(status="invalid_path", error="Report path is outside the configured report directory.")
            return result
        result["path"] = str(path)
        if not path.exists():
            result["error"] = "The recorded report file does not exist."
            return result
        result["exists"] = True
        if not path.is_file():
            result.update(status="unreadable", error="The report path is not a regular file.")
            return result
        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        if not zipfile.is_zipfile(path):
            result.update(status="corrupt", error="The report is not a valid ZIP archive.")
            return result
        with zipfile.ZipFile(path, "r") as archive:
            bad_member = archive.testzip()
            names = set(archive.namelist())
            verified = [name for name in EXPECTED_REPORT_MEMBERS if name in names]
            missing = [name for name in EXPECTED_REPORT_MEMBERS if name not in names]
            result["verified_members"] = verified
            result["missing_members"] = missing
            if bad_member:
                result.update(status="corrupt", error=f"ZIP integrity check failed for {bad_member}.")
            elif missing:
                result.update(status="incomplete", error="One or more required report files are missing.")
            else:
                # Parse the JSON too: a ZIP entry's presence alone is insufficient.
                import json
                json.loads(archive.read("health_report.json"))
                result.update(status="verified", readable=True, error=None)
        return result
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as err:
        result.update(status="unreadable", error=f"Unable to verify report: {err}")
        return result
