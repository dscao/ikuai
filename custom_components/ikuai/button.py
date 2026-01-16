"""IKUAI Entities"""
import logging
import asyncio

from homeassistant.components.button import (
    ButtonEntity,
)
from .const import (
    COORDINATOR, DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWD, CONF_PASS, BUTTON_TYPES
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up iKuai button entities from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    buttons = []
    for button in BUTTON_TYPES:
        buttons.append(IKUAIButton(hass, button, coordinator))

    async_add_entities(buttons, False)

class IKUAIButton(ButtonEntity):
    """Define an iKuai button entity."""
    _attr_has_entity_name = True

    def __init__(self, hass, kind, coordinator):
        """Initialize the button."""
        super().__init__()
        self.kind = kind
        self.coordinator = coordinator
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }
        self._name = BUTTON_TYPES[self.kind]['name']
        self._hass = hass

    @property
    def name(self):
        """Return the name of the button."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.kind}_{self.coordinator.host}"

    @property
    def device_class(self):
        """Return the device class of the button."""
        return BUTTON_TYPES[self.kind]['device_class']

    async def async_press(self):
        """Handle the button press to execute iKuai action."""
        await self.coordinator.async_control_device(BUTTON_TYPES[self.kind]['action_body'])
