import asyncio
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .const import REPORT_DIR


async def write_report(hass, snapshot, analysis, sanitized_log, redaction_counts):
    return await asyncio.to_thread(
        _write_report_sync, hass, snapshot, analysis, sanitized_log, redaction_counts
    )


def _write_report_sync(hass, snapshot, analysis, sanitized_log, redaction_counts):
    directory = Path(hass.config.path(REPORT_DIR))
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"health_report_{stamp}"
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "processing": "local_only",
            "external_transmission": False,
            "redaction_counts": redaction_counts,
            "manual_review_required": True,
            "warning": "Automated redaction cannot guarantee detection of every identifier or secret.",
        },
        "system": snapshot,
        "log_analysis": analysis,
    }
    json_path = directory / f"{base}.json"
    txt_path = directory / f"{base}.txt"
    zip_path = directory / f"{base}.zip"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = [
        "Home Assistant Health Manager report",
        f"Generated: {payload['generated_at']}",
        f"Entities: {snapshot.get('entity_count', 0)}",
        f"Unavailable/unknown entities: {snapshot.get('unavailable_entity_count', 0)}",
        f"Configured integrations: {snapshot.get('config_entry_count', 0)}",
        f"Log levels: {analysis.get('level_counts', {})}",
        "",
        "LOCAL-ONLY REPORT. Manual review is required before sharing.",
        f"Redaction counts: {redaction_counts}",
    ]
    txt_path.write_text("\n".join(summary), encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(json_path, arcname="health_report.json")
        archive.write(txt_path, arcname="summary.txt")
        if sanitized_log is not None:
            archive.writestr("logs/home_assistant_core_sanitized.log", sanitized_log)
    return str(zip_path)
