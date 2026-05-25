"""The iKuai integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from .api import IkuaiAPI
from .const import DOMAIN, PLATFORMS, CONF_PASS, CONF_UPDATE_INTERVAL, CONF_CUSTOM_SWITCHES
from .coordinator import IKUAIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# 定义 YAML Schema 以支持原有的自定义开关功能
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

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_CUSTOM_SWITCHES, default={}): vol.Schema({
            cv.string: CUSTOM_SWITCH_SCHEMA
        })
    })
}, extra=vol.ALLOW_EXTRA)

type IkuaiConfigEntry = ConfigEntry[IKUAIDataUpdateCoordinator]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the iKuai component from YAML."""
    hass.data.setdefault(DOMAIN, {})
    conf = config.get(DOMAIN, {})
    # 存储 YAML 定义的自定义开关
    hass.data[DOMAIN][CONF_CUSTOM_SWITCHES] = conf.get(CONF_CUSTOM_SWITCHES, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: IkuaiConfigEntry) -> bool:
    """Set up iKuai from a config entry."""
    api = IkuaiAPI(
        hass,
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        passwd_md5=entry.data.get("passwd"),
        passwd_base64=entry.data.get(CONF_PASS),
    )

    # 获取 YAML 中的自定义开关并传入协调器
    yaml_custom_switches = hass.data.get(DOMAIN, {}).get(CONF_CUSTOM_SWITCHES, {})

    coordinator = IKUAIDataUpdateCoordinator(
        hass,
        api,
        host=entry.data[CONF_HOST],
        update_interval=entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 10)),
    )
    coordinator.yaml_custom_switches = yaml_custom_switches
    
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def update_listener(hass: HomeAssistant, entry: IkuaiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: IkuaiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)