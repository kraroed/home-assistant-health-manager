"""Native text control for entity classification explanations."""

from homeassistant.components.text import TextEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EntityClassificationReasonText(coordinator, entry)])


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
