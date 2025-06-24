"""IKUAI Entities"""
import logging
import time
import datetime
import json
import re
import requests
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError

from homeassistant.helpers.device_registry import DeviceEntryType

from homeassistant.components.device_tracker.config_entry import ScannerEntity

from .const import (
    COORDINATOR, 
    DOMAIN, 
    CONF_HOST, 
    ACTION_URL,
)

from .data_fetcher import DataFetcher

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add bjtoon_health_code entities from a config_entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    
    # Get device trackers configuration from hass.data
    device_trackers_config = hass.data[DOMAIN].get("device_trackers", {})

    device_trackers = []
    for device_tracker_key, device_tracker_config in device_trackers_config.items():
        device_trackers.append(IKUAITracker(hass, device_tracker_key, device_tracker_config, coordinator))
        _LOGGER.debug("Adding device tracker: %s", device_tracker_key)
    async_add_entities(device_trackers, False)


class IKUAITracker(ScannerEntity):
    """Define an bjtoon_health_code entity."""
    
    _attr_has_entity_name = True

    def __init__(self, hass, kind, device_config, coordinator):
        """Initialize."""
        super().__init__()
        self.kind = kind
        self.device_config = device_config
        self.coordinator = coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }
        self._attr_entity_registry_enabled_default = True
        self._hass = hass        
        self._is_connected = None
        self._attrs = {}
        self._querytime = ""
        

    @property
    def name(self):
        """Return the name."""
        return f"{self.device_config['name']}"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.kind}_{self.coordinator.host}"
        
    @property
    def icon(self):
        """Return the icon."""
        return self.device_config.get("icon", "mdi:cellphone")
        
    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return True
        
    @property
    def device_info(self):
        """Return the device info."""
        return self._attr_device_info

    @property
    def source_type(self):
        return "router"
        
    @property
    def is_connected(self):
        """Return the state."""
        return self._is_connected

    @property
    def extra_state_attributes(self):
        """Return device state attributes."""
        attrs = {}
        if self._attrs:
            attrs = self._attrs
        #attrs["querytime"] = self._querytime        
        return attrs       

    

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update entity."""
        #await self.coordinator.async_request_refresh()        

        listtracker = self.coordinator.data.get("tracker")
        self._is_connected = False
        self._attrs = {}
        self._querytime = self.coordinator.data["querytime"]
        
        if isinstance(listtracker, list):
            for tracker in listtracker:
                #_LOGGER.debug(tracker)
                if tracker["mac"] == self.device_config["mac_address"]:
                    _LOGGER.debug(tracker)
                    self._is_connected = True
                    self._attrs = tracker
                    self._querytime = self.coordinator.data["querytime"]


