"""Native Home Assistant selectors for focused repair investigations."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .focused_repair_prompt import build_repair_plan_options
from .investigation_history import VALID_STATUSES, build_investigation_options


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RepairPlanSelect(coordinator, entry, hass),
        InvestigationHistorySelect(coordinator, entry),
        InvestigationStatusSelect(coordinator, entry),
        EntityClassificationReviewSelect(coordinator, entry),
        ConfirmEntityClassificationReviewSelect(coordinator, entry),
        EntityClassificationValueSelect(coordinator, entry),
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