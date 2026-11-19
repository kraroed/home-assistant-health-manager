from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import HealthManagerCoordinator
from .services import async_setup_services


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = HealthManagerCoordinator(hass, entry)
    entry.async_on_unload(coordinator.async_shutdown)
    await coordinator.async_setup_schedule()
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, "run_diagnostics")
        hass.services.async_remove(DOMAIN, "generate_report")
        hass.services.async_remove(DOMAIN, "generate_ai_repair_prompt")
        hass.services.async_remove(DOMAIN, "generate_focused_repair_prompt")
        hass.services.async_remove(DOMAIN, "set_repair_investigation_status")
        hass.services.async_remove(DOMAIN, "set_entity_classification")
        hass.services.async_remove(DOMAIN, "remove_entity_classification")
        hass.services.async_remove(DOMAIN, "set_classification_review_interval")
    return unloaded
