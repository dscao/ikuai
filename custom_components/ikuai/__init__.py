"""The ikuai integration."""
from __future__ import annotations
from async_timeout import timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from .data_fetcher import DataFetcher
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWD,
    CONF_PASS,
    CONF_HOST,    
    CONF_UPDATE_INTERVAL,
    COORDINATOR,
    UNDO_UPDATE_LISTENER,
    CONF_DEVICE_TRACKERS,
    CONF_CUSTOM_SWITCHES,
)
from homeassistant.exceptions import ConfigEntryNotReady

import time
import datetime
import logging
import asyncio


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH, Platform.DEVICE_TRACKER]

# Configuration schema for device trackers
DEVICE_TRACKER_SCHEMA = vol.Schema({
    vol.Optional("label"): cv.string,
    vol.Required("name"): cv.string,
    vol.Required("mac_address"): cv.string,
    vol.Optional("icon", default="mdi:cellphone"): cv.string,
    vol.Optional("disconnect_refresh_times", default=2): cv.positive_int,
})

# Configuration schema for custom switches
CUSTOM_SWITCH_SCHEMA = vol.Schema({
    vol.Required("label"): cv.string,
    vol.Required("name"): cv.string,
    vol.Optional("icon", default="mdi:toggle-switch"): cv.string,
    vol.Required("turn_on_body"): dict,
    vol.Required("turn_off_body"): dict,
    vol.Optional("show_body"): dict,
    vol.Optional("show_on"): dict,
    vol.Optional("show_off"): dict,
})

# Configuration schema for the domain
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_DEVICE_TRACKERS, default={}): vol.Schema({
            cv.string: DEVICE_TRACKER_SCHEMA
        }),
        vol.Optional(CONF_CUSTOM_SWITCHES, default={}): vol.Schema({
            cv.string: CUSTOM_SWITCH_SCHEMA
        })
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up configured ikuai."""
    hass.data.setdefault(DOMAIN, {})
    
    # Get device trackers configuration from configuration.yaml
    conf = config.get(DOMAIN, {})
    device_trackers_config = conf.get(CONF_DEVICE_TRACKERS, {})
    custom_switches_config = conf.get(CONF_CUSTOM_SWITCHES, {})
    
    if device_trackers_config:
        _LOGGER.info("Loaded %d device trackers from configuration.yaml", len(device_trackers_config))
    else:
        _LOGGER.info("No device trackers configured in configuration.yaml. Device tracking will be disabled.")
    
    if custom_switches_config:
        _LOGGER.info("Loaded %d custom switches from configuration.yaml", len(custom_switches_config))
    else:
        _LOGGER.info("No custom switches configured in configuration.yaml.")
    
    # Store the configurations in hass.data
    hass.data[DOMAIN]["device_trackers"] = device_trackers_config
    hass.data[DOMAIN]["custom_switches"] = custom_switches_config
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ikuai from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    passwd = entry.data[CONF_PASSWD]
    pas = entry.data[CONF_PASS]
    update_interval_seconds = entry.options.get(CONF_UPDATE_INTERVAL, 10)
    
    # Get configurations
    device_trackers_config = hass.data[DOMAIN].get("device_trackers", {})
    custom_switches_config = hass.data[DOMAIN].get("custom_switches", {})
    
    coordinator = IKUAIDataUpdateCoordinator(hass, host, username, passwd, pas, update_interval_seconds, device_trackers_config, custom_switches_config)
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    undo_listener = entry.add_update_listener(update_listener)

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    # for component in PLATFORMS:
        # hass.async_create_task(
            # hass.config_entries.async_forward_entry_setup(entry, component)
        # )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
    

async def update_listener(hass, entry):
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


class IKUAIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching IKUAI data."""

    def __init__(self, hass, host, username, passwd, pas, update_interval_seconds, device_trackers_config=None, custom_switches_config=None):
        """Initialize."""
        update_interval = datetime.timedelta(seconds=update_interval_seconds)
        _LOGGER.debug("%s Data will be update every %s", host, update_interval)
        self._token = ""
        self._token_expire_time = 0
        self._allow_login = True
    
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

        self._fetcher = DataFetcher(hass, host, username, passwd, pas, device_trackers_config, custom_switches_config)
        self.host = host
        
    async def get_access_token(self):
        if time.time() < self._token_expire_time:
            return self._token
        else:
            if self._allow_login == True:
                self._token = await self._fetcher._login_ikuai()
                if self._token == 10001:
                    self._allow_login = False
                self._token_expire_time = time.time() + 60*60*2          
                return self._token
            else:
                _LOGGER.error("The username or password has been incorrect, please reconfigure the ikuai integration.")
                return

    async def _async_update_data(self):
        """Update data via DataFetcher."""
        _LOGGER.debug("token_expire_time=%s", self._token_expire_time)
        if self._allow_login == True:
        
            sess_key = await self.get_access_token()
            _LOGGER.debug(sess_key) 

            try:
                async with timeout(10):
                    data = await self._fetcher.get_data(sess_key)
                    if data == 401:
                        self._token_expire_time = 0
                        return
                    if not data:
                        raise UpdateFailed("failed in getting data")
                    return data
            except Exception as error:
                raise UpdateFailed(error) from error
