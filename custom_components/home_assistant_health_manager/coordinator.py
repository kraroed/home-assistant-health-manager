import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .collector import collect_snapshot, read_core_log
from .compatibility import assess_compatibility
from .const import DOMAIN, SCHEDULE_INTERVAL, STORE_KEY, STORE_VERSION, UPDATE_INTERVAL, DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES
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
from .availability_storage import normalize_availability_data
from .availability_observer import observe_unavailable_entities
from .availability_grouping import build_unavailable_groups
from .availability_investigations import (
    start_investigation as start_unavailable_investigation,
    set_investigation_status as set_unavailable_investigation_status,
    summarize_investigations as summarize_unavailable_investigations,
    find_current_investigation,
)
from .entity_classifications import (
    normalize_classifications,
    set_entity_classification,
    remove_entity_classification,
    mark_entity_observations,
    set_review_interval,
    mark_classifications_reviewed,
)

_LOGGER = logging.getLogger(__name__)


class HealthManagerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORE_VERSION, STORE_KEY)
        # Keep user classifications isolated from diagnostic/report history.
        self.classification_store = Store(hass, 1, f'{DOMAIN}_entity_classifications')
        # Keep availability observations separate from reports and classifications.
        self.availability_store = Store(hass, 1, f'{DOMAIN}_availability_investigations')
        self.availability_data = normalize_availability_data({})
        self.availability_summary = {}
        self.entity_classifications = normalize_classifications({})
        self.schedule = {}
        self.last_report_path = None
        self.last_prompt_path = None
        self.last_repair_context = None
        self.selected_investigation_plan_id = None
        self.selected_entity_classification_id = None
        self.selected_entity_classification = None
        self.selected_entity_classification_reason = ""
        self.selected_unavailable_group_id = None
        self.selected_unavailable_investigation_id = None
        self.selected_manual_unavailable_entity_id = None
        self.selected_unavailable_investigation_note = ""
        self._schedule_unsub = None
        self._report_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self.hass.data[f"{DOMAIN}_retention_days"] = entry.options.get("retention_days", 90)

    async def async_setup_schedule(self):
        stored_data = await self.store.async_load()
        self.schedule = normalize_schedule_data(stored_data)
        stored_classifications = await self.classification_store.async_load()
        self.entity_classifications = normalize_classifications(stored_classifications)
        stored_availability = await self.availability_store.async_load()
        self.availability_data = normalize_availability_data(stored_availability)
        self.availability_summary = {
            "persistent_unavailable_entity_ids": [],
            "missing_tracked_entity_ids": [],
            "persistent_unavailable_entity_count": 0,
            "missing_tracked_entity_count": 0,
            "tracked_unavailable_entity_count": 0,
            "availability_observation_event_count": 0,
        }
        await async_reconcile_report_transactions(
            self.hass, self.schedule.get("last_report_path")
        )
        await async_reconcile_focused_prompt_transactions(
            self.hass, self.schedule.get("investigation_history", [])
        )
        if self.availability_data != stored_availability:
            await self.availability_store.async_save(self.availability_data)
        if self.entity_classifications != stored_classifications:
            await self.classification_store.async_save(self.entity_classifications)

        self.last_report_path = self.schedule.get("last_report_path")
        if self.last_report_path and self.last_report_path.endswith(".zip"):
            self.last_prompt_path = self.last_report_path[:-4] + "_ai_repair_prompt.md"
        await self.store.async_save(self.schedule)
        from homeassistant.helpers.event import async_track_time_interval
        self._schedule_unsub = async_track_time_interval(
            self.hass, self._async_scheduled_check, SCHEDULE_INTERVAL
        )

    async def async_set_entity_classification(
        self, entity_id, classification, reason, **metadata
    ):
        """Persist one explicit user classification independently of reports."""
        async with self._state_lock:
            updated = set_entity_classification(
                self.entity_classifications,
                entity_id,
                classification,
                reason,
                **metadata,
            )
            await self.classification_store.async_save(updated)
            self.entity_classifications = updated
        self.async_update_listeners()
        await self.async_notify_classification_reviews()

    async def async_remove_entity_classification(self, entity_id):
        """Remove only the explicitly selected entity classification."""
        async with self._state_lock:
            updated = remove_entity_classification(
                self.entity_classifications, entity_id
            )
            await self.classification_store.async_save(updated)
            self.entity_classifications = updated
        self.async_update_listeners()
        await self.async_notify_classification_reviews()

    async def async_set_classification_review_interval(self, interval):
        """Persist the user's classification review cadence."""
        async with self._state_lock:
            updated = set_review_interval(self.entity_classifications, interval)
            await self.classification_store.async_save(updated)
            self.entity_classifications = updated
        self.async_update_listeners()
        await self.async_notify_classification_reviews()

    async def async_review_entity_classifications(self, entity_ids):
        """Confirm selected classifications without changing their values."""
        async with self._state_lock:
            updated = mark_classifications_reviewed(
                self.entity_classifications, entity_ids
            )
            if updated != self.entity_classifications:
                await self.classification_store.async_save(updated)
                self.entity_classifications = updated
        self.async_update_listeners()
        await self.async_notify_classification_reviews()

    async def async_update_availability_observations(self, states):
        """Persist unavailable durations and distinguish missing from recovered."""
        entity_registry = er.async_get(self.hass)
        current_entities = []
        for state in states:
            registry_entry = entity_registry.async_get(state.entity_id)
            current_entities.append({
                "entity_id": state.entity_id,
                "state": state.state,
                "source_domain": getattr(registry_entry, "platform", None),
                "device_id": getattr(registry_entry, "device_id", None),
            })
        async with self._state_lock:
            updated = observe_unavailable_entities(
                self.availability_data,
                current_entities,
                datetime.now(timezone.utc).isoformat(),
                self.entry.options.get(
                    "unavailable_persistence_minutes",
                    DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES,
                ),
            )
            persisted = normalize_availability_data({
                "schema_version": updated["schema_version"],
                "observations": updated["observations"],
                "investigations": self.availability_data.get("investigations", {}),
                "events": updated["events"],
            })
            if persisted != self.availability_data:
                await self.availability_store.async_save(persisted)
                self.availability_data = persisted
            self.availability_summary = {
                "persistent_unavailable_entity_ids": updated["persistent_entity_ids"],
                "missing_tracked_entity_ids": updated["missing_entity_ids"],
                "persistent_unavailable_entity_count": len(updated["persistent_entity_ids"]),
                "missing_tracked_entity_count": len(updated["missing_entity_ids"]),
                "tracked_unavailable_entity_count": sum(
                    1 for record in self.availability_data["observations"].values()
                    if record.get("state") == "unavailable" and record.get("present") is True
                ),
                "availability_observation_event_count": len(self.availability_data["events"]),
            }

    async def async_update_classification_observations(self, states):
        """Record presence, registry source and availability for classified entities."""
        entity_registry = er.async_get(self.hass)
        present_ids = {state.entity_id for state in states}
        entity_sources = {}
        entity_states = {}
        for state in states:
            entity_states[state.entity_id] = state.state
            registry_entry = entity_registry.async_get(state.entity_id)
            if registry_entry is not None:
                entity_sources[state.entity_id] = {
                    "source_domain": registry_entry.platform,
                    "source_unique_id": registry_entry.unique_id,
                }
        async with self._state_lock:
            updated = mark_entity_observations(
                self.entity_classifications, present_ids,
                entity_sources=entity_sources, entity_states=entity_states,
            )
            if updated != self.entity_classifications:
                await self.classification_store.async_save(updated)
                self.entity_classifications = updated

    async def async_notify_classification_reviews(self):
        """Create one persistent notification per changed due-review set, when enabled."""
        from homeassistant.components import persistent_notification
        if not self.entry.options.get("classification_review_notifications", False):
            async with self._state_lock:
                if self.entity_classifications.get("last_review_notification_fingerprint") is not None:
                    updated = deepcopy(self.entity_classifications)
                    updated["last_review_notification_fingerprint"] = None
                    await self.classification_store.async_save(updated)
                    self.entity_classifications = updated
            persistent_notification.async_dismiss(
                self.hass, f"{DOMAIN}_classification_review_due"
            )
            return
        from .entity_classifications import get_review_due_entities
        due = get_review_due_entities(self.entity_classifications)
        notification_id = f"{DOMAIN}_classification_review_due"
        fingerprint = "|".join(due)
        async with self._state_lock:
            previous = self.entity_classifications.get("last_review_notification_fingerprint")
            if not due:
                if previous is not None:
                    updated = deepcopy(self.entity_classifications)
                    updated["last_review_notification_fingerprint"] = None
                    await self.classification_store.async_save(updated)
                    self.entity_classifications = updated
                    persistent_notification.async_dismiss(self.hass, notification_id)
                return
            if fingerprint == previous:
                return
            updated = deepcopy(self.entity_classifications)
            updated["last_review_notification_fingerprint"] = fingerprint
            await self.classification_store.async_save(updated)
            self.entity_classifications = updated
        names = "\n".join(f"- {entity_id}" for entity_id in due[:20])
        remainder = f"\n- Plus {len(due) - 20} more" if len(due) > 20 else ""
        persistent_notification.async_create(
            self.hass,
            f"{len(due)} saved entity classification(s) need review:\n\n{names}{remainder}\n\nOpen the Health Manager dashboard to inspect each classification and its reason.",
            title="Home Assistant Health Manager: classification review",
            notification_id=notification_id,
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
            await self.async_notify_classification_reviews()
        except Exception:
            _LOGGER.exception("Scheduled health review failed")

    async def _async_update_data(self):
        try:
            # Home Assistant's async state/config-entry APIs must stay on the
            # event loop; only blocking filesystem work belongs in the executor.
            current_states = list(self.hass.states.async_all())
            await self.async_update_classification_observations(current_states)
            await self.async_update_availability_observations(current_states)
            await self.async_notify_classification_reviews()
            snapshot = collect_snapshot(self.hass, self.entity_classifications)
            snapshot["collection_coverage"] = build_collection_coverage(snapshot)
            availability_groups = build_unavailable_groups(
                self.availability_data.get("observations", {}),
                snapshot.get("integration_inventory"),
                now=datetime.now(timezone.utc).isoformat(),
                group_related=self.entry.options.get("group_related_unavailable_entities", True),
                persistent_entity_ids=self.availability_summary.get("persistent_unavailable_entity_ids", []),
            )
            await self.async_notify_unavailable_investigations(availability_groups)
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
                "status": "attention" if snapshot["actionable_unavailable_entity_count"] or snapshot["actionable_unknown_entity_count"] or snapshot["failed_config_entry_count"] else "healthy",
                "active_issues": snapshot["actionable_unavailable_entity_count"] + snapshot["actionable_unknown_entity_count"] + snapshot["failed_config_entry_count"],
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
                **self.availability_summary,
                **summarize_unavailable_investigations(self.availability_data.get("investigations", {})),
                "unavailable_investigation_groups": availability_groups,
                "unavailable_investigation_group_count": len(availability_groups),
            }
        except Exception as err:
            raise UpdateFailed(f"Unable to collect diagnostics: {err}") from err

    async def async_generate_report(self, comprehensive=False, scheduled_period=None):
        """Serialize report generation so schedule history cannot race."""
        async with self._report_lock:
            current_states = list(self.hass.states.async_all())
            await self.async_update_classification_observations(current_states)
            await self.async_update_availability_observations(current_states)
            async with self._state_lock:
                return await self._async_generate_report_locked(comprehensive, scheduled_period)

    async def _async_generate_report_locked(self, comprehensive=False, scheduled_period=None):
        schedule = deepcopy(self.schedule)
        # A second interval callback may have queued while another scheduled
        # report held the locks. Re-check due state after acquiring them.
        if scheduled_period and not _is_due(schedule.get(scheduled_period), datetime.now(timezone.utc)):
            return None
        snapshot = collect_snapshot(self.hass, self.entity_classifications)
        snapshot["unavailable_investigation_groups"] = build_unavailable_groups(
            self.availability_data.get("observations", {}),
            snapshot.get("integration_inventory"),
            now=datetime.now(timezone.utc).isoformat(),
            group_related=self.entry.options.get("group_related_unavailable_entities", True),
            persistent_entity_ids=self.availability_summary.get("persistent_unavailable_entity_ids", []),
        )
        snapshot["unavailable_investigation_group_count"] = len(snapshot["unavailable_investigation_groups"])
        snapshot.update(summarize_unavailable_investigations(self.availability_data.get("investigations", {})))
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

    async def async_start_unavailable_investigation(self, group_id):
        """Start tracking one currently displayed persistent outage group."""
        groups = (self.data or {}).get("unavailable_investigation_groups", [])
        group = next(
            (item for item in groups if isinstance(item, dict) and item.get("group_id") == group_id),
            None,
        )
        if group is None:
            raise ValueError("That unavailable entity group is no longer available. Refresh diagnostics and select a current group.")
        return await self._async_create_unavailable_investigation(group)

    async def async_start_manual_unavailable_investigation(self, entity_ids):
        """Allow the user to investigate selected entities before the threshold."""
        if not isinstance(entity_ids, list) or not entity_ids:
            raise ValueError("Select at least one unavailable entity.")
        clean_ids = sorted(set(entity_id for entity_id in entity_ids if isinstance(entity_id, str)))
        if not clean_ids:
            raise ValueError("Select at least one valid entity ID.")
        for entity_id in clean_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != "unavailable":
                raise ValueError(f"{entity_id} is not currently unavailable.")
        fingerprint = hashlib.sha256("|".join(clean_ids).encode()).hexdigest()[:12]
        group = {
            "group_id": f"manual:{fingerprint}",
            "group_type": "manual",
            "title": f"Manually selected {len(clean_ids)} unavailable entit{'y' if len(clean_ids) == 1 else 'ies'}",
            "entity_ids": clean_ids,
            "confidence": "user_selected",
            "evidence": ["Manually selected by the user; the persistence threshold was intentionally bypassed."],
            "cause_confirmed": False,
            "requires_user_review": True,
        }
        return await self._async_create_unavailable_investigation(group)

    async def _async_create_unavailable_investigation(self, group):
        now = datetime.now(timezone.utc).isoformat()
        async with self._state_lock:
            investigations, investigation_id = start_unavailable_investigation(
                self.availability_data.get("investigations", {}),
                group,
                now,
            )
            updated = deepcopy(self.availability_data)
            updated["investigations"] = investigations
            updated.setdefault("events", []).append({
                "occurred_at": now,
                "action": "investigation_started",
                "entity_ids": list(group.get("entity_ids", [])),
            })
            updated = normalize_availability_data(updated)
            await self.availability_store.async_save(updated)
            self.availability_data = updated
            self.selected_unavailable_investigation_id = investigation_id
        self.async_update_listeners()
        await self.async_request_refresh()
        return investigation_id

    async def async_set_unavailable_investigation_status(self, investigation_id, status, user_note=None):
        """Save an explicit user status and reminder date for an investigation."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._state_lock:
            investigations = set_unavailable_investigation_status(
                self.availability_data.get("investigations", {}),
                investigation_id,
                status,
                now,
                reminder_days=self.entry.options.get("unavailable_investigation_reminder_days", 7),
                user_note=user_note,
            )
            updated = deepcopy(self.availability_data)
            updated["investigations"] = investigations
            record = investigations[investigation_id]
            updated.setdefault("events", []).append({
                "occurred_at": now,
                "action": f"investigation_status_{status}",
                "entity_ids": list(record.get("entity_ids", [])),
            })
            updated = normalize_availability_data(updated)
            await self.availability_store.async_save(updated)
            self.availability_data = updated
            self.selected_unavailable_investigation_id = investigation_id
        self.async_update_listeners()
        await self.async_request_refresh()

    async def async_notify_unavailable_investigations(self, groups):
        """Notify only for persistent groups needing review or a scheduled reminder."""
        from homeassistant.components import persistent_notification

        notification_id = f"{DOMAIN}_unavailable_investigations_due"
        enabled = self.entry.options.get("unavailable_investigation_notifications", True)
        now = datetime.now(timezone.utc)
        async with self._state_lock:
            updated = deepcopy(self.availability_data)
            if not enabled:
                if updated.get("last_notification_fingerprint") or updated.get("last_notification_at"):
                    updated.pop("last_notification_fingerprint", None)
                    updated.pop("last_notification_at", None)
                    await self.availability_store.async_save(updated)
                    self.availability_data = updated
                persistent_notification.async_dismiss(self.hass, notification_id)
                return

            investigations = updated.get("investigations", {})
            due_groups = []
            reminder_days = self.entry.options.get("unavailable_investigation_reminder_days", 7)
            try:
                reminder_days = min(30, max(1, int(reminder_days)))
            except (TypeError, ValueError):
                reminder_days = 7
            for group in groups:
                if not isinstance(group, dict):
                    continue
                record = find_current_investigation(investigations, group.get("group_id"))
                if not isinstance(record, dict):
                    due_groups.append(group)
                    continue
                current_entities = sorted(group.get("entity_ids", []))
                recorded_entities = sorted(record.get("entity_ids", []))
                current_reason = "; ".join(group.get("evidence", []))
                if current_entities != recorded_entities or current_reason != record.get("reason", ""):
                    due_groups.append(group)
                    continue
                status = record.get("status")
                if status == "needs_review":
                    due_groups.append(group)
                elif status == "waiting":
                    reminder_at = record.get("next_reminder_at")
                    try:
                        if reminder_at and now >= datetime.fromisoformat(reminder_at):
                            due_groups.append(group)
                    except (TypeError, ValueError):
                        due_groups.append(group)

            if not due_groups:
                if updated.get("last_notification_fingerprint") or updated.get("last_notification_at"):
                    updated.pop("last_notification_fingerprint", None)
                    updated.pop("last_notification_at", None)
                    await self.availability_store.async_save(updated)
                    self.availability_data = updated
                persistent_notification.async_dismiss(self.hass, notification_id)
                return

            fingerprint_data = [
                {
                    "group_id": group.get("group_id"),
                    "entity_ids": sorted(group.get("entity_ids", [])),
                    "evidence": sorted(group.get("evidence", [])),
                }
                for group in sorted(due_groups, key=lambda item: item.get("group_id", ""))
            ]
            fingerprint = json.dumps(fingerprint_data, sort_keys=True, separators=(",", ":"))
            previous = updated.get("last_notification_fingerprint")
            last_at = updated.get("last_notification_at")
            reminder_due = False
            if last_at:
                try:
                    reminder_due = now >= datetime.fromisoformat(last_at) + timedelta(days=reminder_days)
                except (TypeError, ValueError):
                    reminder_due = True
            if fingerprint == previous and not reminder_due:
                return
            updated["last_notification_fingerprint"] = fingerprint
            updated["last_notification_at"] = now.isoformat()
            await self.availability_store.async_save(updated)
            self.availability_data = updated

        lines = []
        for group in due_groups[:10]:
            lines.append(
                f"- {group.get('title', 'Unavailable entities')}: "
                f"{', '.join(group.get('entity_ids', []))}\n"
                f"  Evidence: {'; '.join(group.get('evidence', []))}"
            )
        remainder = f"\n- Plus {len(due_groups) - 10} more group(s)" if len(due_groups) > 10 else ""
        persistent_notification.async_create(
            self.hass,
            f"{len(due_groups)} persistent unavailable group(s) need your review. "
            "These are investigation leads, not confirmed root causes.\n\n"
            + "\n".join(lines) + remainder
            + "\n\nOpen the Health Manager dashboard to investigate or defer a group.",
            title="Home Assistant Health Manager: unavailable entities need review",
            notification_id=notification_id,
        )

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
