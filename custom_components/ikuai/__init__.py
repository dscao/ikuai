"""The iKuai integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .api import IkuaiAPI
from .const import (
    DOMAIN, 
    PLATFORMS, 
    CONF_PASS, 
    CONF_UPDATE_INTERVAL, 
    CONF_CUSTOM_SWITCHES,
    CONF_TRACKER_CONFIG
)
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
    hass.data[DOMAIN][CONF_CUSTOM_SWITCHES] = conf.get(CONF_CUSTOM_SWITCHES, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: IkuaiConfigEntry) -> bool:
    """Set up iKuai from a config entry."""
    
    # 1. 初始化 API
    api = IkuaiAPI(
        hass,
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        passwd_md5=entry.data.get("passwd"),
        passwd_base64=entry.data.get(CONF_PASS),
    )

    # 2. 初始化协调器
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

    # --- 核心更新：自动清理已移除的追踪实体 (幽灵清理) ---
    entity_registry = er.async_get(hass)
    
    # 获取当前配置中允许存在的 Tracker MAC 地址列表
    conf_trackers = entry.data.get(CONF_TRACKER_CONFIG, {})
    host = entry.data.get(CONF_HOST)
    
    # 生成当前合法的 Unique ID 集合，用于对比
    # 逻辑必须与 device_tracker.py 中的拼接规则完全一致
    valid_tracker_unique_ids = [
        f"{DOMAIN}_tracker_{mac.replace(':', '_')}_{host}"
        for mac in conf_trackers
    ]

    # 获取该集成下已注册的所有实体
    existing_entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    
    for ent in existing_entities:
        # 我们只清理设备追踪平台 (device_tracker) 的实体
        if ent.domain == Platform.DEVICE_TRACKER:
            # 如果已注册的实体不在当前合法列表中，说明它已被用户移除
            if ent.unique_id not in valid_tracker_unique_ids:
                _LOGGER.info("检测到已移除的追踪配置，正在清理幽灵实体: %s", ent.entity_id)
                entity_registry.async_remove(ent.entity_id)
    # --------------------------------------------------

    # 3. 设置平台
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def update_listener(hass: HomeAssistant, entry: IkuaiConfigEntry) -> None:
    """监听选项更新."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: IkuaiConfigEntry) -> bool:
    """卸载集成."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)