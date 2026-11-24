import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_NAME, DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES, DEFAULT_CLASSIFICATION_MISSING_GRACE_MINUTES, DOMAIN


class HealthManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title=user_input["name"], data={"name": user_input["name"]}
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("name", default=DEFAULT_NAME): str,
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HealthManagerOptionsFlow()


class HealthManagerOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Optional("weekly_reports", default=options.get("weekly_reports", True)): bool,
            vol.Optional("monthly_reviews", default=options.get("monthly_reviews", True)): bool,
            vol.Optional("include_core_log", default=options.get("include_core_log", True)): bool,
            vol.Optional("classification_review_notifications", default=options.get("classification_review_notifications", False)): bool,
            vol.Optional("classification_missing_grace_minutes", default=options.get("classification_missing_grace_minutes", DEFAULT_CLASSIFICATION_MISSING_GRACE_MINUTES)): vol.All(int, vol.Range(min=1, max=120)),
            vol.Optional("retention_days", default=options.get("retention_days", 90)): vol.All(int, vol.Range(min=7, max=365)),
            vol.Optional("unavailable_persistence_minutes", default=options.get("unavailable_persistence_minutes", DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES)): vol.All(int, vol.Range(min=5, max=1440)),
            vol.Optional("group_related_unavailable_entities", default=options.get("group_related_unavailable_entities", True)): bool,
            vol.Optional("unavailable_investigation_notifications", default=options.get("unavailable_investigation_notifications", True)): bool,
            vol.Optional("unavailable_investigation_reminder_days", default=options.get("unavailable_investigation_reminder_days", 7)): vol.All(int, vol.Range(min=1, max=30)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
