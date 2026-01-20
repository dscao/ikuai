"""
get ikuai info by token and sess_key
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
        except ValueError:
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
                        text = await response.text()
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
        host = self._host
        username = self._username
        passwd = self._passwd
        pas = self._pass
        header = {
            "Content-Type": "application/json;charset=UTF-8"
        }

        json_body =  {
            "username": username,
            "passwd": passwd,
            "pass": pas
        }
        url = host + LOGIN_URL

        try:
            resdata = await self.requestpost_cookies(url, header, json_body)
            if isinstance(resdata, list):
                return resdata.get("Result")
            elif isinstance(resdata, int):
                return resdata
            elif resdata:
                return resdata
            else:
                return None
        except Exception:
            return None

    def seconds_to_dhms(self, seconds):
        """Convert seconds to a readable Day-Hour-Minute-Second format."""
        days = seconds // (3600 * 24)
        hours = (seconds // 3600) % 24
        minutes = (seconds // 60) % 60
        seconds = seconds % 60
        if days > 0 :
            return ("{0}天{1}小时{2}分钟".format(days,hours,minutes))
        if hours > 0 :
            return ("{0}小时{1}分钟".format(hours,minutes))
        if minutes > 0 :
            return ("{0}分钟{1}秒".format(minutes,seconds))
        return ("{0}秒".format(seconds))

    async def _get_ikuai_status(self, sess_key, data_dict):
        """Fetch general system status and AC information."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        json_body = {"func_name":"homepage","action":"show","param":{"TYPE":"sysstat,ac_status"}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_dict["ikuai_wan_ip"] = "未检测到默认网关线路"

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        sysstat = data_block.get("sysstat", {})
        ac_status = data_block.get("ac_status", {})

        if sysstat:
            data_dict["sw_version"] = sysstat.get("verinfo", {}).get("verstring", "")
            data_dict["device_name"] = sysstat.get("hostname", "")

            cputemp_list = sysstat.get("cputemp", [])
            data_dict["ikuai_cputemp"] = cputemp_list[0] if cputemp_list else ""

            cpu_list = sysstat.get("cpu", [])
            data_dict["ikuai_cpu"] = cpu_list[0].replace("%","") if cpu_list else ""

            memory = sysstat.get("memory", {})
            if memory:
                data_dict["ikuai_memory"] = memory.get("used", "").replace("%","")
                data_dict["ikuai_memory_attrs"] = memory
            else:
                data_dict["ikuai_memory"] = ""
                data_dict["ikuai_memory_attrs"] = ""

            data_dict["ikuai_uptime"] = self.seconds_to_dhms(sysstat.get("uptime", 0))

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

            querytime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data_dict["querytime"] = querytime
        return

    async def _get_ikuai_waninfo(self, sess_key, data_dict):
        """Fetch WAN interface information and handle VLAN routes."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"lan","action":"show","param":{"TYPE":"ether_info,snapshoot"}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        snapshoot_wan = data_block.get("snapshoot_wan")

        if snapshoot_wan and isinstance(snapshoot_wan, list):
            for item in snapshoot_wan:
                if item.get("default_route") == 1:
                    data_dict["ikuai_wan_ip"] = item.get("ip_addr", "")
                    data_dict["ikuai_wan_ip_attrs"] = item
                    if item.get("updatetime", 0) == 0:
                        data_dict["ikuai_wan_uptime"] = ""
                    else:
                        data_dict["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - item["updatetime"]))

                elif item.get("internet") in [3, 4]:
                    await self._get_ikuai_showvlan(sess_key, item.get("interface"), data_dict)
        return

    async def _get_ikuai_showvlan(self, sess_key, interface, data_dict):
        """Fetch VLAN specific WAN information."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"wan","action":"show","param":{"TYPE":"vlan_data,vlan_total","ORDER_BY":"vlan_name","ORDER":"asc","vlan_internet":2,"interface":interface,"limit":"0,20"}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        vlan_datas = data_block.get("vlan_data")

        if isinstance(vlan_datas, list):
            for vlan_data in vlan_datas:
                if vlan_data.get("pppoe_updatetime", 0) != 0 and vlan_data.get("default_route") == 1:
                    data_dict["ikuai_wan_ip"] = vlan_data.get("pppoe_ip_addr", "")
                    data_dict["ikuai_wan_ip_attrs"] = vlan_data
                    data_dict["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - vlan_data["pppoe_updatetime"]))
                    return
        else:
            data_dict["ikuai_wan_ip"] = ""
            data_dict["ikuai_wan_uptime"] = ""
        return

    async def _get_ikuai_lan6info(self, sess_key, data_dict):
        """Fetch lan IPv6 interface information."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"ipv6","action":"show","param":{"TYPE":"lan_data,lan_total","limit":"0,20","ORDER_BY":"","ORDER":""}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        lan_data = data_block.get("lan_data")

        if isinstance(lan_data, list) and len(lan_data) > 0:
            data_dict["ikuai_lan6_ip"] = lan_data[0].get("ipv6_addr", "")
            data_dict["ikuai_lan6_ip_attrs"] = lan_data[0]
        else:
            data_dict["ikuai_lan6_ip"] = ""
        return

    async def _get_ikuai_wan6info(self, sess_key, data_dict):
        """Fetch wan IPv6 interface information."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"ipv6","action":"show","param":{"TYPE":"data,total","limit":"0,20","ORDER_BY":"","ORDER":""}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        wan_data = data_block.get("data")

        if isinstance(wan_data, list) and len(wan_data) > 0:
            data_dict["ikuai_wan6_ip"] = wan_data[0].get("dhcp6_ip_addr", "")
            data_dict["ikuai_wan6_ip_attrs"] = wan_data[0]
        else:
            data_dict["ikuai_wan6_ip"] = ""
        return

    async def _get_ikuai_mac_control(self, sess_key, data_dict):
        """Fetch MAC access control list."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {"func_name":"acl_mac","action":"show","param":{"TYPE":"total,data","limit":"0,100","ORDER_BY":"","ORDER":""}}
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        data_block = resdata.get("Data", {}) if isinstance(resdata, dict) else {}
        if data_block.get("data"):
            data_dict["mac_control"] = data_block.get("data")
        else:
            data_dict["mac_control"] = ""
        return

    async def _get_all_lan_hosts(self, sess_key):
        """Fetch all LAN hosts to reduce individual tracker requests."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = {
            "func_name": "monitor_lanip",
            "action": "show",
            "param": {"TYPE": "data,total", "limit": "0,2000", "ORDER_BY": "", "ORDER": ""}
        }
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return None
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        online_devices = {"ip": {}, "mac": {}}

        if resdata and isinstance(resdata, dict) and resdata.get("Data"):
            data_list = resdata["Data"].get("data", [])
            if data_list:
                for item in data_list:
                    if item.get("ip_addr"):
                        online_devices["ip"][item["ip_addr"]] = item
                    if item.get("mac"):
                        online_devices["mac"][item["mac"].lower()] = item

        return online_devices

    async def _get_ikuai_switch(self, sess_key, name, show_body, show_on, show_off, data_dict):
        """Fetch status for custom configured switches."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        json_body = show_body
        url = self._host + ACTION_URL

        resdata = await self.requestpost_json(url, header, json_body)

        if resdata is None: return
        if isinstance(resdata, int) and resdata == 401: return 401
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401

        for key, value in show_on.items():
            show_on_key = key
            show_on_value = value
        for key, value in show_off.items():
            show_off_key = key
            show_off_value = value

        data_block = resdata.get("Data") if isinstance(resdata, dict) else None
        if not data_block or data_block.get("data") == []:
            return

        if show_body["param"].get("TYPE") == "data":
            data_list = data_block.get("data")
            if data_list and len(data_list) > 0:
                if data_list[0].get(show_on_key) == show_on_value:
                    data_dict["switch"].append({"name":name,"onoff":"on"})
                elif data_list[0].get(show_off_key) == show_off_value:
                    data_dict["switch"].append({"name":name,"onoff":"off"})
        else:
            if data_block.get(show_on_key) == show_on_value:
                data_dict["switch"].append({"name":name,"onoff":"on"})
            elif data_block.get(show_off_key) == show_off_value:
                data_dict["switch"].append({"name":name,"onoff":"off"})
        return

    async def async_execute_action(self, sess_key, action_body):
        """Execute a specific action call to the router."""
        header = {
            'Cookie': 'Cookie: username='+self._username+'; login=1; sess_key='+sess_key,
            'Content-Type': 'application/json;charset=UTF-8',
        }
        url = self._host + ACTION_URL
        resdata = await self.requestpost_json(url, header, action_body)

        if resdata is None: return None
        if isinstance(resdata, int): return resdata
        if isinstance(resdata, dict) and resdata.get("Result") == 10014: return 401
        return resdata

    async def get_data(self, sess_key):
        """Orchestrate data fetching for all components including buffering for trackers."""
        new_data = {
            "switch": [],
            "tracker": []
        }

        status_res = await self._get_ikuai_status(sess_key, new_data)
        if status_res == 401: return 401

        tasks = [
            asyncio.create_task(self._get_ikuai_waninfo(sess_key, new_data)),
            asyncio.create_task(self._get_ikuai_wan6info(sess_key, new_data)),
            asyncio.create_task(self._get_ikuai_lan6info(sess_key, new_data)),
            asyncio.create_task(self._get_ikuai_mac_control(sess_key, new_data)),
            asyncio.create_task(self._get_all_lan_hosts(sess_key))
        ]

        for switch in SWITCH_TYPES:
            tasks.append(
                asyncio.create_task(self._get_ikuai_switch(
                    sess_key,
                    SWITCH_TYPES[switch]['name'],
                    SWITCH_TYPES[switch]['show_body'],
                    SWITCH_TYPES[switch]['show_on'],
                    SWITCH_TYPES[switch]['show_off'],
                    new_data
                ))
            )

        # Process custom switches from configuration
        for switch_key, switch_config in self._custom_switches_config.items():
            show_body = switch_config.get('show_body', {})
            show_on = switch_config.get('show_on', {})
            show_off = switch_config.get('show_off', {})

            tasks = [
                asyncio.create_task(self._get_ikuai_switch(sess_key, switch_config['name'], show_body, show_on, show_off, new_data)),
                ]
            await asyncio.gather(*tasks)

        results = await asyncio.gather(*tasks)


        if 401 in results: return 401

        all_lan_devices = results[3]

        if self._tracker_config:
            network_error = (all_lan_devices is None)

            for target_id, config in self._tracker_config.items():
                buffer_times = config.get("buffer", 2)
                keyword = target_id
                target_type = config.get("type", "ip")

                if "type" not in config:
                    if ":" in keyword and len(keyword) == 17: target_type = "mac"
                    else: target_type = "ip"

                found_item = None

                if not network_error and all_lan_devices:
                    if target_type == "ip" and keyword in all_lan_devices["ip"]:
                        found_item = all_lan_devices["ip"][keyword]
                    elif target_type == "mac" and keyword.lower() in all_lan_devices["mac"]:
                        found_item = all_lan_devices["mac"][keyword.lower()]

                if found_item:
                    self._datatracker[keyword] = found_item
                    self._datarefreshtimes[keyword] = 0
                    new_data["tracker"].append(found_item)
                else:
                    if self._datatracker.get(keyword):
                        current_times = self._datarefreshtimes.get(keyword, 0)
                        if current_times < buffer_times:
                            new_data["tracker"].append(self._datatracker[keyword])
                            self._datarefreshtimes[keyword] = current_times + 1

        self._data = new_data
        return self._data

class GetDataError(Exception):
    """Custom exception for data fetching errors."""
