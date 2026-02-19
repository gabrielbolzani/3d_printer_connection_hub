from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        ElegooStatusSensor(coordinator, entry),
        ElegooProgressSensor(coordinator, entry),
        ElegooLayerSensor(coordinator, entry),
        ElegooFilenameSensor(coordinator, entry),
        ElegooTimeSensor(coordinator, entry),
        ElegooFinishTimeSensor(coordinator, entry),
    ]
    
    async_add_entities(entities)

class ElegooSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Elegoo sensors."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Elegoo",
            "model": "Saturn 3 Ultra",
            "sw_version": self.coordinator.data.get("firmware"),
        }

class ElegooStatusSensor(ElegooSensorBase):
    """Sensor for printer status."""
    _attr_name = "Status"
    _attr_unique_id = "status"

    @property
    def native_value(self):
        return self.coordinator.data.get("status")

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_status"

class ElegooProgressSensor(ElegooSensorBase):
    """Sensor for print progress."""
    _attr_name = "Progresso"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:percent"
    _attr_state_class = "measurement"

    @property
    def native_value(self):
        return self.coordinator.data.get("progress")

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_progress"

class ElegooLayerSensor(ElegooSensorBase):
    """Sensor for current layer."""
    _attr_name = "Camada Atual"
    _attr_icon = "mdi:layers"

    @property
    def native_value(self):
        curr = self.coordinator.data.get("current_layer")
        total = self.coordinator.data.get("total_layers")
        if total == 0:
            return "N/A"
        return f"{curr}/{total}"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_layer"

class ElegooFilenameSensor(ElegooSensorBase):
    """Sensor for printing file name."""
    _attr_name = "Arquivo"
    _attr_icon = "mdi:file-3d"

    @property
    def native_value(self):
        val = self.coordinator.data.get("filename")
        return val if val else "Nenhum"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_filename"

class ElegooTimeSensor(ElegooSensorBase):
    """Sensor for remaining time."""
    _attr_name = "Tempo Restante"
    _attr_icon = "mdi:timer-sand"

    @property
    def native_value(self):
        return self.coordinator.data.get("remaining_time")

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_remaining_time"

class ElegooFinishTimeSensor(ElegooSensorBase):
    """Sensor for estimated finish time."""
    _attr_name = "Previsão de Término"
    _attr_icon = "mdi:clock-check"

    @property
    def native_value(self):
        return self.coordinator.data.get("finish_time")

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_finish_time"
