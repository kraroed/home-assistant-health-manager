"""Native text control for entity classification explanations."""

from homeassistant.components.text import TextEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EntityClassificationTargetText(coordinator, entry),
        EntityClassificationReasonText(coordinator, entry),
        UnavailableInvestigationEntityText(coordinator, entry),
        UnavailableInvestigationNoteText(coordinator, entry),
    ])


class EntityClassificationReasonText(CoordinatorEntity, TextEntity):
    """Edit the required explanation before applying a classification."""

    _attr_has_entity_name = True
    _attr_name = "Entity Classification Reason"
    _attr_icon = "mdi:text-box-edit-outline"
    _attr_native_min = 1
    _attr_native_max = 500

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_entity_classification_reason"

    @property
    def native_value(self):
        return getattr(self.coordinator, "selected_entity_classification_reason", "")

    async def async_set_value(self, value):
        self.coordinator.selected_entity_classification_reason = value.strip()
        self.coordinator.async_update_listeners()


class EntityClassificationTargetText(CoordinatorEntity, TextEntity):
    """Enter any existing entity ID to classify or edit."""

    _attr_has_entity_name = True
    _attr_name = "Entity IDs to Classify (comma-separated)"
    _attr_icon = "mdi:form-textbox"
    _attr_native_min = 3
    _attr_native_max = 255

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_entity_classification_target"

    @property
    def native_value(self):
        entity_ids = getattr(self.coordinator, "selected_entity_classification_ids", None)
        if entity_ids:
            return ", ".join(entity_ids)
        return getattr(self.coordinator, "selected_entity_classification_id", "") or ""

    async def async_set_value(self, value):
        entity_ids = list(dict.fromkeys(
            item.strip()
            for item in value.replace(",", "\n").splitlines()
            if item.strip()
        ))
        if not entity_ids:
            raise ValueError("Enter at least one Home Assistant entity ID.")
        registry = er.async_get(self.hass)
        for entity_id in entity_ids:
            if "." not in entity_id or " " in entity_id:
                raise ValueError(f"Invalid Home Assistant entity ID: {entity_id}")
            if self.hass.states.get(entity_id) is None and registry.async_get(entity_id) is None:
                raise ValueError(f"Entity not found in Home Assistant: {entity_id}")
        selected_id = entity_ids[0]
        record = self.coordinator.entity_classifications.get("entities", {}).get(selected_id, {})
        self.coordinator.selected_entity_classification_ids = entity_ids
        self.coordinator.selected_entity_classification_id = selected_id
        self.coordinator.selected_entity_classification = record.get("classification", "actionable")
        self.coordinator.selected_entity_classification_reason = record.get("reason", "")
        self.coordinator.async_update_listeners()


class UnavailableInvestigationEntityText(CoordinatorEntity, TextEntity):
    """Select one currently unavailable entity for immediate manual review."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Entity to Investigate"
    _attr_icon = "mdi:alert-box-outline"
    _attr_native_min = 3
    _attr_native_max = 255

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_entity_to_investigate"

    @property
    def native_value(self):
        return self.coordinator.selected_manual_unavailable_entity_id or ""

    async def async_set_value(self, value):
        entity_id = value.strip()
        state = self.hass.states.get(entity_id)
        if state is None or state.state != "unavailable":
            raise ValueError("Enter an entity ID that is currently unavailable.")
        self.coordinator.selected_manual_unavailable_entity_id = entity_id
        self.coordinator.async_update_listeners()


class UnavailableInvestigationNoteText(CoordinatorEntity, TextEntity):
    """Edit a user note for the selected unavailable investigation."""

    _attr_has_entity_name = True
    _attr_name = "Unavailable Investigation Note"
    _attr_icon = "mdi:text-box-edit-outline"
    _attr_native_min = 0
    _attr_native_max = 1000

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unavailable_investigation_note"

    @property
    def native_value(self):
        return self.coordinator.selected_unavailable_investigation_note

    async def async_set_value(self, value):
        self.coordinator.selected_unavailable_investigation_note = value.strip()
        self.coordinator.async_update_listeners()
