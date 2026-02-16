"""
get ikuai info by token and sess_key
完全兼容：
1. 旧版: Result: 30000, 数据在 Data 字段
2. 新版: code: 0, 数据在 results 字段
"""

import logging
import json
import time
import datetime
import asyncio
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    LOGIN_URL,
    ACTION_URL,
    SWITCH_TYPES,
)

_LOGGER = logging.getLogger(__name__)

class DataFetcher:
    """Class to fetch data from iKuai router."""

    def __init__(self, hass, host, username, passwd, pas, tracker_config, custom_switches_config=None):
        """Initialize the data fetcher."""
        self._host = host
        self._username = username
        self._passwd = passwd
        self._pass = pas
        self._hass = hass
        self._session_client = async_get_clientsession(hass, verify_ssl=False)
        self._datatracker = {}
        self._datarefreshtimes = {}
        self._tracker_config = tracker_config if tracker_config else {}
        self._custom_switches_config = custom_switches_config or {}
        self._semaphore = asyncio.Semaphore(3)

    def is_json(self, jsonstr):
        """Check if a string is valid JSON."""
        try:
            json.loads(jsonstr)
        except (ValueError, TypeError):
            return False
        return True

    async def requestpost_json(self, url, headerstr, json_body):
        """Send an asynchronous POST request and return JSON data."""
        async with self._semaphore:
            try:
                async with timeout(10):
                    async with self._session_client.post(url, headers=headerstr, json=json_body) as response:
                        if response.status != 200:
                            return None
                        
                        # 直接读取原始字节流，手动尝试多种编码解码
                        content = await response.read()
                        
                        text = None
                        # 依次尝试：UTF-8 -> GBK -> GB18030 -> Latin-1
                        for encoding in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
                            try:
                                text = content.decode(encoding)
                                break
                            except UnicodeDecodeError:
                                continue
                        
                        # 如果所有已知编码都失败，则忽略错误强制解码（防止集成崩溃）
                        if text is None:
                            text = content.decode('utf-8', errors='ignore')
                            _LOGGER.debug("All standard decodings failed, using ignore mode.")

                        if self.is_json(text):
                            return json.loads(text)
                        return text
            except (ClientConnectorError, asyncio.TimeoutError) as e:
                _LOGGER.warning("Network error visiting iKuai: %s", e)
                return None
            except Exception as e:
                _LOGGER.error("Unexpected error in requestpost_json: %s", e)
                return None

    async def requestpost_cookies(self, url, headerstr, json_body):
        """Send a POST request and extract the sess_key from cookies."""
        async with self._semaphore:
            try:
                async with timeout(10):
                    async with self._session_client.post(url, headers=headerstr, json=json_body) as response:
                        if response.status != 200:
                            return None
                        for cookie in response.cookies:
                            if cookie == "sess_key":
                                return response.cookies["sess_key"].value
                        return None
            except Exception as e:
                _LOGGER.error("Error in requestpost_cookies: %s", e)
                return None

    async def _login_ikuai(self):
        """Perform login to iKuai and return the session key."""
        header = {"Content-Type": "application/json;charset=UTF-8"}
        json_body = {"username": self._username, "passwd": self._passwd, "pass": self._pass}
        url = self._host + LOGIN_URL
        try:
            return await self.requestpost_cookies(url, header, json_body)
        except Exception:
            return None

    def seconds_to_dhms(self, seconds):
        """Convert seconds to a readable Day-Hour-Minute-Second format."""
        try:
            seconds = int(seconds)
            days = seconds // (3600 * 24)
            hours = (seconds // 3600) % 24
            minutes = (seconds // 60) % 60
            seconds = seconds % 60
            if days > 0: return f"{days}天{hours}小时{minutes}分钟"
            if hours > 0: return f"{hours}小时{minutes}分钟"
            if minutes > 0: return f"{minutes}分钟{seconds}秒"
            return f"{seconds}秒"
        except: return "Unknown"

    def _get_data_block(self, resdata):
        """Helper to extract data block compatible with both API versions."""
        if not isinstance(resdata, dict): return None
        # 兼容性判断：成功状态码可能是 code=0 (新) 或 Result=30000 (旧)
        if resdata.get("code") == 0 or resdata.get("Result") == 30000:
            # 数据块可能在 results (新) 或 Data (旧)
            return resdata.get("results") or resdata.get("Data")
        return None

    async def _get_ikuai_status(self, sess_key, data_dict):
        """Fetch general system status and AC information."""
        header = {
            'Cookie': f'username={self._username}; login=1; sess_key={sess_key}',
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"homepage","action":"show","param":{"TYPE":"sysstat,ac_status"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)

        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401
        
        data_block = self._get_data_block(resdata)
        if not data_block: return

        sysstat = data_block.get("sysstat", {})
        ac_status = data_block.get("ac_status", {})

        if sysstat:
            data_dict["sw_version"] = sysstat.get("verinfo", {}).get("verstring", "Unknown")
            data_dict["device_name"] = sysstat.get("hostname", "iKuai")
            data_dict["ikuai_uptime"] = self.seconds_to_dhms(sysstat.get("uptime", 0))

            cputemp_list = sysstat.get("cputemp", [])
            data_dict["ikuai_cputemp"] = cputemp_list[0] if (isinstance(cputemp_list, list) and cputemp_list) else ""

            cpu_list = sysstat.get("cpu", [])
            data_dict["ikuai_cpu"] = str(cpu_list[0]).replace("%","") if (isinstance(cpu_list, list) and cpu_list) else "0"

            memory = sysstat.get("memory", {})
            data_dict["ikuai_memory"] = str(memory.get("used", "")).replace("%","")
            data_dict["ikuai_memory_attrs"] = memory

            online_user = sysstat.get("online_user", {})
            data_dict["ikuai_online_user"] = online_user.get("count", 0)
            data_dict["ikuai_online_user_attrs"] = online_user

            stream = sysstat.get("stream", {})
            data_dict["ikuai_connect_num"] = int(stream.get("connect_num", 0))
            data_dict["ikuai_upload"] = round(stream.get("upload", 0)/1024/1024, 3)
            data_dict["ikuai_download"] = round(stream.get("download", 0)/1024/1024, 3)
            data_dict["ikuai_total_up"] = round(stream.get("total_up", 0)/1024/1024/1024, 2)
            data_dict["ikuai_total_down"] = round(stream.get("total_down", 0)/1024/1024/1024, 2)

            data_dict["ikuai_ap_online"] = ac_status.get("ap_online", 0)
            data_dict["ikuai_ap_online_attrs"] = ac_status
            data_dict["querytime"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return

    async def _get_ikuai_waninfo(self, sess_key, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name":"lan","action":"show","param":{"TYPE":"ether_info,snapshoot"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        
        data_block = self._get_data_block(resdata)
        if not data_block: return
        
        snapshoot_wan = data_block.get("snapshoot_wan")
        if isinstance(snapshoot_wan, list):
            for item in snapshoot_wan:
                if item.get("default_route") == 1:
                    data_dict["ikuai_wan_ip"] = item.get("ip_addr", "")
                    data_dict["ikuai_wan_ip_attrs"] = item
                    up_time = item.get("updatetime", 0)
                    data_dict["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - up_time)) if up_time > 0 else ""
                elif item.get("internet") in [3, 4]:
                    await self._get_ikuai_showvlan(sess_key, item.get("interface"), data_dict)

    async def _get_ikuai_showvlan(self, sess_key, interface, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name":"wan","action":"show","param":{"TYPE":"vlan_data,vlan_total","interface":interface,"limit":"0,20"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        
        data_block = self._get_data_block(resdata)
        if data_block and isinstance(data_block.get("vlan_data"), list):
            for vlan in data_block["vlan_data"]:
                if vlan.get("default_route") == 1:
                    data_dict["ikuai_wan_ip"] = vlan.get("pppoe_ip_addr", "")
                    up_time = vlan.get("pppoe_updatetime", 0)
                    data_dict["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - up_time)) if up_time > 0 else ""

    async def _get_ikuai_lan6info(self, sess_key, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name":"ipv6","action":"show","param":{"TYPE":"lan_data,lan_total"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        data_block = self._get_data_block(resdata)
        if data_block and isinstance(data_block.get("lan_data"), list) and data_block["lan_data"]:
            data_dict["ikuai_lan6_ip"] = data_block["lan_data"][0].get("ipv6_addr", "")

    async def _get_ikuai_wan6info(self, sess_key, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name":"ipv6","action":"show","param":{"TYPE":"data,total"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        data_block = self._get_data_block(resdata)
        if data_block and isinstance(data_block.get("data"), list) and data_block["data"]:
            data_dict["ikuai_wan6_ip"] = data_block["data"][0].get("dhcp6_ip_addr", "")

    async def _get_ikuai_mac_control(self, sess_key, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name":"acl_mac","action":"show","param":{"TYPE":"total,data","limit":"0,100"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        data_block = self._get_data_block(resdata)
        data_dict["mac_control"] = data_block.get("data", "") if data_block else ""

    async def _get_all_lan_hosts(self, sess_key):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        json_body = {"func_name": "monitor_lanip", "action": "show", "param": {"TYPE": "data,total", "limit": "0,2000"}}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, json_body)
        data_block = self._get_data_block(resdata)
        
        online_devices = {"ip": {}, "mac": {}}
        if data_block and isinstance(data_block.get("data"), list):
            for item in data_block["data"]:
                if item.get("ip_addr"): online_devices["ip"][item["ip_addr"]] = item
                if item.get("mac"): online_devices["mac"][item["mac"].lower()] = item
        return online_devices

    async def _get_ikuai_switch(self, sess_key, name, show_body, show_on, show_off, data_dict):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        resdata = await self.requestpost_json(self._host + ACTION_URL, header, show_body)
        data_block = self._get_data_block(resdata)
        if not data_block: return

        check_data = data_block.get("data")[0] if (isinstance(data_block.get("data"), list) and data_block["data"]) else data_block
        
        is_on = all(check_data.get(k) == v for k, v in show_on.items())
        if is_on:
            data_dict["switch"].append({"name": name, "onoff": "on"})
        else:
            data_dict["switch"].append({"name": name, "onoff": "off"})

    async def async_execute_action(self, sess_key, action_body):
        header = {'Cookie': f'username={self._username}; login=1; sess_key={sess_key}', 'Content-Type': 'application/json;charset=UTF-8'}
        return await self.requestpost_json(self._host + ACTION_URL, header, action_body)

    async def get_data(self, sess_key):
        """Orchestrate data fetching for all components."""
        new_data = {
            "switch": [], 
            "tracker": [], 
            "ikuai_wan_ip": "未检测到",
            "querytime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_name": "iKuai",
            "sw_version": "Unknown"
        }
        
        # 并发抓取主要状态
        status_res = await self._get_ikuai_status(sess_key, new_data)
        if status_res == 401: return 401

        tasks = [
            self._get_ikuai_waninfo(sess_key, new_data),
            self._get_ikuai_wan6info(sess_key, new_data),
            self._get_ikuai_lan6info(sess_key, new_data),
            self._get_ikuai_mac_control(sess_key, new_data),
            self._get_all_lan_hosts(sess_key)
        ]

        # 抓取内置开关
        for switch in SWITCH_TYPES:
            tasks.append(self._get_ikuai_switch(sess_key, SWITCH_TYPES[switch]['name'], 
                         SWITCH_TYPES[switch]['show_body'], SWITCH_TYPES[switch]['show_on'], 
                         SWITCH_TYPES[switch]['show_off'], new_data))

        # 抓取自定义开关
        for _, switch_config in self._custom_switches_config.items():
            tasks.append(self._get_ikuai_switch(sess_key, switch_config['name'], 
                         switch_config.get('show_body', {}), switch_config.get('show_on', {}), 
                         switch_config.get('show_off', {}), new_data))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_lan_devices = results[4] if (len(results) > 4 and not isinstance(results[4], Exception)) else None

        # 处理 Tracker 逻辑
        if self._tracker_config:
            for target_id, config in self._tracker_config.items():
                buffer_times = config.get("buffer", 2)
                target_type = config.get("type", "mac" if ":" in target_id else "ip")
                found_item = None

                if all_lan_devices:
                    if target_type == "ip": found_item = all_lan_devices["ip"].get(target_id)
                    else: found_item = all_lan_devices["mac"].get(target_id.lower())

                if found_item:
                    self._datatracker[target_id] = found_item
                    self._datarefreshtimes[target_id] = 0
                    new_data["tracker"].append(found_item)
                elif self._datatracker.get(target_id):
                    curr = self._datarefreshtimes.get(target_id, 0)
                    if curr < buffer_times:
                        new_data["tracker"].append(self._datatracker[target_id])
                        self._datarefreshtimes[target_id] = curr + 1

        return new_data
