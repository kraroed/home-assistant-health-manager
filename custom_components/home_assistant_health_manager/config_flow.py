import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_NAME, DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES, DOMAIN


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
            vol.Optional("retention_days", default=options.get("retention_days", 90)): vol.All(int, vol.Range(min=7, max=365)),
            vol.Optional("unavailable_persistence_minutes", default=options.get("unavailable_persistence_minutes", DEFAULT_UNAVAILABLE_PERSISTENCE_MINUTES)): vol.All(int, vol.Range(min=5, max=1440)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
