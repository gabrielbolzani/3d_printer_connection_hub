from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_IP_ADDRESS

REDACT_CONFIG = {CONF_IP_ADDRESS}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    return {
        "config_entry": async_redact_data(entry.as_dict(), REDACT_CONFIG),
        "printer_data": coordinator.data,
    }
