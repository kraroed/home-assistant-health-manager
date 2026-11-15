import asyncio
import json
import os
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .const import DOMAIN, REPORT_DIR


async def write_report(
    hass, snapshot, analysis, sanitized_log, redaction_counts, recommendations,
    issue_history=None, issue_summary=None, repair_prompt=None, compatibility=None, change_summary=None,
):
    retention_days = hass.data.get(f"{DOMAIN}_retention_days", 90)
    directory = hass.config.path(REPORT_DIR)
    task = asyncio.create_task(asyncio.to_thread(
        _write_report_sync, directory, snapshot, analysis, sanitized_log,
        redaction_counts, recommendations, issue_history or {}, issue_summary or {},
        repair_prompt or "No AI repair prompt was generated.", compatibility or {}, change_summary or {}, retention_days
    ))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling asyncio.to_thread does not stop its worker thread. Wait for
        # publication to finish, then remove the uncommitted artifact set now
        # rather than leaving cleanup solely to the next HA startup.
        try:
            report_path = await task
        except Exception:
            pass
        else:
            await asyncio.to_thread(_remove_report_artifacts_sync, report_path)
        raise


def _write_report_sync(
    directory_path, snapshot, analysis, sanitized_log, redaction_counts,
    recommendations, issue_history, issue_summary, repair_prompt, compatibility, change_summary, retention_days,
):
    directory = Path(directory_path)
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    base = f"health_report_{stamp}"
    payload = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "privacy": {
            "processing": "local_only",
            "external_transmission": False,
            "redaction_counts": redaction_counts,
            "manual_review_required": True,
            "warning": "Automated redaction cannot guarantee detection of every identifier or secret.",
        },
        "system": snapshot,
        "log_analysis": analysis,
        "recommendations": recommendations,
        "prioritized_repair_plan": snapshot.get("repair_plan", {}),
        "compatibility_assessment": compatibility,
        "diagnostic_change_history": change_summary,
        "issue_history": issue_history,
        "issue_history_summary": issue_summary,
    }
    json_path = directory / f"{base}.json"
    txt_path = directory / f"{base}.txt"
    zip_path = directory / f"{base}.zip"
    prompt_path = directory / f"{base}_ai_repair_prompt.md"

    marker_path = directory / f".{base}.pending"

    # Build every artifact in a private staging directory first. A failed
    # serialization or ZIP operation must not leave a seemingly complete
    # report set in the user's report directory.
    with tempfile.TemporaryDirectory(prefix=".health_report_", dir=directory) as staging:
        staged = Path(staging)
        staged_json = staged / json_path.name
        staged_txt = staged / txt_path.name
        staged_zip = staged / zip_path.name
        staged_prompt = staged / prompt_path.name
        staged_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        summary = [
            "Home Assistant Health Manager report",
            f"Generated: {payload['generated_at']}",
            f"Assessment: {analysis.get('assessment_type', 'diagnostic')}",
            f"Home Assistant Core version: {snapshot.get('home_assistant_version', 'unknown')}",
            f"Platform update inventory: {snapshot.get('platform_updates', {})}",
            f"Update entity inventory: {snapshot.get('update_entity_inventory', {})}",
            f"Compatibility triage: {compatibility.get('overall_status', 'not_assessed')}",
            f"Compatibility scope: {compatibility.get('scope_note', '')}",
            f"Entities: {snapshot.get('entity_count', 0)}",
            f"Entity counts by domain: {snapshot.get('entity_counts_by_domain', {})}",
            f"Unavailable entities: {snapshot.get('unavailable_entity_count', 0)}",
            f"Unknown entities: {snapshot.get('unknown_entity_count', 0)}",
            f"Failed integrations: {snapshot.get('failed_config_entry_count', 0)}",
            f"Failed integration domains: {snapshot.get('failed_config_entry_domains', {})}",
            f"Integration setup states: {snapshot.get('config_entry_states', {})}",
            f"Configured integration inventory: {snapshot.get('integration_inventory', {})}",
            f"Integration domains needing attention: {snapshot.get('integration_inventory', {}).get('attention_domains', [])}",
            f"Log levels: {analysis.get('level_counts', {})}",
            f"Integration log evidence: {analysis.get('integration_log_evidence', {})}",
            f"Recommendations: {len(recommendations)}",
            f"Prioritized repair plan: {snapshot.get('repair_plan', {})}",
            f"Tracked issues: {issue_summary.get('tracked_issue_count', 0)}",
            f"Active tracked issues: {issue_summary.get('active_tracked_issue_count', 0)}",
            f"Resolved tracked issues: {issue_summary.get('resolved_tracked_issue_count', 0)}",
            f"Recurring issues: {issue_summary.get('recurring_issue_count', 0)}",
            f"Active recurring issues: {issue_summary.get('active_recurring_issue_count', 0)}",
            f"Recurring issue details: {issue_summary.get('recurring_issues', [])}",
            "",
            f"Diagnostic change history: {change_summary}",
            f"Diagnostic collection coverage: {snapshot.get('collection_coverage', {})}",
            f"Diagnostic trend: {snapshot.get('diagnostic_trend', {})}",
            f"Integration trend summary: {snapshot.get('integration_trend_summary', {})}",
            "",
            "LOCAL-ONLY REPORT. Manual review is required before sharing.",
            f"Redaction counts: {redaction_counts}",
        ]
        for item in recommendations:
            summary.extend(["", f"[{item['severity'].upper()}] {item['title']}", item["detail"], f"Suggested next step: {item['suggested_action']}"])
        staged_txt.write_text("\\n".join(summary), encoding="utf-8")
        staged_prompt.write_text(repair_prompt, encoding="utf-8")
        with zipfile.ZipFile(staged_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(staged_json, arcname="health_report.json")
            archive.write(staged_txt, arcname="summary.txt")
            archive.write(staged_prompt, arcname="ai_repair_prompt.md")
            if sanitized_log is not None:
                archive.writestr("logs/home_assistant_core_sanitized.log", sanitized_log)

        # The marker lets startup distinguish an interrupted publication from
        # a report whose Store transaction was committed.
        marker_path.touch()
        # Publish only after all four artifacts have been created successfully.
        for staged_path, final_path in (
            (staged_json, json_path),
            (staged_txt, txt_path),
            (staged_prompt, prompt_path),
            (staged_zip, zip_path),
        ):
            os.replace(staged_path, final_path)
    cutoff = now - timedelta(days=max(7, min(int(retention_days), 365)))
    # The ZIP is the canonical report artifact. Its completion marker is
    # written only after the Store transaction commits, so its mtime is
    # expected to be newer than the report files. Retention must remove the
    # marker with the report set rather than age-checking it independently.
    for report_zip in directory.glob("health_report_*.zip"):
        try:
            if not report_zip.is_file() or datetime.fromtimestamp(
                report_zip.stat().st_mtime, timezone.utc
            ) >= cutoff:
                continue
            base = report_zip.stem
            # A pending marker is a live recovery record. Leave the entire
            # artifact set untouched until startup reconciliation determines
            # whether its Store transaction committed.
            if (directory / f".{base}.pending").exists():
                continue
            for suffix in (".json", ".txt", ".zip", "_ai_repair_prompt.md"):
                (directory / f"{base}{suffix}").unlink(missing_ok=True)
            (directory / f".{base}.complete").unlink(missing_ok=True)
        except OSError:
            continue
    return str(zip_path)




async def async_reconcile_report_transactions(hass, committed_report_path=None):
    """Recover interrupted report publications after Home Assistant restarts."""
    directory = Path(hass.config.path(REPORT_DIR))
    await asyncio.to_thread(_reconcile_report_transactions_sync, directory, committed_report_path)


def _reconcile_report_transactions_sync(directory, committed_report_path=None):
    if not directory.exists():
        return
    committed = Path(committed_report_path).name if committed_report_path else None
    for staging in directory.glob(".health_report_*"):
        try:
            if staging.is_dir():
                import shutil
                shutil.rmtree(staging, ignore_errors=True)
        except OSError:
            continue
    for marker in directory.glob(".health_report_*.pending"):
        base = marker.name[1:-len(".pending")]
        zip_name = f"{base}.zip"
        if zip_name == committed:
            try:
                marker.replace(directory / f".{base}.complete")
            except OSError:
                continue
            continue
        for suffix in (".json", ".txt", ".zip", "_ai_repair_prompt.md"):
            try:
                (directory / f"{base}{suffix}").unlink(missing_ok=True)
            except OSError:
                continue
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            continue


async def async_commit_report(hass, report_path):
    """Mark a report transaction committed after its Store record is durable."""
    directory = Path(hass.config.path(REPORT_DIR))
    await asyncio.to_thread(_commit_report_sync, directory, report_path)


def _commit_report_sync(directory, report_path):
    base = Path(report_path).stem
    pending = directory / f".{base}.pending"
    if pending.exists():
        pending.replace(directory / f".{base}.complete")



async def async_reconcile_focused_prompt_transactions(hass, investigation_history):
    """Remove focused prompts left behind by an interrupted Store transaction."""
    directory = Path(hass.config.path(REPORT_DIR))
    committed_paths = {
        Path(item["prompt_path"]).name
        for item in investigation_history
        if isinstance(item, dict) and isinstance(item.get("prompt_path"), str)
    }
    await asyncio.to_thread(_reconcile_focused_prompt_transactions_sync, directory, committed_paths)


def _reconcile_focused_prompt_transactions_sync(directory, committed_paths):
    if not directory.exists():
        return
    for marker in directory.glob(".focused_repair_*.md.pending"):
        filename = marker.name[1:-len(".pending")]
        if filename not in committed_paths:
            try:
                (directory / filename).unlink(missing_ok=True)
            except OSError:
                continue
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            continue


async def async_commit_focused_prompt(hass, prompt_path):
    """Finalize a focused prompt after its investigation record is durable."""
    path = Path(prompt_path)
    marker = path.with_name(f".{path.name}.pending")
    await asyncio.to_thread(marker.unlink, missing_ok=True)


async def write_focused_repair_prompt(hass, plan_id, prompt):
    """Write one focused prompt locally without adding raw diagnostic data."""
    directory = hass.config.path(REPORT_DIR)
    safe_id = "".join(char if char.isalnum() or char in "_-" else "_" for char in plan_id)[:80]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    retention_days = hass.data.get(f"{DOMAIN}_retention_days", 90)
    task = asyncio.create_task(asyncio.to_thread(
        _write_focused_prompt_sync, directory, safe_id, stamp, prompt, retention_days, set()
    ))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # The worker may finish after its awaiting task is cancelled. Remove
        # the prompt and pending marker so an uncommitted prompt is not orphaned.
        try:
            prompt_path = await task
        except Exception:
            pass
        else:
            await asyncio.to_thread(_remove_focused_prompt_artifacts_sync, prompt_path)
        raise


def _write_focused_prompt_sync(directory_path, safe_id, stamp, prompt, retention_days, preserved_paths=None):
    directory = Path(directory_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"focused_repair_{safe_id}_{stamp}.md"
    marker = path.with_name(f".{path.name}.pending")
    marker.touch()
    path.write_text(prompt, encoding="utf-8")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(7, min(int(retention_days), 365)))
    preserved_names = {
        Path(value).name for value in (preserved_paths or set()) if isinstance(value, str)
    }
    for old_file in directory.glob("focused_repair_*.md"):
        try:
            if (
                old_file.name not in preserved_names
                and old_file.is_file()
                and datetime.fromtimestamp(old_file.stat().st_mtime, timezone.utc) < cutoff
                and not old_file.with_name(f".{old_file.name}.pending").exists()
            ):
                old_file.unlink()
        except OSError:
            continue
    return str(path)



def _remove_report_artifacts_sync(report_path):
    """Remove an unpublished report set after its writer thread has finished."""
    path = Path(report_path)
    directory = path.parent
    base = path.stem
    for suffix in (".json", ".txt", ".zip", "_ai_repair_prompt.md"):
        try:
            (directory / f"{base}{suffix}").unlink(missing_ok=True)
        except OSError:
            continue
    try:
        (directory / f".{base}.pending").unlink(missing_ok=True)
    except OSError:
        pass


def _remove_focused_prompt_artifacts_sync(prompt_path):
    """Remove an unpublished focused prompt and its transaction marker."""
    path = Path(prompt_path)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        path.with_name(f".{path.name}.pending").unlink(missing_ok=True)
    except OSError:
        pass
