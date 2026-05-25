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
    CONF_ACT_BUFFER,
)
from .helpers import extract_name_from_label

_LOGGER = logging.getLogger(__name__)

class IkuaiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理初次配置和重新配置."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理初次安装步骤."""
        errors = {}
        
        if user_input is not None:
            # 执行校验逻辑
            res = await self._async_test_and_prepare_data(user_input, errors)
            if res:
                # 如果是重新配置模式，更新现有条目并退出
                if self._reconfigure_entry:
                    return self.async_update_reload_and_abort(
                        self._reconfigure_entry, data=res
                    )
                
                # 初次安装，创建新条目
                await self.async_set_unique_id(f"ikuai-{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"iKuai ({user_input[CONF_HOST]})", 
                    data=res
                )

        # 默认值逻辑
        default_host = "http://10.10.10.1"
        default_user = "admin"
        if self._reconfigure_entry:
            default_host = self._reconfigure_entry.data.get(CONF_HOST)
            default_user = self._reconfigure_entry.data.get(CONF_USERNAME)

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=default_host): str,
                vol.Required(CONF_USERNAME, default=default_user): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理重新配置触发点."""
        self._reconfigure_entry = self._get_reconfigure_entry()
        return await self.async_step_user(user_input)

    async def _async_test_and_prepare_data(self, user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any] | None:
        """通用校验逻辑：加密密码并测试登录."""
        host = user_input[CONF_HOST]
        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]

        # 核心加密逻辑 (兼容 3.0/4.0)
        passwd_md5 = md5(password.encode()).hexdigest()
        passwd_base64 = base64.b64encode(f"salt_11{password}".encode()).decode()

        api = IkuaiAPI(
            self.hass,
            host=host,
            username=username,
            passwd_md5=passwd_md5,
            passwd_base64=passwd_base64
        )

        try:
            await api.login()
        except IkuaiAuthError:
            errors["base"] = "invalid_auth"
        except IkuaiConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during iKuai login")
            errors["base"] = "unknown"
        else:
            # 验证成功，组装保存的数据包
            new_data = {
                CONF_HOST: host,
                CONF_USERNAME: username,
                "passwd": passwd_md5,
                CONF_PASS: passwd_base64,
            }
            # 如果是重配，保留原有的 Tracker 配置
            if self._reconfigure_entry:
                new_data[CONF_TRACKER_CONFIG] = self._reconfigure_entry.data.get(CONF_TRACKER_CONFIG, {})
            return new_data
        
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> IkuaiOptionsFlowHandler:
        return IkuaiOptionsFlowHandler()


class IkuaiOptionsFlowHandler(config_entries.OptionsFlow):
    """处理 UI 动态设备选择 (保持不变，已支持扫描和添加)."""

    def __init__(self) -> None:
        """Initialize."""
        self._temp_devices: list[str] = []
        self._discovered_map: dict[str, str] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选项主菜单."""
        if user_input is not None:
            if user_input.get("action") == "scan":
                return await self.async_step_scan()
            return self.async_create_entry(title="", data=user_input)

        # 获取当前值，注意从 options 获取，没用则从 data 获取
        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, self.config_entry.data.get(CONF_UPDATE_INTERVAL, 10)
        )
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="save"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "save", "label": "仅保存基础设置"},
                            {"value": "scan", "label": "扫描并添加终端追踪"}
                        ],
                        mode="list"
                    )
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): int,
            })
        )

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """从路由器实时扫描在线设备."""
        errors = {}
        coordinator = self.config_entry.runtime_data
        
        if user_input is not None:
            self._temp_devices = user_input.get("devices", [])
            if not self._temp_devices:
                errors["base"] = "no_devices_selected"
            else:
                return await self.async_step_configure_devices()

        try:
            lan_list = await coordinator.api.get_lan_devices()
            self._discovered_map = {}
            # 过滤掉已经存在的设备，只显示新设备
            existing_trackers = self.config_entry.data.get(CONF_TRACKER_CONFIG, {})
            
            for item in lan_list:
                mac = item.get("mac", "").lower()
                if not mac or mac in existing_trackers:
                    continue
                ip = item.get("ip_addr", "")
                comment = extract_name_from_label(item.get("comment", ""))
                label = f"{ip} - {comment}" if comment else ip
                self._discovered_map[mac] = f"{mac} ({label})"
        except Exception:
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema({
                vol.Optional("devices"): cv.multi_select(self._discovered_map)
            }),
            errors=errors
        )

    async def async_step_configure_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """为选中的每个设备设置名称和缓冲."""
        if user_input is not None:
            # 必须从 data 获取当前配置
            current_config = dict(self.config_entry.data.get(CONF_TRACKER_CONFIG, {}))
            
            for mac in self._temp_devices:
                safe_key = mac.replace(":", "_")
                current_config[mac] = {
                    "name": user_input.get(f"name_{safe_key}"),
                    "buffer": user_input.get(f"buffer_{safe_key}", 2),
                    "type": "mac"
                }
            
            # 更新持久化数据
            new_data = {**self.config_entry.data, CONF_TRACKER_CONFIG: current_config}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            
            return self.async_create_entry(title="", data=self.config_entry.options)

        fields = {}
        for mac in self._temp_devices:
            safe_key = mac.replace(":", "_")
            label = self._discovered_map.get(mac, mac)
            default_name = extract_name_from_label(label) or f"Device {mac[-5:]}"
            
            fields[vol.Required(f"name_{safe_key}", default=default_name)] = str
            fields[vol.Optional(f"buffer_{safe_key}", default=2)] = int

        return self.async_show_form(
            step_id="configure_devices",
            data_schema=vol.Schema(fields),
            description_placeholders={"count": str(len(self._temp_devices))}
        )