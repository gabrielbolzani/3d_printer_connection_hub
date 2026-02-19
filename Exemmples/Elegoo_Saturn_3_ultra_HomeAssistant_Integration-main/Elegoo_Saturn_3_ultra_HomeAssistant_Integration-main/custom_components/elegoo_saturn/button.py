from homeassistant.components.button import ButtonEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Pass both coordinator and the entry to the buttons
    entities = [
        ElegooPauseButton(coordinator, entry),
        ElegooResumeButton(coordinator, entry),
        ElegooStopButton(coordinator, entry),
    ]
    
    async_add_entities(entities)

class ElegooButtonBase(ButtonEntity):
    """Base class for Elegoo buttons."""
    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Elegoo",
            "model": "Saturn 3 Ultra",
        }

class ElegooPauseButton(ElegooButtonBase):
    """Button to pause the print."""
    _attr_name = "Pausar Impressão"
    _attr_icon = "mdi:pause"

    async def async_press(self):
        """Handle the button press."""
        # Using the client directly from the coordinator's update method context isn't ideal, 
        # but for buttons we can use the same client logic.
        from .client import ElegooClient
        client = ElegooClient(self._entry.data["ip_address"])
        await self.hass.async_add_executor_job(client.pause)
        await self.coordinator.async_request_refresh()

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_pause"

class ElegooResumeButton(ElegooButtonBase):
    """Button to resume the print."""
    _attr_name = "Retomar Impressão"
    _attr_icon = "mdi:play"

    async def async_press(self):
        """Handle the button press."""
        from .client import ElegooClient
        client = ElegooClient(self._entry.data["ip_address"])
        await self.hass.async_add_executor_job(client.resume)
        await self.coordinator.async_request_refresh()

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_resume"

class ElegooStopButton(ElegooButtonBase):
    """Button to stop the print."""
    _attr_name = "Parar Impressão"
    _attr_icon = "mdi:stop"

    async def async_press(self):
        """Handle the button press."""
        from .client import ElegooClient
        client = ElegooClient(self._entry.data["ip_address"])
        await self.hass.async_add_executor_job(client.stop)
        await self.coordinator.async_request_refresh()

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_stop"
