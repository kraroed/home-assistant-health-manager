from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

SENSORS = [
    ("status", "Health Status", None, None),
    ("active_issues", "Active Issues", "issues", SensorStateClass.MEASUREMENT),
    ("unavailable_entity_count", "Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("unknown_entity_count", "Unknown Entities", "entities", SensorStateClass.MEASUREMENT),
    ("failed_config_entry_count", "Failed Integrations", "integrations", SensorStateClass.MEASUREMENT),
    ("config_entry_count", "Configured Integrations", "integrations", SensorStateClass.MEASUREMENT),
    ("tracked_issue_count", "Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("active_tracked_issue_count", "Active Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("resolved_tracked_issue_count", "Resolved Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("core_update_status", "Core Update", None, None),
    ("supervisor_update_status", "Supervisor Update", None, None),
    ("operating_system_update_status", "Operating System Update", None, None),
    ("compatibility_status", "Compatibility Status", None, None),
    ("report_count", "Generated Reports", "reports", SensorStateClass.TOTAL_INCREASING),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HealthManagerSensor(coordinator, entry, key, name, unit, state_class)
        for key, name, unit, state_class in SENSORS
    )


class HealthManagerSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, unit, state_class):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.key == "compatibility_status":
            return data.get("compatibility_assessment", {}).get("overall_status", "not_assessed")
        if self.key.endswith("_update_status"):
            platform = self.key.removesuffix("_update_status")
            update = data.get("platform_updates", {}).get(platform, {})
            if not update.get("entity_present"):
                return "not_detected"
            if update.get("update_available") is True:
                return "update_available"
            if update.get("state") == "off":
                return "up_to_date"
            return update.get("state", "unknown")
        return data.get(self.key)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        if self.key == "status":
            return {
                "last_assessment": data.get("last_assessment"),
                "last_report": data.get("last_report"),
                "last_ai_repair_prompt_path": data.get("last_ai_repair_prompt_path"),
                "report_count": data.get("report_count", 0),
                "home_assistant_version": data.get("home_assistant_version"),
                "platform_updates": data.get("platform_updates", {}),
                "update_entity_inventory": data.get("update_entity_inventory", {}),
                "compatibility_assessment": data.get("compatibility_assessment", {}),
                "entity_count": data.get("entity_count"),
                "unavailable_entity_count": data.get("unavailable_entity_count"),
                "unknown_entity_count": data.get("unknown_entity_count"),
                "failed_config_entry_count": data.get("failed_config_entry_count"),
                "failed_config_entry_domains": data.get("failed_config_entry_domains", {}),
                "config_entry_states": data.get("config_entry_states", {}),
                "integration_inventory": data.get("integration_inventory", {}),
                "unavailable_counts_by_domain": data.get("unavailable_counts_by_domain", {}),
                "unknown_counts_by_domain": data.get("unknown_counts_by_domain", {}),
            }
        if self.key.endswith("_update_status"):
            platform = self.key.removesuffix("_update_status")
            return data.get("platform_updates", {}).get(platform, {})
        return {}
