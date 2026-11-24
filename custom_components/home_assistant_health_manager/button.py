"""Explicit action buttons for entity classification management."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ApplyEntityClassificationButton(coordinator, entry),
        RemoveEntityClassificationButton(coordinator, entry),
        StartUnavailableInvestigationButton(coordinator, entry),
        StartManualUnavailableInvestigationButton(coordinator, entry),
    ])


class ApplyEntityClassificationButton(CoordinatorEntity, ButtonEntity):
    """Apply the selected classification and user-provided reason."""

    _attr_has_entity_name = True
    _attr_name = "Apply Entity Classification"
    _attr_icon = "mdi:check-bold"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_apply_entity_classification"

    async def async_press(self):
        entity_id = getattr(self.coordinator, "selected_entity_classification_id", None)
        classification = getattr(self.coordinator, "selected_entity_classification", None)
        reason = getattr(self.coordinator, "selected_entity_classification_reason", "")
        if not entity_id:
            raise ValueError("Choose an entity classification record first.")
        if classification not in {"actionable", "expected", "setup_in_progress", "seasonal"}:
            raise ValueError("Choose a valid classification first.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Enter a reason before applying the classification.")
        record = self.coordinator.entity_classifications.get("entities", {}).get(entity_id, {})
        await self.coordinator.async_set_entity_classification(
            entity_id, classification, reason,
            entity_domain=entity_id.split(".", 1)[0],
            source_domain=record.get("source_domain"),
            source_unique_id=record.get("source_unique_id"),
        )
        self.coordinator.selected_entity_classification_reason = reason.strip()


class RemoveEntityClassificationButton(CoordinatorEntity, ButtonEntity):
    """Remove only the selected saved classification after explicit confirmation."""

    _attr_has_entity_name = True
    _attr_name = "Remove Entity Classification"
    _attr_icon = "mdi:delete-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_remove_entity_classification"

    async def async_press(self):
        entity_id = getattr(self.coordinator, "selected_entity_classification_id", None)
        if not entity_id:
            raise ValueError("Choose an entity classification record first.")
        await self.coordinator.async_remove_entity_classification(entity_id)
        self.coordinator.selected_entity_classification_id = None
        self.coordinator.selected_entity_classification_reason = ""
        self.coordinator.async_update_listeners()


class StartUnavailableInvestigationButton(CoordinatorEntity, ButtonEntity):
    """Start tracking the selected persistent unavailable group."""

    _attr_has_entity_name = True
    _attr_name = "Start Unavailable Investigation"
    _attr_icon = "mdi:clipboard-alert-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_start_unavailable_investigation"

    async def async_press(self):
        group_id = self.coordinator.selected_unavailable_group_id
        if not group_id:
            raise ValueError("Choose an unavailable group first.")
        await self.coordinator.async_start_unavailable_investigation(group_id)


class StartManualUnavailableInvestigationButton(CoordinatorEntity, ButtonEntity):
    """Start an immediate investigation for one manually selected entity."""

    _attr_has_entity_name = True
    _attr_name = "Start Manual Unavailable Investigation"
    _attr_icon = "mdi:clipboard-plus-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_start_manual_unavailable_investigation"

    async def async_press(self):
        entity_id = self.coordinator.selected_manual_unavailable_entity_id
        if not entity_id:
            raise ValueError("Enter an unavailable entity ID first.")
        investigation_id = await self.coordinator.async_start_manual_unavailable_investigation([entity_id])
        self.coordinator.selected_unavailable_investigation_id = investigation_id
