from __future__ import annotations

import logging
import base64
from hashlib import md5
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import IkuaiAPI, IkuaiAuthError, IkuaiConnectionError
from .const import (
    DOMAIN,
    CONF_PASS,
    CONF_UPDATE_INTERVAL,
    CONF_TRACKER_CONFIG,
)
from .helpers import extract_name_from_label

_LOGGER = logging.getLogger(__name__)

class IkuaiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理初次配置和重新配置."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理初次安装步骤."""
        errors = {}
        if user_input is not None:
            # 校验并加密数据
            data, error = await self._async_verify_and_create_data(user_input)
            if data:
                await self.async_set_unique_id(f"ikuai-{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"iKuai ({user_input[CONF_HOST]})", 
                    data=data
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="http://10.10.10.1"): str,
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理重新配置步骤 (修改 IP/密码)."""
        errors = {}
        # 获取当前正在重配的 Entry
        reconfigure_entry = self._get_reconfigure_entry()
        
        if user_input is not None:
            # 校验并加密数据
            data, error = await self._async_verify_and_create_data(user_input)
            if data:
                # 保持原有的 Tracker 配置不被覆盖
                new_data = {
                    **data,
                    CONF_TRACKER_CONFIG: reconfigure_entry.data.get(CONF_TRACKER_CONFIG, {})
                }
                # 更新条目并自动重启集成
                return self.async_update_reload_and_abort(
                    reconfigure_entry, 
                    data=new_data,
                    reason="reconfigure_successful"
                )
            errors["base"] = error

        # 预填当前配置的值
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=reconfigure_entry.data[CONF_HOST]): str,
                vol.Required(CONF_USERNAME, default=reconfigure_entry.data[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    async def _async_verify_and_create_data(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """验证认证信息并生成加密后的存储数据."""
        host = user_input[CONF_HOST]
        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]

        # 核心加密逻辑 (包含 salt_11)
        passwd_md5 = md5(password.encode()).hexdigest()
        passwd_base64 = base64.b64encode(f"salt_11{password}".encode()).decode()

        api = IkuaiAPI(self.hass, host, username, passwd_md5, passwd_base64)
        try:
            await api.login()
        except IkuaiAuthError:
            return None, "invalid_auth"
        except IkuaiConnectionError:
            return None, "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error")
            return None, "unknown"

        return {
            CONF_HOST: host,
            CONF_USERNAME: username,
            "passwd": passwd_md5,
            CONF_PASS: passwd_base64,
        }, None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> IkuaiOptionsFlowHandler:
        return IkuaiOptionsFlowHandler(config_entry)

class IkuaiOptionsFlowHandler(config_entries.OptionsFlow):
    """处理 UI 动态配置，包含添加和移除功能."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        # 关键修复：不要直接给 self.config_entry 赋值，改用私有变量名 self._config_entry
        self._config_entry = config_entry
        self._temp_devices: list[str] = []
        self._discovered_map: dict[str, str] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选项主菜单."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "scan":
                return await self.async_step_scan()
            if action == "remove":
                return await self.async_step_remove()
            
            # 仅保存基础设置
            return self.async_create_entry(title="", data=user_input)

        # 所有的 self.config_entry 改为 self._config_entry
        current_interval = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL, self._config_entry.data.get(CONF_UPDATE_INTERVAL, 10)
        )
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="save"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "save", "label": "仅保存基础设置"},
                            {"value": "scan", "label": "扫描并添加终端追踪"},
                            {"value": "remove", "label": "移除已存在的终端追踪"}
                        ],
                        mode="list"
                    )
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): int,
            })
        )

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """扫描并按格式显示设备: MAC | IP (备注)."""
        errors = {}
        # 使用 self._config_entry 获取协调器
        coordinator = self._config_entry.runtime_data
        
        if user_input is not None:
            self._temp_devices = user_input.get("devices", [])
            if not self._temp_devices:
                errors["base"] = "no_devices_selected"
            else:
                return await self.async_step_configure_devices()

        try:
            lan_list = await coordinator.api.get_lan_devices()
            self._discovered_map = {}
            existing_trackers = self._config_entry.data.get(CONF_TRACKER_CONFIG, {})
            
            for item in lan_list:
                mac = item.get("mac", "").lower()
                if not mac or mac in existing_trackers:
                    continue
                
                ip = item.get("ip_addr", "")
                
                # 同样的 3.0/4.0 兼容取名逻辑
                c = extract_name_from_label(item.get("comment", ""))
                t = item.get("termname", "")
                d = item.get("client_device", "")
                h = item.get("hostname", "")
                
                name = c or t or d or h
                display_label = None
                if name:
                    display_label = f"{mac} | {ip} ({name})"
                else:
                    display_label = f"{mac} | {ip}"
                    
                self._discovered_map[mac] = display_label
        except Exception:
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema({
                vol.Optional("devices"): cv.multi_select(self._discovered_map)
            }),
            errors=errors
        )

    async def async_step_remove(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """移除追踪配置并物理删除实体注册表项."""
        if user_input is not None:
            to_remove = user_input.get("devices", [])
            current_config = dict(self._config_entry.data.get(CONF_TRACKER_CONFIG, {}))
            
            ent_reg = er.async_get(self.hass)
            
            # 获取当前配置的主机地址 (必须与 coordinator.host 来源一致)
            host = self._config_entry.data.get(CONF_HOST)

            for mac in to_remove:
                if mac in current_config:
                    # --- 必须与 device_tracker.py 里的拼接逻辑完全一致 ---
                    # 1. 这里的 mac 对应 device_tracker 里的 target_id
                    # 2. replace(':', '_') 必须保留
                    # 3. 最后必须加上 host
                    safe_id = mac.replace(":", "_")
                    unique_id = f"{DOMAIN}_tracker_{safe_id}_{host}"
                    
                    # 查找该实体在 HA 数据库中的 ID
                    entity_id = ent_reg.async_get_entity_id("device_tracker", DOMAIN, unique_id)
                    
                    if entity_id:
                        _LOGGER.debug("正在从注册表中抹除实体: %s", entity_id)
                        ent_reg.async_remove(entity_id)
                    
                    # 从配置数据中删除
                    del current_config[mac]
            
            # 保存更新后的配置
            new_data = {**self._config_entry.data, CONF_TRACKER_CONFIG: current_config}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            
            # 立即重启集成生效
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return self.async_create_entry(title="", data=self._config_entry.options)

        # 展示当前可移除设备列表的逻辑保持不变
        current_config = self._config_entry.data.get(CONF_TRACKER_CONFIG, {})
        remove_options = {}
        for mac, info in current_config.items():
            remove_options[mac] = f"{mac} | {info.get('name', 'Unknown')}"

        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema({
                vol.Required("devices"): cv.multi_select(remove_options)
            })
        )
    
    async def async_step_configure_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """为新增设备设置显示名称."""
        if user_input is not None:
            current_config = dict(self._config_entry.data.get(CONF_TRACKER_CONFIG, {}))
            for mac in self._temp_devices:
                safe_key = mac.replace(":", "_")
                current_config[mac] = {
                    "name": user_input.get(f"name_{safe_key}"),
                    "buffer": user_input.get(f"buffer_{safe_key}", 2),
                    "type": "mac"
                }
            
            new_data = {**self._config_entry.data, CONF_TRACKER_CONFIG: current_config}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            
            return self.async_create_entry(title="", data=self._config_entry.options)

        fields = {}
        for mac in self._temp_devices:
            safe_key = mac.replace(":", "_")
            label = self._discovered_map.get(mac, "")
            default_name = ""
            if "(" in label:
                default_name = label.split("(")[-1].strip(")")
            
            fields[vol.Required(f"name_{safe_key}", default=default_name or f"Device {mac[-5:]}")] = str
            fields[vol.Optional(f"buffer_{safe_key}", default=2)] = int

        return self.async_show_form(
            step_id="configure_devices",
            data_schema=vol.Schema(fields)
        )