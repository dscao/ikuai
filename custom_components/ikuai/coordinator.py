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
from .helpers import extract_name_from_label

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
        """从 API 抓取数据，采用分段式请求以降低路由器压力."""
        try:
            # 第一阶段：抓取最核心的数据 (系统状态 + 终端列表)
            # 只有这两个成功，集成才有意义
            core_results = await asyncio.gather(
                self.api.get_system_status(), # 0
                self.api.get_lan_devices(),   # 1
                return_exceptions=True
            )

            # 核心数据容错
            status = core_results[0]
            lan_list = core_results[1]

            if isinstance(status, Exception) or isinstance(lan_list, Exception):
                if self.data:
                    _LOGGER.warning("核心数据抓取抖动，临时使用缓存数据")
                    return self.data
                raise UpdateFailed("无法连接到爱快核心服务")

            # 第二阶段：抓取次要数据 (分小批次，避免冲击路由器)
            # 2026 优化：不重要的信息如果失败，直接给空，不影响整体运行
            other_results = await asyncio.gather(
                self.api.get_wan_info(),                         # 0
                self.api.call_action(SWITCH_TYPES[0].show_body), # 1
                self.api.call_action(SWITCH_TYPES[1].show_body), # 2
                self.api.get_ipv6_lan(),                         # 3
                self.api.get_ipv6_wan(),                         # 4
                self.api.get_wan_vlan(),                         # 5
                self.api.get_mac_acl(),                          # 6
                return_exceptions=True
            )

            def get_other(index, default_val=None):
                res = other_results[index]
                return res if not isinstance(res, Exception) else default_val

            wan         = get_other(0, [])
            arp_res     = get_other(1, {})
            stream_res  = get_other(2, {})
            ipv6_lan    = get_other(3, [])
            ipv6_wan    = get_other(4, [])
            vlan_data   = get_other(5, [])
            mac_acl     = get_other(6, [])

            # --- 开始清洗数据 ---
            processed_data: dict[str, Any] = {}
            
            sysstat = status.get("sysstat", {})
            ac_status = status.get("ac_status", {})
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

            # 1. 基础信息
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

            # 2. IP 处理
            current_wan_ip = "Disconnected"
            processed_data["ikuai_wan_uptime"] = 0
            found_wan_item = None

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

            # IPv6 提取
            lan6_ip = ipv6_lan[0].get("ipv6_addr", "Unknown") if (isinstance(ipv6_lan, list) and ipv6_lan) else "Unknown"
            wan6_ip = ipv6_wan[0].get("dhcp6_ip_addr", "Unknown") if (isinstance(ipv6_wan, list) and ipv6_wan) else "Unknown"

            # 属性注入
            ip_attrs = (found_wan_item if found_wan_item else {}).copy()
            ip_attrs.update({"wan_ipv6": wan6_ip, "lan_ipv6": lan6_ip, "query_time": time.strftime("%Y-%m-%d %H:%M:%S")})
            processed_data["ikuai_ip_attrs"] = ip_attrs
            processed_data["ikuai_memory_attrs"] = memory
            processed_data["ikuai_online_user_attrs"] = sysstat.get("online_user", {})
            processed_data["ikuai_ap_online_attrs"] = ac_status

            # 3. 开关状态解析 (使用你提供的嵌套逻辑)
            static_states = {}
            def check_is_on(api_res, show_on_def):
                if not api_res or not isinstance(api_res, dict): return False
                for key, expected_val in show_on_def.items():
                    attr_list = api_res.get(key)
                    target_val = attr_list[0].get(key) if isinstance(attr_list, list) and attr_list else api_res.get(key)
                    if str(target_val) != str(expected_val): return False
                return True

            static_states["ikuai_arp_filter"] = "on" if check_is_on(arp_res, SWITCH_TYPES[0].show_on) else "off"
            static_states["ikuai_stream_control"] = "on" if check_is_on(stream_res, SWITCH_TYPES[1].show_on) else "off"
            processed_data["static_switches"] = static_states

            # 4. MAC ACL
            processed_data["mac_control_map"] = {str(item["id"]): item for item in (mac_acl if isinstance(mac_acl, list) else []) if "id" in item}

            # 5. Device Tracker 映射与备注提取 (核心优化)
            processed_data["tracker_map"] = {}
            online_lan_map = {}
            for item in (lan_list if isinstance(lan_list, list) else []):
                mac = item.get("mac", "").lower()
                if not mac: continue
                # 优先级取名: comment -> termname -> client_device -> hostname
                c = extract_name_from_label(item.get("comment", ""))
                t = item.get("termname", "")
                d = item.get("client_device", "")
                h = item.get("hostname", "")
                item["friendly_name"] = c or t or d or h or item.get("ip_addr", mac)
                online_lan_map[mac] = item

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

        except Exception as err:
            _LOGGER.error("iKuai 数据处理异常: %s", err)
            if self.data: return self.data
            raise UpdateFailed(f"通信故障: {err}")

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
        """执行动作并触发延迟刷新."""
        try:
            await self.api.call_action(action_body)
            # 立即触发本地数据“乐观更新”虽在 switch 逻辑，这里手动触发全局刷新确保最终状态一致
            self.hass.async_create_task(self._async_delay_refresh())
        except Exception as err:
            _LOGGER.error("Failed to execute iKuai action: %s", err)

    async def _async_delay_refresh(self) -> None:
        """操作后等待爱快后台更新，再抓取最新状态."""
        await asyncio.sleep(1.5)
        await self.async_refresh()