import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_MACHINE_NAME, CONF_IP_ADDRESS

class ElegooSaturnConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elegoo Saturn."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Here we could validate the IP address or try to connect to the printer
            return self.async_create_entry(
                title=user_input[CONF_MACHINE_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MACHINE_NAME): cv.string,
                    vol.Required(CONF_IP_ADDRESS): cv.string,
                }
            ),
            errors=errors,
        )
