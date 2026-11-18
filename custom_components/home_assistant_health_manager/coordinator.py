import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .collector import collect_snapshot, read_core_log
from .compatibility import assess_compatibility
from .const import DOMAIN, SCHEDULE_INTERVAL, STORE_KEY, STORE_VERSION, UPDATE_INTERVAL
from .history import summarize_issue_history, update_issue_history
from .change_history import update_change_history
from .collection_coverage import build_collection_coverage
from .trend_history import summarize_trends, update_trend_history
from .integration_trends import summarize_integration_trends, update_integration_trend_history
from .log_analyzer import analyze_log
from .recommendations import add_integration_trend_recommendations, add_recurring_issue_recommendations, build_recommendations
from .redactor import redact_object, redact_text
from .report import (
    async_commit_focused_prompt,
    async_commit_report,
    async_reconcile_focused_prompt_transactions,
    async_reconcile_report_transactions,
    write_report,
    write_focused_repair_prompt,
)
from .repair_prompt import build_repair_prompt
from .repair_plan import build_repair_plan
from .focused_repair_prompt import build_focused_repair_prompt
from .investigation_history import record_investigation, set_investigation_status, summarize_investigations
from .storage import normalize_schedule_data

_LOGGER = logging.getLogger(__name__)


class HealthManagerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORE_VERSION, STORE_KEY)
        self.schedule = {}
        self.last_report_path = None
        self.last_prompt_path = None
        self.last_repair_context = None
        self.selected_investigation_plan_id = None
        self._schedule_unsub = None
        self._report_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self.hass.data[f"{DOMAIN}_retention_days"] = entry.options.get("retention_days", 90)

    async def async_setup_schedule(self):
        stored_data = await self.store.async_load()
        self.schedule = normalize_schedule_data(stored_data)
        await async_reconcile_report_transactions(
            self.hass, self.schedule.get("last_report_path")
        )
        await async_reconcile_focused_prompt_transactions(
            self.hass, self.schedule.get("investigation_history", [])
        )
        self.last_report_path = self.schedule.get("last_report_path")
        if self.last_report_path and self.last_report_path.endswith(".zip"):
            self.last_prompt_path = self.last_report_path[:-4] + "_ai_repair_prompt.md"
        await self.store.async_save(self.schedule)
        from homeassistant.helpers.event import async_track_time_interval
        self._schedule_unsub = async_track_time_interval(
            self.hass, self._async_scheduled_check, SCHEDULE_INTERVAL
        )

    def async_shutdown(self):
        if self._schedule_unsub:
            self._schedule_unsub()
            self._schedule_unsub = None

    async def _async_scheduled_check(self, _now):
        now = datetime.now(timezone.utc)
        try:
            if self.entry.options.get("monthly_reviews", True) and _is_due(self.schedule.get("next_monthly"), now):
                await self.async_generate_report(comprehensive=True, scheduled_period="next_monthly")
            elif self.entry.options.get("weekly_reports", True) and _is_due(self.schedule.get("next_weekly"), now):
                await self.async_generate_report(comprehensive=False, scheduled_period="next_weekly")
            await self.async_request_refresh()
        except Exception:
            _LOGGER.exception("Scheduled health review failed")

    async def _async_update_data(self):
        try:
            # Home Assistant's async state/config-entry APIs must stay on the
            # event loop; only blocking filesystem work belongs in the executor.
            snapshot = collect_snapshot(self.hass)
            snapshot["collection_coverage"] = build_collection_coverage(snapshot)
            async with self._state_lock:
                change_history, change_summary = update_change_history(self.schedule.get('change_history', []), snapshot, snapshot['collected_at'])
                if change_history != self.schedule.get('change_history', []):
                    schedule = deepcopy(self.schedule)
                    schedule['change_history'] = change_history
                    await self.store.async_save(schedule)
                    self.schedule = schedule
                schedule_snapshot = deepcopy(self.schedule)
            history_summary = summarize_issue_history(schedule_snapshot.get("issue_history", {}))
            return {
                **snapshot,
                **history_summary,
                "status": "attention" if snapshot["unavailable_entity_count"] or snapshot["actionable_unknown_entity_count"] or snapshot["failed_config_entry_count"] else "healthy",
                "active_issues": snapshot["unavailable_entity_count"] + snapshot["actionable_unknown_entity_count"] + snapshot["failed_config_entry_count"],
                "last_assessment": schedule_snapshot.get("last_assessment"),
                "last_report": schedule_snapshot.get("last_report"),
                "report_count": schedule_snapshot.get("report_count", 0),
                "last_report_path": schedule_snapshot.get("last_report_path"),
                "last_ai_repair_prompt_path": (
                    schedule_snapshot.get("last_report_path", "")[:-4] + "_ai_repair_prompt.md"
                    if schedule_snapshot.get("last_report_path", "").endswith(".zip") else None
                ),
                "compatibility_assessment": schedule_snapshot.get("last_compatibility", {}),
                "diagnostic_change_history": change_summary,
                "diagnostic_trend": summarize_trends(schedule_snapshot.get("trend_history", [])),
                "integration_trend_summary": summarize_integration_trends(schedule_snapshot.get("integration_trend_history", [])),
                "repair_plan": schedule_snapshot.get("last_repair_plan", {}),
                **summarize_investigations(schedule_snapshot.get("investigation_history", [])),
            }
        except Exception as err:
            raise UpdateFailed(f"Unable to collect diagnostics: {err}") from err

    async def async_generate_report(self, comprehensive=False, scheduled_period=None):
        """Serialize report generation so schedule history cannot race."""
        async with self._report_lock:
            async with self._state_lock:
                return await self._async_generate_report_locked(comprehensive, scheduled_period)

    async def _async_generate_report_locked(self, comprehensive=False, scheduled_period=None):
        schedule = deepcopy(self.schedule)
        # A second interval callback may have queued while another scheduled
        # report held the locks. Re-check due state after acquiring them.
        if scheduled_period and not _is_due(schedule.get(scheduled_period), datetime.now(timezone.utc)):
            return None
        snapshot = collect_snapshot(self.hass)
        change_history, change_summary = update_change_history(schedule.get('change_history', []), snapshot, snapshot['collected_at'])
        schedule['change_history'] = change_history
        snapshot['diagnostic_change_history'] = change_summary
        raw_log, log_error = (None, None)
        core_log_status = "not_enabled"
        if self.entry.options.get("include_core_log", True):
            max_bytes = 5_000_000 if comprehensive else 1_500_000
            log_path = self.hass.config.path("home-assistant.log")
            raw_log, log_error = await self.hass.async_add_executor_job(read_core_log, log_path, max_bytes)
            core_log_status = "collected" if raw_log is not None else "unavailable"
        sanitized_log, log_counts = redact_text(raw_log) if raw_log else (None, {})
        snapshot["collection_coverage"] = build_collection_coverage(snapshot, core_log_status)
        analysis = analyze_log(sanitized_log)
        if log_error:
            analysis["collection_note"] = log_error
        analysis["assessment_type"] = "monthly_comprehensive" if comprehensive else "weekly_diagnostic"
        now = datetime.now(timezone.utc)
        compatibility = assess_compatibility(snapshot, analysis)
        trend_history, trend_summary = update_trend_history(
            schedule.get("trend_history", []), snapshot, analysis, compatibility, now.isoformat()
        )
        schedule["trend_history"] = trend_history
        snapshot["diagnostic_trend"] = trend_summary
        integration_trend_history, integration_trend_summary = update_integration_trend_history(
            schedule.get("integration_trend_history", []),
            snapshot.get("integration_inventory", {}),
            now.isoformat(),
        )
        schedule["integration_trend_history"] = integration_trend_history
        snapshot["integration_trend_summary"] = integration_trend_summary
        recommendations = build_recommendations(snapshot, analysis)
        recommendations = add_integration_trend_recommendations(recommendations, integration_trend_summary)
        schedule["issue_history"] = update_issue_history(
            schedule.get("issue_history", {}),
            recommendations,
            now.isoformat(),
        )
        history_summary = summarize_issue_history(schedule["issue_history"])
        recommendations = add_recurring_issue_recommendations(recommendations, history_summary)
        snapshot["issue_history_summary"] = history_summary
        snapshot["repair_plan"] = build_repair_plan(
            recommendations,
            analysis.get("integration_log_evidence", {}),
            integration_trend_summary,
        )
        schedule["last_repair_plan"] = snapshot["repair_plan"]
        safe_snapshot, snapshot_counts = redact_object(snapshot)
        safe_compatibility, _ = redact_object(compatibility)
        safe_recommendations, _ = redact_object(recommendations)
        safe_analysis, _ = redact_object(analysis)
        safe_snapshot['compatibility_assessment'] = safe_compatibility
        repair_context = {
            'generated_at': now.isoformat(),
            'snapshot': safe_snapshot,
            'analysis': safe_analysis,
            'recommendations': safe_recommendations,
            'repair_plan': safe_snapshot.get('repair_plan', {}),
        }
        repair_prompt = build_repair_prompt(safe_snapshot, analysis, safe_recommendations, now.isoformat(), safe_compatibility)
        path = await write_report(
            self.hass, safe_snapshot, analysis, sanitized_log,
            {"core_log": log_counts, "snapshot": snapshot_counts},
            recommendations, schedule["issue_history"], history_summary, repair_prompt, safe_compatibility, change_summary,
        )
        schedule["last_compatibility"] = safe_compatibility
        schedule["last_assessment"] = now.isoformat()
        schedule["last_report"] = now.isoformat()
        schedule["last_report_path"] = path
        if scheduled_period == "next_monthly":
            schedule["next_monthly"] = (now + timedelta(days=30)).isoformat()
        elif scheduled_period == "next_weekly":
            schedule["next_weekly"] = (now + timedelta(days=7)).isoformat()
        schedule["report_count"] = schedule.get("report_count", 0) + 1
        await self.store.async_save(schedule)
        self.schedule = schedule
        try:
            await async_commit_report(self.hass, path)
        except OSError:
            # The durable Store reference lets startup finish this marker rename.
            _LOGGER.exception("Report was saved, but its commit marker could not be finalized")
        self.last_repair_context = repair_context
        self.last_report_path = path
        self.last_prompt_path = path[:-4] + "_ai_repair_prompt.md" if path.endswith(".zip") else None
        self.async_update_listeners()
        return path

    async def async_generate_focused_repair_prompt(self, plan_id):
        """Generate a focused prompt for one item from the latest report."""
        async with self._state_lock:
            context = self.last_repair_context
            if not context:
                raise RuntimeError('Generate a diagnostic report before requesting a focused repair prompt.')
            plan_item = next(
                (item for item in context.get("repair_plan", {}).get("items", [])
                 if item.get("plan_id") == plan_id),
                None,
            )
            if plan_item is None:
                raise ValueError(f"Repair plan item not found: {plan_id}")
            prompt = build_focused_repair_prompt(context, plan_id)
            schedule = deepcopy(self.schedule)
            preserved_prompt_paths = {
                item.get("prompt_path")
                for item in schedule.get("investigation_history", [])
                if isinstance(item, dict) and isinstance(item.get("prompt_path"), str)
            }
            prompt_path = await write_focused_repair_prompt(
                self.hass, plan_id, prompt, preserved_paths=preserved_prompt_paths
            )
            schedule["investigation_history"] = record_investigation(
                schedule.get("investigation_history", []),
                plan_item,
                prompt_path,
                datetime.now(timezone.utc).isoformat(),
            )
            await self.store.async_save(schedule)
            self.schedule = schedule
            try:
                await async_commit_focused_prompt(self.hass, prompt_path)
            except OSError:
                _LOGGER.exception("Focused prompt was saved, but its commit marker could not be removed")
        await self.async_request_refresh()
        return prompt_path

    async def async_set_investigation_status(self, plan_id, status):
        """Record the user's tracking status; this never changes the system."""
        async with self._state_lock:
            schedule = deepcopy(self.schedule)
            schedule["investigation_history"] = set_investigation_status(
                schedule.get("investigation_history", []),
                plan_id,
                status,
                datetime.now(timezone.utc).isoformat(),
            )
            await self.store.async_save(schedule)
            self.schedule = schedule
        await self.async_request_refresh()


def _is_due(value, now):
    if not value:
        return False
    try:
        return now >= datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return True
