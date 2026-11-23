"""Native Home Assistant selectors for focused repair investigations."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .focused_repair_prompt import build_repair_plan_options
from .investigation_history import VALID_STATUSES, build_investigation_options
from .availability_investigations import VALID_STATUSES as UNAVAILABLE_INVESTIGATION_STATUSES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RepairPlanSelect(coordinator, entry, hass),
        InvestigationHistorySelect(coordinator, entry),
        InvestigationStatusSelect(coordinator, entry),
        EntityClassificationReviewSelect(coordinator, entry),
        ConfirmEntityClassificationReviewSelect(coordinator, entry),
        EntityClassificationValueSelect(coordinator, entry),
        ClassificationReviewIntervalSelect(coordinator, entry),
        UnavailableEntityGroupSelect(coordinator, entry),
        UnavailableInvestigationHistorySelect(coordinator, entry),
        UnavailableInvestigationStatusSelect(coordinator, entry),
        UnavailableInvestigationGroupSelect(coordinator, entry),
        UnavailableInvestigationHistorySelect(coordinator, entry),
        UnavailableInvestigationStatusSelect(coordinator, entry),
    ])


class RepairPlanSelect(CoordinatorEntity, SelectEntity):
    """Select one current repair item and create its focused prompt."""

    _attr_has_entity_name = True
    _attr_name = "Generate Focused Repair Prompt"
    _attr_icon = "mdi:message-text-outline"

    def __init__(self, coordinator, entry, hass):
        super().__init__(coordinator)
        self.hass = hass
        self._attr_unique_id = f"{entry.entry_id}_focused_repair_prompt"
        self._attr_current_option = None
        self._option_to_plan_id = {}
        self._last_prompt_path = None

    @property
    def options(self):
        if self.coordinator.last_repair_context is None:
            self._option_to_plan_id = {}
            return []
        items = (self.coordinator.data or {}).get("repair_plan", {}).get("items", [])
        self._option_to_plan_id = build_repair_plan_options(items)
        return list(self._option_to_plan_id)

    @property
    def current_option(self):
        return self._attr_current_option if self._attr_current_option in self.options else None

    @property
    def extra_state_attributes(self):
        return {
            "last_prompt_path": self._last_prompt_path,
            "selection_action": "Selecting an option immediately generates a local Markdown prompt; it does not change Home Assistant configuration.",
            "plan_item_count": len(self.options),
        }

    async def async_select_option(self, option):
        items = (self.coordinator.data or {}).get("repair_plan", {}).get("items", [])
        self._option_to_plan_id = build_repair_plan_options(items)
        plan_id = self._option_to_plan_id.get(option)
        if plan_id is None:
            raise ValueError("That repair-plan option is no longer available. Refresh diagnostics and select a current item.")
        prompt_path = await self.coordinator.async_generate_focused_repair_prompt(plan_id)
        self._last_prompt_path = prompt_path
        self._attr_current_option = option
        self.hass.bus.async_fire(f"{DOMAIN}_focused_repair_prompt_created", {
            "plan_id": plan_id,
            "prompt_path": prompt_path,
        })
        self.async_write_ha_state()


class InvestigationHistorySelect(CoordinatorEntity, SelectEntity):
    """Choose a previously generated investigation to update."""

    _attr_has_entity_name = True
    _attr_name = "Investigation to Update"
    _attr_icon = "mdi:clipboard-text-clock-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_investigation_to_update"
        self._option_to_plan_id = {}

    @property
    def options(self):
        history = (self.coordinator.data or {}).get("investigations", [])
        self._option_to_plan_id = build_investigation_options(history)
        return list(self._option_to_plan_id)

    @property
    def current_option(self):
        _ = self.options
        selected_id = getattr(self.coordinator, "selected_investigation_plan_id", None)
        return next(
            (label for label, plan_id in self._option_to_plan_id.items() if plan_id == selected_id),
            None,
        )

    @property
    def extra_state_attributes(self):
        selected_id = getattr(self.coordinator, "selected_investigation_plan_id", None)
        return {"selected_plan_id": selected_id}

    async def async_select_option(self, option):
        history = (self.coordinator.data or {}).get("investigations", [])
        self._option_to_plan_id = build_investigation_options(history)
        plan_id = self._option_to_plan_id.get(option)
        if plan_id is None:
            raise ValueError("That investigation is no longer in the retained history.")
        self.coordinator.selected_investigation_plan_id = plan_id
        self.coordinator.async_update_listeners()


class InvestigationStatusSelect(CoordinatorEntity, SelectEntity):
    """Set a tracking status for the selected investigation."""

    _attr_has_entity_name = True
    _attr_name = "Investigation Status"
    _attr_icon = "mdi:list-status"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_investigation_status"

    @property
    def options(self):
        return sorted(VALID_STATUSES)

    @property
    def current_option(self):
        selected_id = getattr(self.coordinator, "selected_investigation_plan_id", None)
        history = (self.coordinator.data or {}).get("investigations", [])
        record = next((item for item in history if item.get("plan_id") == selected_id), None)
        return record.get("status") if record else None

    @property
    def extra_state_attributes(self):
        selected_id = getattr(self.coordinator, "selected_investigation_plan_id", None)
        history = (self.coordinator.data or {}).get("investigations", [])
        selection_exists = any(
            item.get("plan_id") == selected_id
            for item in history
            if isinstance(item, dict)
        )
        return {
            "selected_plan_id": selected_id,
            "selection_required": not selection_exists,
            "selection_stale": selected_id is not None and not selection_exists,
            "note": "This changes only your local tracking label; it does not verify or perform a repair.",
        }

    async def async_select_option(self, option):
        if option not in VALID_STATUSES:
            raise ValueError("Unsupported investigation status.")
        plan_id = getattr(self.coordinator, "selected_investigation_plan_id", None)
        if not plan_id:
            raise ValueError("Choose an investigation in the Investigation to Update dropdown first.")
        await self.coordinator.async_set_investigation_status(plan_id, option)


class UnavailableInvestigationGroupSelect(CoordinatorEntity, SelectEntity):
    """Choose a persistent unavailable group to begin tracking."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Group to Investigate"
    _attr_icon = "mdi:alert-circle-check-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_group_to_investigate"
        self._option_to_group_id = {}

    @property
    def options(self):
        groups = (self.coordinator.data or {}).get("unavailable_investigation_groups", [])
        self._option_to_group_id = {
            f"{group.get('title', 'Unavailable entities')} — {group.get('group_id')}": group.get("group_id")
            for group in groups if isinstance(group, dict) and group.get("group_id")
        }
        return list(self._option_to_group_id)

    @property
    def current_option(self):
        _ = self.options
        selected = self.coordinator.selected_unavailable_group_id
        return next((label for label, group_id in self._option_to_group_id.items() if group_id == selected), None)

    @property
    def extra_state_attributes(self):
        selected = self.coordinator.selected_unavailable_group_id
        groups = (self.coordinator.data or {}).get("unavailable_investigation_groups", [])
        group = next((item for item in groups if item.get("group_id") == selected), None)
        return {
            "selected_group_id": selected,
            "selected_group": group,
            "note": "Only groups past the persistence threshold appear here. Use the manual investigation service to bypass the threshold for selected entities.",
        }

    async def async_select_option(self, option):
        _ = self.options
        group_id = self._option_to_group_id.get(option)
        if group_id is None:
            raise ValueError("That unavailable group is no longer available. Refresh diagnostics and select a current group.")
        self.coordinator.selected_unavailable_group_id = group_id
        self.coordinator.async_update_listeners()


class UnavailableInvestigationHistorySelect(CoordinatorEntity, SelectEntity):
    """Choose a saved unavailable investigation to update."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Investigation to Update"
    _attr_icon = "mdi:clipboard-text-clock-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_investigation_to_update"
        self._option_to_investigation_id = {}

    @property
    def options(self):
        records = (self.coordinator.data or {}).get("unavailable_investigations", [])
        self._option_to_investigation_id = {
            f"{item.get('status', 'needs_review')} — {item.get('title', 'Unavailable entities')} [{item.get('investigation_id')}]": item.get("investigation_id")
            for item in records if isinstance(item, dict) and item.get("investigation_id")
        }
        return list(self._option_to_investigation_id)

    @property
    def current_option(self):
        _ = self.options
        selected = self.coordinator.selected_unavailable_investigation_id
        return next(
            (label for label, investigation_id in self._option_to_investigation_id.items()
             if investigation_id == selected),
            None,
        )

    @property
    def extra_state_attributes(self):
        selected = self.coordinator.selected_unavailable_investigation_id
        records = (self.coordinator.data or {}).get("unavailable_investigations", [])
        record = next(
            (item for item in records if item.get("investigation_id") == selected),
            None,
        )
        return {
            "selected_investigation_id": selected,
            "selected_investigation": record,
            "selection_required": record is None,
        }

    async def async_select_option(self, option):
        _ = self.options
        investigation_id = self._option_to_investigation_id.get(option)
        if investigation_id is None:
            raise ValueError("That unavailable investigation is no longer in retained history.")
        self.coordinator.selected_unavailable_investigation_id = investigation_id
        record = next(
            item for item in (self.coordinator.data or {}).get("unavailable_investigations", [])
            if item.get("investigation_id") == investigation_id
        )
        self.coordinator.selected_unavailable_investigation_note = record.get("user_note", "")
        self.coordinator.async_update_listeners()


class UnavailableInvestigationStatusSelect(CoordinatorEntity, SelectEntity):
    """Set the user's status for the selected unavailable investigation."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Investigation Status"
    _attr_icon = "mdi:list-status"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_investigation_status"

    @property
    def options(self):
        return sorted(UNAVAILABLE_INVESTIGATION_STATUSES)

    @property
    def current_option(self):
        selected = self.coordinator.selected_unavailable_investigation_id
        records = (self.coordinator.data or {}).get("unavailable_investigations", [])
        record = next((item for item in records if item.get("investigation_id") == selected), None)
        return record.get("status") if record else None

    @property
    def extra_state_attributes(self):
        selected = self.coordinator.selected_unavailable_investigation_id
        records = (self.coordinator.data or {}).get("unavailable_investigations", [])
        record = next((item for item in records if item.get("investigation_id") == selected), None)
        return {
            "selected_investigation_id": selected,
            "selection_required": record is None,
            "next_reminder_at": record.get("next_reminder_at") if record else None,
            "note": "Waiting schedules a reminder. Resolved and Expected are user tracking decisions; neither suppresses entities or confirms a technical fix.",
        }

    async def async_select_option(self, option):
        if option not in UNAVAILABLE_INVESTIGATION_STATUSES:
            raise ValueError("Unsupported unavailable investigation status.")
        investigation_id = self.coordinator.selected_unavailable_investigation_id
        if not investigation_id:
            raise ValueError("Choose an unavailable investigation first.")
        await self.coordinator.async_set_unavailable_investigation_status(
            investigation_id,
            option,
            self.coordinator.selected_unavailable_investigation_note,
        )


class EntityClassificationReviewSelect(CoordinatorEntity, SelectEntity):
    """Select a saved entity classification and expose its full review context."""

    _attr_has_entity_name = True
    _attr_name = "Entity Classification to Review"
    _attr_icon = "mdi:clipboard-check-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_entity_classification_review"
        self._option_to_entity_id = {}

    @property
    def options(self):
        records = self.coordinator.entity_classifications.get("entities", {})
        self._option_to_entity_id = {
            f"{entity_id} — {record.get('classification', 'unknown')}": entity_id
            for entity_id, record in sorted(records.items())
            if isinstance(record, dict)
        }
        return list(self._option_to_entity_id)

    @property
    def current_option(self):
        _ = self.options
        selected = getattr(self.coordinator, "selected_entity_classification_id", None)
        return next((label for label, entity_id in self._option_to_entity_id.items() if entity_id == selected), None)

    @property
    def extra_state_attributes(self):
        selected = getattr(self.coordinator, "selected_entity_classification_id", None)
        record = self.coordinator.entity_classifications.get("entities", {}).get(selected, {})
        return {
            "selected_entity_id": selected,
            "classification": record.get("classification"),
            "reason": record.get("reason"),
            "review_due": record.get("review_due", False),
            "review_due_reason": record.get("review_due_reason"),
            "review_due_reasons": record.get("review_due_reasons", []),
            "last_reviewed": record.get("last_reviewed"),
            "entity_missing": record.get("entity_missing", False),
            "missing_since": record.get("missing_since"),
            "source_domain": record.get("source_domain"),
            "source_unique_id": record.get("source_unique_id"),
            "previous_source_domain": record.get("previous_source_domain"),
            "previous_source_unique_id": record.get("previous_source_unique_id"),
            "last_observed_state": record.get("last_observed_state"),
            "previous_observed_state": record.get("previous_observed_state"),
            "available_review_entities": self.coordinator.data.get("classification_review_due_entities", []) if self.coordinator.data else [],
            "note": "Selection is for inspection only. Use the explicit classification services to change or remove a record.",
        }

    async def async_select_option(self, option):
        self._option_to_entity_id = {
            f"{entity_id} — {record.get('classification', 'unknown')}": entity_id
            for entity_id, record in sorted(self.coordinator.entity_classifications.get("entities", {}).items())
            if isinstance(record, dict)
        }
        entity_id = self._option_to_entity_id.get(option)
        if entity_id is None:
            raise ValueError("That classification is no longer available.")
        self.coordinator.selected_entity_classification_id = entity_id
        record = self.coordinator.entity_classifications.get("entities", {}).get(entity_id, {})
        self.coordinator.selected_entity_classification = record.get("classification", "actionable")
        self.coordinator.selected_entity_classification_reason = record.get("reason", "")
        self.coordinator.async_update_listeners()


class EntityClassificationValueSelect(CoordinatorEntity, SelectEntity):
    """Choose the classification to apply to the selected entity."""

    _attr_has_entity_name = True
    _attr_name = "Entity Classification Value"
    _attr_icon = "mdi:tag-edit-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_entity_classification_value"

    @property
    def options(self):
        return ["actionable", "expected", "setup_in_progress", "seasonal"]

    @property
    def current_option(self):
        return getattr(self.coordinator, "selected_entity_classification", None)

    async def async_select_option(self, option):
        if option not in self.options:
            raise ValueError("Unsupported entity classification.")
        self.coordinator.selected_entity_classification = option
        self.coordinator.async_update_listeners()




class ClassificationReviewIntervalSelect(CoordinatorEntity, SelectEntity):
    """Configure periodic classification review cadence."""

    _attr_has_entity_name = True
    _attr_name = "Classification Review Interval"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_classification_review_interval"

    @property
    def options(self):
        return ["manual", "30", "60", "90"]

    @property
    def current_option(self):
        return self.coordinator.entity_classifications.get("review_interval", "90")

    async def async_select_option(self, option):
        if option not in self.options:
            raise ValueError("Unsupported classification review interval.")
        await self.coordinator.async_set_classification_review_interval(option)
class ConfirmEntityClassificationReviewSelect(CoordinatorEntity, SelectEntity):
    """Explicitly confirm the currently selected classification was reviewed."""

    _attr_has_entity_name = True
    _attr_name = "Confirm Entity Classification Review"
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_confirm_entity_classification_review"

    @property
    def options(self):
        selected = getattr(self.coordinator, "selected_entity_classification_id", None)
        return ["Confirm selected classification"] if selected in self.coordinator.entity_classifications.get("entities", {}) else []

    @property
    def current_option(self):
        return None

    @property
    def extra_state_attributes(self):
        return {"action": "Selecting the option records that you reviewed the selected classification; it does not change its classification or reason."}

    async def async_select_option(self, option):
        entity_id = getattr(self.coordinator, "selected_entity_classification_id", None)
        if option != "Confirm selected classification" or entity_id not in self.coordinator.entity_classifications.get("entities", {}):
            raise ValueError("Select a valid entity classification first.")
        await self.coordinator.async_review_entity_classifications([entity_id])

class UnavailableEntityGroupSelect(CoordinatorEntity, SelectEntity):
    """Start a user-tracked investigation for a persistent unavailable group."""

    _attr_has_entity_name = True
    _attr_name = "Start Unavailable Entity Investigation"
    _attr_icon = "mdi:clipboard-search-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_start_unavailable_entity_investigation"
        self._option_to_group_id = {}

    @property
    def options(self):
        groups = (self.coordinator.data or {}).get("unavailable_investigation_groups", [])
        self._option_to_group_id = {}
        for group in groups:
            if not isinstance(group, dict) or not group.get("group_id"):
                continue
            entity_ids = group.get("entity_ids", [])
            label = f"{group.get('title', 'Unavailable entities')} — {len(entity_ids)} entities"
            if label in self._option_to_group_id:
                label = f"{label} ({group['group_id'][-8:]})"
            self._option_to_group_id[label] = group["group_id"]
        return list(self._option_to_group_id)

    @property
    def current_option(self):
        return None

    @property
    def extra_state_attributes(self):
        return {
            "action": "Selecting a group starts local investigation tracking. It does not change entity states, classifications, or device configuration.",
            "group_count": len(self.options),
            "persistence_threshold_minutes": self.coordinator.entry.options.get("unavailable_persistence_minutes", 60),
        }

    async def async_select_option(self, option):
        group_id = self._option_to_group_id.get(option)
        if group_id is None:
            _ = self.options
            group_id = self._option_to_group_id.get(option)
        if group_id is None:
            raise ValueError("That unavailable group is no longer available. Refresh diagnostics and select a current group.")
        await self.coordinator.async_start_unavailable_investigation(group_id)


class UnavailableInvestigationHistorySelect(CoordinatorEntity, SelectEntity):
    """Select a saved unavailable-entity investigation for review or status updates."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Investigation to Update"
    _attr_icon = "mdi:clipboard-list-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_investigation_to_update"
        self._option_to_investigation_id = {}

    @property
    def options(self):
        records = (self.coordinator.data or {}).get("unavailable_investigations", [])
        self._option_to_investigation_id = {}
        for record in records:
            if not isinstance(record, dict) or not record.get("investigation_id"):
                continue
            label = f"{record.get('title', 'Unavailable entities')} — {record.get('status', 'needs_review')}"
            if label in self._option_to_investigation_id:
                label = f"{label} ({record['investigation_id'][-8:]})"
            self._option_to_investigation_id[label] = record["investigation_id"]
        return list(self._option_to_investigation_id)

    @property
    def current_option(self):
        _ = self.options
        selected = self.coordinator.selected_unavailable_investigation_id
        return next(
            (label for label, investigation_id in self._option_to_investigation_id.items() if investigation_id == selected),
            None,
        )

    @property
    def extra_state_attributes(self):
        selected_id = self.coordinator.selected_unavailable_investigation_id
        record = next(
            (
                item for item in (self.coordinator.data or {}).get("unavailable_investigations", [])
                if item.get("investigation_id") == selected_id
            ),
            {},
        )
        return {
            "selected_investigation_id": selected_id,
            "entity_ids": record.get("entity_ids", []),
            "reason": record.get("reason"),
            "evidence": record.get("evidence", []),
            "confidence": record.get("confidence"),
            "status": record.get("status"),
            "user_note": record.get("user_note"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "next_reminder_at": record.get("next_reminder_at"),
            "cause_confirmed": record.get("cause_confirmed", False),
            "note": "Investigation history is user-managed. A group is not a confirmed root cause.",
        }

    async def async_select_option(self, option):
        _ = self.options
        investigation_id = self._option_to_investigation_id.get(option)
        if investigation_id is None:
            raise ValueError("That unavailable investigation is no longer in the saved history.")
        self.coordinator.selected_unavailable_investigation_id = investigation_id
        self.coordinator.async_update_listeners()


class UnavailableInvestigationStatusSelect(CoordinatorEntity, SelectEntity):
    """Set the user's status for the selected unavailable investigation."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Investigation Status"
    _attr_icon = "mdi:list-status"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_investigation_status"

    @property
    def options(self):
        return ["needs_review", "investigating", "waiting", "resolved", "expected"]

    @property
    def current_option(self):
        selected_id = self.coordinator.selected_unavailable_investigation_id
        record = next((item for item in (self.coordinator.data or {}).get("unavailable_investigations", []) if item.get("investigation_id") == selected_id), {})
        return record.get("status") if record else None

    @property
    def extra_state_attributes(self):
        selected_id = self.coordinator.selected_unavailable_investigation_id
        record = next((item for item in (self.coordinator.data or {}).get("unavailable_investigations", []) if item.get("investigation_id") == selected_id), {})
        return {
            "selected_investigation_id": selected_id,
            "user_note": record.get("user_note"),
            "next_reminder_at": record.get("next_reminder_at"),
            "note": "This updates only your local investigation status; it never changes entity classifications or suppresses alerts.",
        }

    async def async_select_option(self, option):
        if option not in self.options:
            raise ValueError("Unsupported unavailable investigation status.")
        selected_id = self.coordinator.selected_unavailable_investigation_id
        if not selected_id:
            raise ValueError("Choose an unavailable investigation in the history selector first.")
        await self.coordinator.async_set_unavailable_investigation_status(selected_id, option)
