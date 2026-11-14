import voluptuous as vol
from homeassistant.core import ServiceCall

from .const import DOMAIN


async def async_setup_services(hass):
    if hass.services.has_service(DOMAIN, "run_diagnostics"):
        return

    async def run_diagnostics(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        await coordinator.async_request_refresh()
        path = await coordinator.async_generate_report(call.data.get("comprehensive", False))
        await coordinator.async_request_refresh()
        hass.bus.async_fire(f"{DOMAIN}_report_created", {
            "path": path, "prompt_path": coordinator.last_prompt_path, "comprehensive": call.data.get("comprehensive", False)
        })

    async def generate_report(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        path = await coordinator.async_generate_report(call.data.get("comprehensive", False))
        await coordinator.async_request_refresh()
        hass.bus.async_fire(f"{DOMAIN}_report_created", {
            "path": path, "comprehensive": call.data.get("comprehensive", False)
        })

    async def generate_ai_repair_prompt(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        path = await coordinator.async_generate_report(call.data.get("comprehensive", False))
        await coordinator.async_request_refresh()
        hass.bus.async_fire(f"{DOMAIN}_ai_repair_prompt_created", {
            "report_path": path,
            "prompt_path": coordinator.last_prompt_path,
        })

    schema = vol.Schema({vol.Optional("comprehensive", default=False): bool})
    hass.services.async_register(DOMAIN, "run_diagnostics", run_diagnostics, schema=schema)
    hass.services.async_register(DOMAIN, "generate_report", generate_report, schema=schema)
    hass.services.async_register(DOMAIN, "generate_ai_repair_prompt", generate_ai_repair_prompt, schema=schema)


def _get_coordinator(hass):
    coordinators = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise RuntimeError("Health Manager is not loaded")
    return next(iter(coordinators.values()))
