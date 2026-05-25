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
            # 并发执行所有任务 (注意索引顺序)
            results = await asyncio.gather(
                self.api.get_system_status(),             # 0
                self.api.get_wan_info(),                  # 1
                self.api.call_action(SWITCH_TYPES[0].show_body), # 2: ARP Filter 状态
                self.api.call_action(SWITCH_TYPES[1].show_body), # 3: Stream Control 状态
                self.api.get_lan_devices(),               # 4
                self.api.get_mac_acl(),                   # 5
                self.api.get_ipv6_lan(),                  # 6
                self.api.get_ipv6_wan(),                  # 7
                self.api.get_wan_vlan(),                  # 8
                return_exceptions=True
            )

            # 严格按照 gather 顺序解包
            status      = results[0]
            wan         = results[1]
            arp_res     = results[2]
            stream_res  = results[3]
            lan_list    = results[4]
            mac_acl     = results[5]
            ipv6_lan    = results[6]
            ipv6_wan    = results[7]
            vlan_data   = results[8]

            # 异常检查
            for res in results:
                if isinstance(res, Exception):
                    if isinstance(res, IkuaiAuthError):
                        raise ConfigEntryAuthFailed from res
                    # 记录非致命异常但继续处理
                    _LOGGER.warning("Partial data fetch error: %s", res)

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

            # --- 1. 基础状态数据 ---
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

            # --- 2. IP 处理 ---
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

            # 属性合并
            ip_attrs = (found_wan_item if found_wan_item else {}).copy()
            ip_attrs.update({
                "wan_ipv6": wan6_ip,
                "lan_ipv6": lan6_ip,
                "query_time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            processed_data["ikuai_ip_attrs"] = ip_attrs
            processed_data["ikuai_memory_attrs"] = memory
            processed_data["ikuai_online_user_attrs"] = sysstat.get("online_user", {})
            processed_data["ikuai_ap_online_attrs"] = ac_status

            # --- 3. 开关状态解析 (关键修复逻辑) ---
            static_states = {}

            def check_is_on(api_res, show_on_def):
                """通用解析器：兼容 3.0 (Data/data) 和 4.0 (results/key) 结构."""
                if not api_res or not isinstance(api_res, dict):
                    return False
                
                # 遍历定义的检查条件 (例如 {"stream_ctl_mode": 1})
                for key, expected_val in show_on_def.items():
                    target_val = None
                    
                    # --- 探测路径 1: 4.0 风格 {"key": [ {"key": val} ]} ---
                    attr_list = api_res.get(key)
                    if isinstance(attr_list, list) and len(attr_list) > 0:
                        target_val = attr_list[0].get(key)
                    
                    # --- 探测路径 2: 3.0 风格 {"data": [ {"key": val} ]} ---
                    if target_val is None:
                        data_list = api_res.get("data")
                        if isinstance(data_list, list) and len(data_list) > 0:
                            target_val = data_list[0].get(key)

                    # --- 探测路径 3: 扁平风格 {"key": val} ---
                    if target_val is None:
                        target_val = api_res.get(key)

                    # --- 比对逻辑 ---
                    # 转换成字符串比对，确保数字 1 和 字符串 "1" 都能通过
                    if target_val is None or str(target_val) != str(expected_val):
                        return False
                        
                return True

            # 解析内置开关
            # 1. 先用通用解析器从 action 结果里找
            static_states["ikuai_arp_filter"] = "on" if check_is_on(arp_res, SWITCH_TYPES[0].show_on) else "off"
            static_states["ikuai_stream_control"] = "on" if check_is_on(stream_res, SWITCH_TYPES[1].show_on) else "off"

            # 2. 如果没对上，用 sysstat 里的原始字段强制纠正 (3.0 版本的强项)
            sysstat = (status or {}).get("sysstat", {})
            if static_states["ikuai_arp_filter"] == "off" and str(sysstat.get("arp_filter")) == "1":
                static_states["ikuai_arp_filter"] = "on"
            if static_states["ikuai_stream_control"] == "off" and str(sysstat.get("stream_ctl_mode")) == "1":
                static_states["ikuai_stream_control"] = "on"

            processed_data["static_switches"] = static_states

            # --- 4. 辅助数据映射 (用于 MAC 控制) ---
            processed_data["mac_control_map"] = {
                str(item["id"]): item for item in (mac_acl if isinstance(mac_acl, list) else []) if "id" in item
            }

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