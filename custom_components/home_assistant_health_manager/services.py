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
            "path": path, "prompt_path": coordinator.last_prompt_path, "comprehensive": call.data.get("comprehensive", False)
        })

    async def generate_ai_repair_prompt(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        path = await coordinator.async_generate_report(call.data.get("comprehensive", False))
        await coordinator.async_request_refresh()
        hass.bus.async_fire(f"{DOMAIN}_ai_repair_prompt_created", {
            "report_path": path,
            "prompt_path": coordinator.last_prompt_path,
        })

    async def generate_focused_repair_prompt(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        plan_id = call.data["plan_id"]
        prompt_path = await coordinator.async_generate_focused_repair_prompt(plan_id)
        hass.bus.async_fire(f"{DOMAIN}_focused_repair_prompt_created", {
            "plan_id": plan_id,
            "prompt_path": prompt_path,
        })

    async def set_entity_classification_service(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        await coordinator.async_set_entity_classification(
            call.data["entity_id"],
            call.data["classification"],
            call.data["reason"],
            entity_domain=call.data.get("entity_domain"),
            source_domain=call.data.get("source_domain"),
            source_unique_id=call.data.get("source_unique_id"),
        )

    async def remove_entity_classification_service(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        await coordinator.async_remove_entity_classification(call.data["entity_id"])

    async def set_classification_review_interval_service(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        await coordinator.async_set_classification_review_interval(
            call.data["interval"]
        )

    async def review_entity_classifications_service(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        await coordinator.async_review_entity_classifications(call.data["entity_ids"])

    async def start_unavailable_investigation(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        investigation_id = await coordinator.async_start_manual_unavailable_investigation(
            call.data["entity_ids"]
        )
        hass.bus.async_fire(f"{DOMAIN}_unavailable_investigation_started", {
            "investigation_id": investigation_id,
            "entity_ids": call.data["entity_ids"],
        })

    async def set_unavailable_investigation_status(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        investigation_id = call.data["investigation_id"]
        status = call.data["status"]
        await coordinator.async_set_unavailable_investigation_status(
            investigation_id, status, call.data.get("user_note")
        )
        hass.bus.async_fire(f"{DOMAIN}_unavailable_investigation_updated", {
            "investigation_id": investigation_id,
            "status": status,
        })

    async def set_repair_investigation_status(call: ServiceCall):
        coordinator = _get_coordinator(hass)
        plan_id = call.data["plan_id"]
        status = call.data["status"]
        await coordinator.async_set_investigation_status(plan_id, status)
        hass.bus.async_fire(f"{DOMAIN}_repair_investigation_updated", {
            "plan_id": plan_id,
            "status": status,
        })

    schema = vol.Schema({vol.Optional("comprehensive", default=False): bool})
    focused_schema = vol.Schema({vol.Required("plan_id"): str})
    classification_schema = vol.Schema({
        vol.Required("entity_id"): str,
        vol.Required("classification"): vol.In([
            "actionable", "expected", "setup_in_progress", "seasonal"
        ]),
        vol.Required("reason"): str,
        vol.Optional("entity_domain"): str,
        vol.Optional("source_domain"): str,
        vol.Optional("source_unique_id"): str,
    })
    remove_classification_schema = vol.Schema({
        vol.Required("entity_id"): str,
    })
    review_interval_schema = vol.Schema({
        vol.Required("interval"): vol.In(["manual", "30", "60", "90"]),
    })
    review_classifications_schema = vol.Schema({
        vol.Required("entity_ids"): vol.All([str], vol.Length(min=1)),
    })
    start_unavailable_investigation_schema = vol.Schema({
        vol.Required("entity_ids"): vol.All([str], vol.Length(min=1)),
    })
    unavailable_investigation_status_schema = vol.Schema({
        vol.Required("investigation_id"): str,
        vol.Required("status"): vol.In(["needs_review", "investigating", "waiting", "resolved", "expected"]),
        vol.Optional("user_note"): str,
    })
    investigation_status_schema = vol.Schema({
        vol.Required("plan_id"): str,
        vol.Required("status"): vol.In(["prompt_generated", "in_progress", "resolved", "needs_follow_up", "dismissed"]),
    })
    hass.services.async_register(DOMAIN, "run_diagnostics", run_diagnostics, schema=schema)
    hass.services.async_register(DOMAIN, "generate_report", generate_report, schema=schema)
    hass.services.async_register(DOMAIN, "generate_ai_repair_prompt", generate_ai_repair_prompt, schema=schema)
    hass.services.async_register(DOMAIN, "generate_focused_repair_prompt", generate_focused_repair_prompt, schema=focused_schema)
    hass.services.async_register(DOMAIN, "set_repair_investigation_status", set_repair_investigation_status, schema=investigation_status_schema)
    hass.services.async_register(DOMAIN, "start_unavailable_investigation", start_unavailable_investigation, schema=start_unavailable_investigation_schema)
    hass.services.async_register(DOMAIN, "set_unavailable_investigation_status", set_unavailable_investigation_status, schema=unavailable_investigation_status_schema)
    hass.services.async_register(DOMAIN, "set_entity_classification", set_entity_classification_service, schema=classification_schema)
    hass.services.async_register(DOMAIN, "remove_entity_classification", remove_entity_classification_service, schema=remove_classification_schema)
    hass.services.async_register(DOMAIN, "set_classification_review_interval", set_classification_review_interval_service, schema=review_interval_schema)
    hass.services.async_register(DOMAIN, "review_entity_classifications", review_entity_classifications_service, schema=review_classifications_schema)


def _get_coordinator(hass):
    coordinators = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise RuntimeError("Health Manager is not loaded")
    return next(iter(coordinators.values()))
