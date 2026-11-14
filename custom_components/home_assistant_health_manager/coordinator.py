from datetime import datetime, timedelta, timezone
import logging

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .collector import collect_snapshot, read_core_log
from .const import DOMAIN, SCHEDULE_INTERVAL, STORE_KEY, STORE_VERSION, UPDATE_INTERVAL
from .log_analyzer import analyze_log
from .recommendations import build_recommendations
from .redactor import redact_object, redact_text
from .report import write_report

_LOGGER = logging.getLogger(__name__)


class HealthManagerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORE_VERSION, STORE_KEY)
        self.schedule = {}
        self.last_report_path = None
        self._schedule_unsub = None
        self.hass.data[f"{DOMAIN}_retention_days"] = entry.options.get("retention_days", 90)

    async def async_setup_schedule(self):
        self.schedule = await self.store.async_load() or {}
        now = datetime.now(timezone.utc)
        self.schedule.setdefault("next_weekly", (now + timedelta(days=7)).isoformat())
        self.schedule.setdefault("next_monthly", (now + timedelta(days=30)).isoformat())
        await self.store.async_save(self.schedule)
        from homeassistant.helpers.event import async_track_time_interval
        self._schedule_unsub = async_track_time_interval(
            self.hass, self._async_scheduled_check, SCHEDULE_INTERVAL
        )

    async def async_shutdown(self):
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
            snapshot = await self.hass.async_add_executor_job(collect_snapshot, self.hass)
            return {
                **snapshot,
                "status": "attention" if snapshot["unavailable_entity_count"] or snapshot["failed_config_entry_count"] else "healthy",
                "active_issues": snapshot["unavailable_entity_count"] + snapshot["failed_config_entry_count"],
                "last_assessment": self.schedule.get("last_assessment"),
                "last_report": self.schedule.get("last_report"),
                "report_count": self.schedule.get("report_count", 0),
                "last_report_path": self.last_report_path,
            }
        except Exception as err:
            raise UpdateFailed(f"Unable to collect diagnostics: {err}") from err

    async def async_generate_report(self, comprehensive=False):
        snapshot = await self.hass.async_add_executor_job(collect_snapshot, self.hass)
        raw_log, log_error = (None, None)
        if self.entry.options.get("include_core_log", True):
            max_bytes = 5_000_000 if comprehensive else 1_500_000
            raw_log, log_error = await self.hass.async_add_executor_job(read_core_log, self.hass, max_bytes)
        sanitized_log, log_counts = redact_text(raw_log) if raw_log else (None, {})
        safe_snapshot, snapshot_counts = redact_object(snapshot)
        analysis = analyze_log(sanitized_log)
        if log_error:
            analysis["collection_note"] = log_error
        analysis["assessment_type"] = "monthly_comprehensive" if comprehensive else "weekly_diagnostic"
        recommendations = build_recommendations(snapshot, analysis)
        path = await write_report(
            self.hass, safe_snapshot, analysis, sanitized_log,
            {"core_log": log_counts, "snapshot": snapshot_counts}, recommendations
        )
        now = datetime.now(timezone.utc)
        self.schedule["last_assessment"] = now.isoformat()
        self.schedule["last_report"] = now.isoformat()
        self.schedule["report_count"] = self.schedule.get("report_count", 0) + 1
        self.last_report_path = path
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
