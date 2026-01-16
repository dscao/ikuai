"""IKUAI Entities"""
import logging
from homeassistant.util import slugify
from homeassistant.helpers import entity_registry as er
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.core import callback
from .const import (
    COORDINATOR, 
    DOMAIN, 
    CONF_TRACKER_CONFIG,
    CONF_SOURCE_MODE,
    MODE_CONST
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up iKuai device tracker entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    
    if config_entry.data.get(CONF_SOURCE_MODE) == MODE_CONST:
        try:
            from .const import DEVICE_TRACKERS
            tracker_config = {}
            for key, info in DEVICE_TRACKERS.items():
                target = info.get("mac_address") or info.get("ip_address")
                if target:
                    tracker_config[target] = {
                        "name": info.get("name", key),
                        "buffer": info.get("disconnect_refresh_times", 2),
                        "mac_address": info.get("mac_address"),
                        "ip_address": info.get("ip_address")
                    }
        except ImportError:
            _LOGGER.warning("DEVICE_TRACKERS not found in const.py")
            tracker_config = {}
    else:
        tracker_config = config_entry.data.get(CONF_TRACKER_CONFIG, {})

    device_trackers = []
    for target_id, info in tracker_config.items():
        device_trackers.append(IKUAITracker(hass, target_id, info, coordinator))
    
    async_add_entities(device_trackers, False)

class IKUAITracker(ScannerEntity):
    """Define an iKuai device tracker entity."""
    
    _attr_has_entity_name = True

    def __init__(self, hass, target_id, info, coordinator):
        """Initialize the tracker."""
        super().__init__()
        self._target_id = target_id
        self._info = info
        self.coordinator = coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"] if self.coordinator.data else "iKuai",
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data.get("sw_version") if self.coordinator.data else "Unknown",
        }
        self._attr_entity_registry_enabled_default = True
        self._hass = hass        
        self._is_connected = False 
        self._attrs = {}
        self._querytime = ""

        self._custom_name = self._info.get("name", self._target_id)
        
        router_name = "ikuai"
        if self.coordinator.data and self.coordinator.data.get("device_name"):
            router_name = slugify(self.coordinator.data["device_name"])
            
        if self._custom_name:
            name_part = slugify(self._custom_name)
            desired_entity_id = f"device_tracker.{router_name}_{name_part}"
        else:
            id_part = slugify(self._target_id)
            desired_entity_id = f"device_tracker.{router_name}_{id_part}"
        
        registry = er.async_get(hass)
        if not registry.async_is_registered(desired_entity_id):
            self.entity_id = desired_entity_id
            _LOGGER.debug("Set entity_id to %s", desired_entity_id)

    @property
    def name(self):
        """Return the name of the device."""
        return self._custom_name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self._target_id}_{self.coordinator.host}"
        
    @property
    def should_poll(self):
        """No polling needed for coordinator entities."""
        return False
    
    @property
    def available(self):
        """Return if entity is available based on coordinator existence."""
        return self.coordinator is not None
        
    @property
    def device_info(self):
        """Return device information."""
        return self._attr_device_info

    @property
    def source_type(self):
        """Return the source type."""
        return "router"
        
    @property
    def is_connected(self):
        """Return true if the device is connected to the network."""
        return self._is_connected

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        attrs = {}
        if self._attrs:
            attrs = self._attrs
        return attrs       

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self):
        """Update the connection state from coordinator data."""
        self._is_connected = False
        self._attrs = {}
        
        if not self.coordinator.data:
            return

        listtracker = self.coordinator.data.get("tracker", [])
        if self.coordinator.data.get("querytime"):
            self._querytime = self.coordinator.data["querytime"]
        
        if isinstance(listtracker, list):
            target_lower = str(self._target_id).lower()
            
            for tracker in listtracker:
                matched = False
                config_mac = self._info.get("mac_address", "").lower()
                tracker_mac = tracker.get("mac", "").lower()
                tracker_ip = tracker.get("ip_addr", "")
                
                if tracker_ip == self._target_id:
                    matched = True
                elif config_mac and tracker_mac == config_mac:
                    matched = True
                elif tracker_mac == target_lower:
                    matched = True
                
                if matched:
                    self._is_connected = True
                    self._attrs = tracker
                    break
