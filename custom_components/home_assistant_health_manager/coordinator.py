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
from .report import write_report
from .repair_prompt import build_repair_prompt
from .repair_plan import build_repair_plan

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
        self._schedule_unsub = None
        self.hass.data[f"{DOMAIN}_retention_days"] = entry.options.get("retention_days", 90)

    async def async_setup_schedule(self):
        self.schedule = await self.store.async_load() or {}
        now = datetime.now(timezone.utc)
        self.schedule.setdefault("next_weekly", (now + timedelta(days=7)).isoformat())
        self.schedule.setdefault("next_monthly", (now + timedelta(days=30)).isoformat())
        self.schedule.setdefault("issue_history", {})
        self.schedule.setdefault("change_history", [])
        self.schedule.setdefault("trend_history", [])
        self.schedule.setdefault("integration_trend_history", [])
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
                await self.async_generate_report(comprehensive=True)
                self.schedule["next_monthly"] = (now + timedelta(days=30)).isoformat()
                await self.store.async_save(self.schedule)
            elif self.entry.options.get("weekly_reports", True) and _is_due(self.schedule.get("next_weekly"), now):
                await self.async_generate_report(comprehensive=False)
                self.schedule["next_weekly"] = (now + timedelta(days=7)).isoformat()
                await self.store.async_save(self.schedule)
            await self.async_request_refresh()
        except Exception:
            _LOGGER.exception("Scheduled health review failed")

    async def _async_update_data(self):
        try:
            # Home Assistant's async state/config-entry APIs must stay on the
            # event loop; only blocking filesystem work belongs in the executor.
            snapshot = collect_snapshot(self.hass)
            snapshot["collection_coverage"] = build_collection_coverage(snapshot)
            change_history, change_summary = update_change_history(self.schedule.get('change_history', []), snapshot, snapshot['collected_at'])
            if change_history != self.schedule.get('change_history', []):
                self.schedule['change_history'] = change_history
                await self.store.async_save(self.schedule)
            history_summary = summarize_issue_history(self.schedule.get("issue_history", {}))
            return {
                **snapshot,
                **history_summary,
                "status": "attention" if snapshot["unavailable_entity_count"] or snapshot["unknown_entity_count"] or snapshot["failed_config_entry_count"] else "healthy",
                "active_issues": snapshot["unavailable_entity_count"] + snapshot["unknown_entity_count"] + snapshot["failed_config_entry_count"],
                "last_assessment": self.schedule.get("last_assessment"),
                "last_report": self.schedule.get("last_report"),
                "report_count": self.schedule.get("report_count", 0),
                "last_report_path": self.last_report_path,
                "last_ai_repair_prompt_path": self.last_prompt_path,
                "compatibility_assessment": self.schedule.get("last_compatibility", {}),
                "diagnostic_change_history": change_summary,
                "diagnostic_trend": summarize_trends(self.schedule.get("trend_history", [])),
                "integration_trend_summary": summarize_integration_trends(self.schedule.get("integration_trend_history", [])),
            }
        except Exception as err:
            raise UpdateFailed(f"Unable to collect diagnostics: {err}") from err

    async def async_generate_report(self, comprehensive=False):
        snapshot = collect_snapshot(self.hass)
        change_history, change_summary = update_change_history(self.schedule.get('change_history', []), snapshot, snapshot['collected_at'])
        self.schedule['change_history'] = change_history
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
            self.schedule.get("trend_history", []), snapshot, analysis, compatibility, now.isoformat()
        )
        self.schedule["trend_history"] = trend_history
        snapshot["diagnostic_trend"] = trend_summary
        integration_trend_history, integration_trend_summary = update_integration_trend_history(
            self.schedule.get("integration_trend_history", []),
            snapshot.get("integration_inventory", {}),
            now.isoformat(),
        )
        self.schedule["integration_trend_history"] = integration_trend_history
        snapshot["integration_trend_summary"] = integration_trend_summary
        recommendations = build_recommendations(snapshot, analysis)
        recommendations = add_integration_trend_recommendations(recommendations, integration_trend_summary)
        self.schedule["issue_history"] = update_issue_history(
            self.schedule.get("issue_history", {}),
            recommendations,
            now.isoformat(),
        )
        history_summary = summarize_issue_history(self.schedule["issue_history"])
        recommendations = add_recurring_issue_recommendations(recommendations, history_summary)
        snapshot["issue_history_summary"] = history_summary
        snapshot["repair_plan"] = build_repair_plan(
            recommendations,
            analysis.get("integration_log_evidence", {}),
            integration_trend_summary,
        )
        safe_snapshot, snapshot_counts = redact_object(snapshot)
        safe_compatibility, _ = redact_object(compatibility)
        safe_recommendations, _ = redact_object(recommendations)
        repair_prompt = build_repair_prompt(safe_snapshot, analysis, safe_recommendations, now.isoformat(), safe_compatibility)
        path = await write_report(
            self.hass, safe_snapshot, analysis, sanitized_log,
            {"core_log": log_counts, "snapshot": snapshot_counts},
            recommendations, self.schedule["issue_history"], history_summary, repair_prompt, safe_compatibility, change_summary,
        )
        self.schedule["last_compatibility"] = safe_compatibility
        self.schedule["last_assessment"] = now.isoformat()
        self.schedule["last_report"] = now.isoformat()
        self.schedule["report_count"] = self.schedule.get("report_count", 0) + 1
        self.last_report_path = path
        self.last_prompt_path = path[:-4] + "_ai_repair_prompt.md" if path.endswith(".zip") else None
        await self.store.async_save(self.schedule)
        self.async_update_listeners()
        return path


def _is_due(value, now):
    if not value:
        return False
    try:
        return now >= datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return True
