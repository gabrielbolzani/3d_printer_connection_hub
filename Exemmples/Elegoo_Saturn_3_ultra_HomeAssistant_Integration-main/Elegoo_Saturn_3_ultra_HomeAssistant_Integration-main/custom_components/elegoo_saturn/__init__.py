import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from datetime import timedelta

from .const import DOMAIN, CONF_IP_ADDRESS
from .client import ElegooClient

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elegoo Saturn from a config entry."""
    ip = entry.data[CONF_IP_ADDRESS]
    client = ElegooClient(ip)

    async def async_update_data():
        """Fetch data from the printer."""
        # Using async_add_executor_job because ElegooClient uses blocking sockets
        data = await hass.async_add_executor_job(client.get_data)
        if data is None:
            raise UpdateFailed(f"Erro ao comunicar com a impressora no IP {ip}")
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Elegoo Saturn Printer",
        update_method=async_update_data,
        update_interval=timedelta(seconds=10),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
