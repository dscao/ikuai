"""IKUAI Entities"""
import logging
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import COORDINATOR, DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add bjtoon_health_code entities from a config_entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    sensors = []
    for sensor in SENSOR_TYPES:
        sensors.append(IKUAISensor(sensor, coordinator))

    async_add_entities(sensors, False)


class IKUAISensor(CoordinatorEntity):
    """Define an bjtoon_health_code entity."""

    def __init__(self, kind, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self.kind = kind
        self.coordinator = coordinator

    @property
    def name(self):
        """Return the name."""
        return f"{SENSOR_TYPES[self.kind]['name']}"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.kind}_{self.coordinator.host}"
        
    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }

    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return False

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def state(self):
        """Return the state."""
        return self.coordinator.data[self.kind]

    @property
    def icon(self):
        """Return the icon."""
        return SENSOR_TYPES[self.kind]["icon"]
        
    @property
    def unit_of_measurement(self):
        """Return the unit_of_measurement."""
        if SENSOR_TYPES[self.kind].get("unit_of_measurement"):
            return SENSOR_TYPES[self.kind]["unit_of_measurement"]
        
    @property
    def device_class(self):
        """Return the unit_of_measurement."""
        if SENSOR_TYPES[self.kind].get("device_class"):
            return SENSOR_TYPES[self.kind]["device_class"]
        
    @property
    def state_attributes(self): 
        attrs = {}
        data = self.coordinator.data
        if self.coordinator.data.get(self.kind + "_attrs"):
            attrs = self.coordinator.data[self.kind + "_attrs"]
        if data:            
            attrs["querytime"] = data["querytime"]        
        return attrs  

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update Bjtoon health code entity."""
        await self.coordinator.async_request_refresh()
