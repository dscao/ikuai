"""DataUpdateCoordinator for iKuai integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceInfo

from .api import IkuaiAPI, IkuaiAuthError
from .const import DOMAIN, CONF_TRACKER_CONFIG, CONF_ACT_BUFFER, SWITCH_TYPES

_LOGGER = logging.getLogger(__name__)

class IKUAIDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """管理 iKuai 数据更新的核心类."""

    config_entry: ConfigEntry

    def __init__(
        self, 
        hass: HomeAssistant, 
        api: IkuaiAPI, 
        host: str, 
        update_interval: int
    ) -> None:
        """初始化协调器."""
        super().__init__(
            hass, 
            _LOGGER, 
            name=f"{DOMAIN} ({host})",
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api
        self.host = host
        self._tracker_buffer_state: dict[str, int] = {}
        self.yaml_custom_switches = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """从 API 抓取并清洗数据."""
        try:
            results = await asyncio.gather(
                self.api.get_system_status(),
                self.api.get_wan_info(),
                self.api.get_lan_devices(),
                self.api.get_mac_acl(),
                self.api.get_ipv6_lan(),
                self.api.get_ipv6_wan(),
                self.api.get_wan_vlan(),
                return_exceptions=True
            )

            status, wan, lan_list, mac_acl, ipv6_lan, ipv6_wan, vlan_data = results

            # 异常检查
            for res in results:
                if isinstance(res, Exception):
                    if isinstance(res, IkuaiAuthError):
                        raise ConfigEntryAuthFailed from res
                    raise res

            processed_data: dict[str, Any] = {}
            
            # --- 安全提取基础数据块 ---
            sysstat = (status or {}).get("sysstat", {})
            ac_status = (status or {}).get("ac_status", {})
            stream = sysstat.get("stream", {})
            memory = sysstat.get("memory", {})
            
            def get_safe_value(data, key, index=0, default=0):
                val_list = data.get(key)
                if isinstance(val_list, list) and len(val_list) > index:
                    raw_val = str(val_list[index]).replace("%", "").strip()
                    try:
                        return float(raw_val) if "." in raw_val else int(raw_val)
                    except ValueError:
                        return raw_val
                return default

            # --- 1. 基础状态 ---
            processed_data["ikuai_cpu"] = get_safe_value(sysstat, "cpu", 0)
            processed_data["ikuai_cputemp"] = get_safe_value(sysstat, "cputemp", 0)
            processed_data["ikuai_uptime"] = sysstat.get("uptime", 0)
            processed_data["ikuai_memory"] = str(memory.get("used", "0")).replace("%", "").strip()
            processed_data["ikuai_upload"] = round(stream.get("upload", 0) / 1024 / 1024, 3)
            processed_data["ikuai_download"] = round(stream.get("download", 0) / 1024 / 1024, 3)
            processed_data["ikuai_total_up"] = round(stream.get("total_up", 0) / 1024 / 1024 / 1024, 2)
            processed_data["ikuai_total_down"] = round(stream.get("total_down", 0) / 1024 / 1024 / 1024, 2)
            processed_data["ikuai_connect_num"] = stream.get("connect_num", 0)
            processed_data["ikuai_online_user"] = sysstat.get("online_user", {}).get("count", 0)
            processed_data["ikuai_ap_online"] = ac_status.get("ap_online", 0)
            processed_data["device_name"] = sysstat.get("hostname", "iKuai Router")
            processed_data["sw_version"] = sysstat.get("verinfo", {}).get("verstring", "Unknown")

            # --- 2. IP 处理 (重点改动) ---
            current_wan_ip = "Disconnected"
            processed_data["ikuai_wan_uptime"] = 0
            found_wan_item = None

            # 搜索 IPv4 逻辑
            if isinstance(wan, list):
                found_wan_item = next((i for i in wan if isinstance(i, dict) and i.get("default_route") == 1 and i.get("ip_addr")), None)
                if not found_wan_item:
                    found_wan_item = next((i for i in wan if isinstance(i, dict) and i.get("ip_addr")), None)

            if (not found_wan_item or not found_wan_item.get("ip_addr")) and isinstance(vlan_data, list):
                target_vlan = next((v for v in vlan_data if isinstance(v, dict) and v.get("default_route") == 1), None) or (vlan_data[0] if vlan_data else None)
                if target_vlan:
                    current_wan_ip = target_vlan.get("pppoe_ip_addr") or target_vlan.get("ip_addr") or "Disconnected"
                    v_uptime = target_vlan.get("pppoe_updatetime") or target_vlan.get("updatetime", 0)
                    if v_uptime > 0:
                        processed_data["ikuai_wan_uptime"] = int(time.time() - v_uptime)
            
            if found_wan_item and current_wan_ip == "Disconnected":
                current_wan_ip = found_wan_item.get("ip_addr", "Disconnected")
                up_time = found_wan_item.get("updatetime", 0)
                if up_time > 0:
                    processed_data["ikuai_wan_uptime"] = int(time.time() - up_time)

            processed_data["ikuai_ip"] = current_wan_ip

            # IPv6 提取 (不再作为独立传感器，仅提取值)
            lan6_ip = ipv6_lan[0].get("ipv6_addr", "Unknown") if (isinstance(ipv6_lan, list) and ipv6_lan) else "Unknown"
            wan6_ip = ipv6_wan[0].get("dhcp6_ip_addr", "Unknown") if (isinstance(ipv6_wan, list) and ipv6_wan) else "Unknown"

            # --- 3. 属性注入 ---
            # 合并 IPv6 到 ikuai_ip 的属性中
            ip_attrs = (found_wan_item if found_wan_item else {}).copy()
            ip_attrs.update({
                "wan_ipv6": wan6_ip,
                "lan_ipv6": lan6_ip,
                "query_time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            processed_data["ikuai_ip_attrs"] = ip_attrs

            # 其他属性
            processed_data["ikuai_memory_attrs"] = memory
            processed_data["ikuai_online_user_attrs"] = sysstat.get("online_user", {})
            processed_data["ikuai_ap_online_attrs"] = ac_status

            # --- 4. 开关状态 ---
            static_states = {
                "ikuai_arp_filter": "on" if sysstat.get("arp_filter") == 1 else "off",
                "ikuai_stream_control": "on" if sysstat.get("stream_ctl_mode") == 1 else "off"
            }
            processed_data["static_switches"] = static_states

            # --- 5. Device Tracker ---
            processed_data["tracker_map"] = {}
            online_lan_map = {item.get("mac", "").lower(): item for item in (lan_list if isinstance(lan_list, list) else []) if item.get("mac")}
            tracker_config = self.config_entry.data.get(CONF_TRACKER_CONFIG, {})
            global_buffer = self.config_entry.options.get(CONF_ACT_BUFFER, self.config_entry.data.get(CONF_ACT_BUFFER, 2))

            for target_id, config in tracker_config.items():
                target_lower = target_id.lower()
                if target_lower in online_lan_map:
                    processed_data["tracker_map"][target_id] = online_lan_map[target_lower]
                    self._tracker_buffer_state[target_id] = 0
                else:
                    curr_buf = self._tracker_buffer_state.get(target_id, 0)
                    max_buf = config.get("buffer") or global_buffer
                    if curr_buf < max_buf:
                        processed_data["tracker_map"][target_id] = {"offline_buffering": True}
                        self._tracker_buffer_state[target_id] = curr_buf + 1

            return processed_data

        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.exception("Critical error in iKuai data processing")
            raise UpdateFailed(f"iKuai communication error: {err}") from err

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.host)},
            name=self.data.get("device_name", "iKuai Router"),
            manufacturer="iKuai",
            model="iKuai Router",
            sw_version=self.data.get("sw_version"),
            configuration_url=f"http://{self.host}",
        )

    async def async_control_device(self, action_body: dict[str, Any]) -> None:
        try:
            await self.api.call_action(action_body)
            self.hass.async_create_task(self._async_delay_refresh())
        except Exception as err:
            _LOGGER.error("Failed to execute iKuai action: %s", err)

    async def _async_delay_refresh(self) -> None:
        await asyncio.sleep(1)
        await self.async_refresh()