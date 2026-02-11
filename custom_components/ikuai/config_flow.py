"""Config flow for ikuai integration."""
from __future__ import annotations
import logging
import voluptuous as vol
import requests
import json
import base64
import re
import ipaddress
import asyncio
from hashlib import md5
from urllib.parse import unquote

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector, 
    SelectSelectorConfig, 
    TextSelector, 
    TextSelectorConfig
)
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

from .const import (
    LOGIN_URL, ACTION_URL, DOMAIN, 
    CONF_PASSWD, CONF_PASS, CONF_UPDATE_INTERVAL, 
    CONF_ACT_BUFFER, CONF_TRACKER_CONFIG,
    CONF_SOURCE_MODE, MODE_UI, MODE_CONST
)

_LOGGER = logging.getLogger(__name__)

MODE_INCLUDE = "include"
MODE_EXCLUDE = "exclude"
MODE_OPTIONS = [MODE_INCLUDE, MODE_EXCLUDE]

CONFIG_MODES = [MODE_UI, MODE_CONST]

OPTION_ACTION_SCAN = "scan_add"
OPTION_ACTION_CUSTOM = "custom_add"
OPTION_ACTION_MANAGE = "manage_devices"
OPTION_ACTION_DELETE = "delete_devices"
OPTION_ACTION_SAVE = "exit"

ACTION_OPTIONS = [
    OPTION_ACTION_SCAN,
    OPTION_ACTION_CUSTOM,
    OPTION_ACTION_MANAGE,
    OPTION_ACTION_DELETE,
    OPTION_ACTION_SAVE
]

class IkuaiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for iKuai."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._login_data = {}
        self._temp_trackers = {} 
        self._sess_key = None
        self._host_url = None
        self._title = "iKuai"
        self._fetched_hosts = {} 
        self._fetched_macs = {}
        self._current_username = "admin"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return IkuaiOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step and global settings."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].rstrip("/")
            password = user_input[CONF_PASSWORD]
            username = user_input[CONF_USERNAME]
            
            try:
                if int(user_input.get(CONF_UPDATE_INTERVAL, 10)) < 5:
                    errors[CONF_UPDATE_INTERVAL] = "interval_too_small"
                if int(user_input.get(CONF_ACT_BUFFER, 2)) < 1:
                    errors[CONF_ACT_BUFFER] = "invalid_buffer"
            except (ValueError, TypeError):
                errors["base"] = "expected_int"

            if not errors:
                passwd_md5 = md5(password.encode('utf-8')).hexdigest()
                passwd_base64 = base64.b64encode(f"salt_11{password}".encode()).decode()

                res = await self.hass.async_add_executor_job(
                    self._try_login, host, username, passwd_md5, passwd_base64
                )
                
                if res.get("status") == "success":
                    self._sess_key = res.get("sess_key")
                    self._host_url = host
                    self._current_username = username
                    self._title = f"ikuai-{host.split('//')[1] if '//' in host else host}"
                    self._login_data = {
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWD: passwd_md5,
                        CONF_PASS: passwd_base64,
                        CONF_UPDATE_INTERVAL: int(user_input.get(CONF_UPDATE_INTERVAL, 10)),
                        CONF_ACT_BUFFER: int(user_input.get(CONF_ACT_BUFFER, 2)),
                        CONF_SOURCE_MODE: user_input.get(CONF_SOURCE_MODE, MODE_UI),
                        CONF_TRACKER_CONFIG: {},
                        "title": self._title
                    }
                    
                    await self.async_set_unique_id(f"ikuai-{host}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=self._title, data=self._login_data)
                else:
                    errors["base"] = res.get("error", "unknown")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="http://192.168.1.1"): str,
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_UPDATE_INTERVAL, default=10): vol.Coerce(int),
                vol.Optional(CONF_ACT_BUFFER, default=2): vol.Coerce(int),
                vol.Required(CONF_SOURCE_MODE, default=MODE_UI): SelectSelector(
                    SelectSelectorConfig(options=CONFIG_MODES, translation_key="config_mode")
                ),
            }),
            errors=errors
        )

    def _try_login(self, host, username, passwd, pas):
        """Test if the login credentials are valid."""
        header = {"Content-Type": "application/json;charset=UTF-8"}
        json_body = {"username": username, "passwd": passwd, "pass": pas}
        try:
            response = requests.post(host + LOGIN_URL, json=json_body, headers=header, verify=False, timeout=5)
            if response.status_code != 200:
                return {"status": "error", "error": "cannot_connect"}
            resdata = response.json()
            if resdata.get("Result") == 10001:
                return {"status": "error", "error": "invalid_auth"}
            return {"status": "success", "sess_key": response.cookies.get("sess_key")}
        except Exception:
            return {"status": "error", "error": "cannot_connect"}

    async def async_step_menu(self, user_input=None):
        """Display the configuration menu."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=[OPTION_ACTION_SCAN, OPTION_ACTION_CUSTOM]
        )

    async def async_step_scan_add(self, user_input=None):
        """Handle device discovery and selection."""
        errors = {}
        if user_input is not None:
            selected_ips = user_input.get("selected_ips", [])
            ip_mode = user_input.get("ip_filter_mode", MODE_INCLUDE)
            selected_macs = user_input.get("selected_macs", [])
            mac_mode = user_input.get("mac_filter_mode", MODE_INCLUDE)
            
            self._temp_trackers = {}
            
            if ip_mode == MODE_INCLUDE:
                for item in selected_ips:
                    display_name = self._extract_name_from_label(self._fetched_hosts.get(item, item))
                    self._temp_trackers[item] = {"type": "ip", "id": item, "name": display_name, "buffer": 0}
            else:
                for ip_addr, label in self._fetched_hosts.items():
                    display_name = self._extract_name_from_label(label)
                    if ip_addr not in selected_ips:
                        self._temp_trackers[ip_addr] = {"type": "ip", "id": ip_addr, "name": display_name, "buffer": 0}

            if mac_mode == MODE_INCLUDE:
                for item in selected_macs:
                    display_name = self._extract_name_from_label(self._fetched_macs.get(item, item))
                    self._temp_trackers[item] = {"type": "mac", "id": item, "name": display_name, "buffer": 0}
            else:
                for mac_addr, label in self._fetched_macs.items():
                    display_name = self._extract_name_from_label(label)
                    if mac_addr not in selected_macs:
                        self._temp_trackers[mac_addr] = {"type": "mac", "id": mac_addr, "name": display_name, "buffer": 0}

            if not self._temp_trackers:
                errors["base"] = "no_devices_found"
            else:
                return await self.async_step_manage_devices()

        hosts_dict, macs_dict = {}, {}
        retry_strategy = [(1, 0.5), (3, 1.0), (5, 0)]
        retry_success = False

        for attempt, (timeout_sec, wait_sec) in enumerate(retry_strategy):
            try:
                hosts_dict, macs_dict = await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        self._fetch_lan_info, self._host_url, self._sess_key, self._current_username
                    ),
                    timeout=timeout_sec
                )
                retry_success = True
                break
            except (asyncio.TimeoutError, Exception):
                if attempt < 2: await asyncio.sleep(wait_sec)

        if not retry_success:
            errors["base"] = "cannot_connect"
        else:
            try:
                self._fetched_hosts = dict(sorted(hosts_dict.items(), key=lambda x: ipaddress.ip_address(x[0])))
            except ValueError:
                self._fetched_hosts = dict(sorted(hosts_dict.items()))
            self._fetched_macs = dict(sorted(macs_dict.items()))

        schema = vol.Schema({
            vol.Required("ip_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("selected_ips"): cv.multi_select(self._fetched_hosts),
            vol.Required("mac_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("selected_macs"): cv.multi_select(self._fetched_macs),
        })
        
        return self.async_show_form(step_id="scan_add", data_schema=schema, errors=errors)

    def _fetch_lan_info(self, host_url, sess_key, username):
        """Fetch current online device information from the router."""
        hosts = {}
        macs = {}
        if not sess_key: return hosts, macs
        header = {
            'Cookie': f'username={username}; login=1; sess_key={sess_key}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        json_body = {"func_name": "monitor_lanip", "action": "show", "param": {"TYPE": "data,total", "limit": "0,1000"}}
        try:
            response = requests.post(host_url + ACTION_URL, json=json_body, headers=header, verify=False, timeout=5)
            if response.status_code == 200:
                res = response.json()
                if res.get("Data", {}).get("data"):
                    for item in res["Data"]["data"]:
                        ip = item.get("ip_addr")
                        mac = item.get("mac")
                        raw_comment = item.get("comment", "")
                        comment = unquote(raw_comment) if raw_comment else ""
                        label_ip = f"{ip} ({comment})" if comment and ip else (ip or "")
                        label_mac = f"{mac} ({comment})" if comment and mac else (mac or "")
                        if ip: hosts[ip] = label_ip
                        if mac: macs[mac] = label_mac
        except Exception as e:
            _LOGGER.error("Error fetching LAN info: %s", e)
            raise e
        return hosts, macs

    def _extract_name_from_label(self, label):
        """Extract a readable name from a formatted label."""
        match = re.match(r'[^\(]+\((.+)\)$', label)
        if match:
            return match.group(1).strip()
        return label.strip()

    async def async_step_custom_add(self, user_input=None):
        """Handle manual device configuration input."""
        errors = {}
        default_buffer_fill = 0 

        if user_input is not None:
            ip_mode = user_input.get("ip_filter_mode")
            ip_text = user_input.get("custom_ips", "")
            subnet_mode = user_input.get("subnet_filter_mode")
            subnet_text = user_input.get("custom_subnets", "")
            mac_mode = user_input.get("mac_filter_mode")
            mac_text = user_input.get("custom_macs", "")

            valid_config = True
            self._temp_trackers = {}
            
            def parse_item(item_str):
                item_str = item_str.strip()
                addr, buff, name = None, None, None
                if '#' in item_str:
                    parts = item_str.split('#', 1)
                    addr = parts[0].strip()
                    rest = parts[1].strip()
                    if ':' in rest:
                        buff_str, name_str = rest.split(':', 1)
                        if buff_str.isdigit():
                            buff = int(buff_str)
                        name = name_str
                    else:
                        if rest.isdigit():
                            buff = int(rest)
                else:
                    mac_match = re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', item_str)
                    if mac_match:
                        addr = mac_match.group(0)
                        remaining = item_str[len(addr):]
                        if remaining.startswith(':'):
                            name = remaining[1:]
                    elif ':' in item_str:
                         parts = item_str.split(':', 1)
                         addr = parts[0].strip()
                         name = parts[1]
                    else:
                        addr = item_str
                final_buff = buff if buff is not None else 0
                return addr, final_buff, name

            is_exclude = (ip_mode == MODE_EXCLUDE or mac_mode == MODE_EXCLUDE)
            if is_exclude:
                try:
                    all_hosts, all_macs = await self.hass.async_add_executor_job(
                        self._fetch_lan_info, self._host_url, self._sess_key, self._current_username
                    )
                    if ip_mode == MODE_EXCLUDE:
                        for ip, label in all_hosts.items():
                            self._temp_trackers[ip] = {"type": "ip", "id": ip, "name": self._extract_name_from_label(label), "buffer": default_buffer_fill}
                    if mac_mode == MODE_EXCLUDE:
                        for mac, label in all_macs.items():
                            self._temp_trackers[mac] = {"type": "mac", "id": mac, "name": self._extract_name_from_label(label), "buffer": default_buffer_fill}
                except Exception as e:
                    _LOGGER.error("Failed to fetch LAN info: %s", e)
                    errors["base"] = "cannot_connect"
                    valid_config = False

            if ip_text and valid_config:
                for line in ip_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    try:
                        ipaddress.ip_address(addr)
                        if ip_mode == MODE_INCLUDE:
                            self._temp_trackers[addr] = {"type": "ip", "id": addr, "name": name or addr, "buffer": buff}
                        elif ip_mode == MODE_EXCLUDE:
                            if addr in self._temp_trackers: del self._temp_trackers[addr]
                    except ValueError:
                        errors["custom_ips"] = "invalid_ip_format"
                        valid_config = False

            if subnet_text and valid_config:
                for line in subnet_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    try:
                        net = ipaddress.ip_network(addr, strict=False)
                        if subnet_mode == MODE_INCLUDE:
                            for ip in net.hosts():
                                ip_str = str(ip)
                                if ip_str not in self._temp_trackers:
                                    self._temp_trackers[ip_str] = {"type": "ip", "id": ip_str, "name": name or ip_str, "buffer": buff}
                    except ValueError: errors["custom_subnets"], valid_config = "invalid_subnet_format", False

            if mac_text and valid_config:
                for line in mac_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    if not re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", addr):
                         errors["custom_macs"] = "invalid_mac_format"
                         valid_config = False
                    else:
                         fmt_mac = addr.lower().replace("-", ":")
                         if mac_mode == MODE_INCLUDE:
                             self._temp_trackers[fmt_mac] = {"type": "mac", "id": fmt_mac, "name": name or fmt_mac, "buffer": buff}
                         elif mac_mode == MODE_EXCLUDE:
                             if fmt_mac in self._temp_trackers: del self._temp_trackers[fmt_mac]

            if valid_config and not errors:
                if not self._temp_trackers:
                     errors["base"] = "no_devices_found"
                else:
                     return await self.async_step_manage_devices()

        schema = vol.Schema({
            vol.Required("ip_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("custom_ips"): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required("subnet_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=[MODE_INCLUDE], translation_key="filter_mode")),
            vol.Optional("custom_subnets"): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required("mac_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("custom_macs"): TextSelector(TextSelectorConfig(multiline=True)),
        })
        return self.async_show_form(step_id="custom_add", data_schema=schema, errors=errors)

    async def async_step_manage_devices(self, user_input=None):
        """Finalize and manage selected devices."""
        errors = {}
        if user_input is not None:
            final_tracker_config = {}
            
            for target_id, info in self._temp_trackers.items():
                safe_key = target_id.replace(".", "_").replace(":", "_")
                new_name = user_input.get(f"name_{safe_key}", info.get("name", target_id))
                
                raw_buffer = user_input.get(f"buffer_{safe_key}")
                
                if raw_buffer is None or raw_buffer == "" or raw_buffer == "0":
                    new_buffer = 0
                else:
                    try:
                        new_buffer = int(raw_buffer)
                        if new_buffer < 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        errors[f"buffer_{safe_key}"] = "expected_int"
                        new_buffer = 0

                if not errors:
                    final_tracker_config[target_id] = {"type": info["type"], "name": new_name, "buffer": new_buffer}
            
            if not errors:
                return self.async_create_entry(
                    title=self._login_data.get("title", "iKuai"),
                    data={**self._login_data, CONF_TRACKER_CONFIG: final_tracker_config}
                )

        schema = {}
        global_default = self._login_data.get(CONF_ACT_BUFFER, 2)
        for target_id, info in self._temp_trackers.items():
            safe_key = target_id.replace(".", "_").replace(":", "_")
            default_name = info.get("name", target_id)
            val = info.get("buffer", info.get("custom_buffer", 0))
            default_buffer_val = "" if val == 0 else str(val)
            
            schema[vol.Required(f"name_{safe_key}", default=default_name)] = str
            schema[vol.Optional(f"buffer_{safe_key}", default=default_buffer_val)] = str
            
        return self.async_show_form(
            step_id="manage_devices",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"global_default": str(global_default)}
        )

class IkuaiOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options update for the integration."""
    
    def __init__(self, config_entry):
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._login_data = config_entry.data
        self._sess_key = None
        self._temp_trackers = {}
        self._fetched_hosts = {} 
        self._fetched_macs = {}
        self._current_username = config_entry.data.get(CONF_USERNAME, "admin")
        self._fetch_error = None
        self._options = config_entry.options.copy()

    async def _ensure_login_with_retry(self):
        """Ensure session validity for router actions."""
        if self._sess_key: return True
        flow = IkuaiConfigFlow()
        try:
            res = await asyncio.wait_for(
                self.hass.async_add_executor_job(
                    flow._try_login, 
                    self._login_data[CONF_HOST], 
                    self._login_data[CONF_USERNAME], 
                    self._login_data[CONF_PASSWD], 
                    self._login_data[CONF_PASS]
                ),
                timeout=10
            )
            if res.get("status") == "success":
                self._sess_key = res.get("sess_key")
                self._fetch_error = None
                return True
        except asyncio.TimeoutError:
            self._fetch_error = "login_timeout"
        except Exception as e:
            self._fetch_error = str(e)
        return False

    async def async_step_init(self, user_input=None):
        """Initial step for options menu."""
        errors = {}
        
        current_buffer = self._options.get(
            CONF_ACT_BUFFER, 
            self._config_entry.data.get(CONF_ACT_BUFFER, 2)
        )
        current_interval = self._options.get(
            CONF_UPDATE_INTERVAL, 
            self._config_entry.data.get(CONF_UPDATE_INTERVAL, 10)
        )
        current_mode = self._options.get(
            CONF_SOURCE_MODE, 
            self._config_entry.data.get(CONF_SOURCE_MODE, MODE_UI)
        )

        if user_input is not None:
            try:
                new_buffer = int(user_input.get(CONF_ACT_BUFFER, current_buffer))
                if new_buffer < 1:
                    errors[CONF_ACT_BUFFER] = "invalid_buffer"
                    
                new_interval = int(user_input.get(CONF_UPDATE_INTERVAL, current_interval))
                if new_interval < 5:
                    errors[CONF_UPDATE_INTERVAL] = "interval_too_small"
            except (ValueError, TypeError):
                errors["base"] = "expected_int"

            if not errors:
                self._options[CONF_ACT_BUFFER] = new_buffer
                self._options[CONF_UPDATE_INTERVAL] = new_interval
                self._options[CONF_SOURCE_MODE] = user_input.get(CONF_SOURCE_MODE)
                
                new_data = self._config_entry.data.copy()
                new_data[CONF_ACT_BUFFER] = new_buffer
                new_data[CONF_UPDATE_INTERVAL] = new_interval
                new_data[CONF_SOURCE_MODE] = user_input.get(CONF_SOURCE_MODE)
                
                self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
                
                action = user_input.get("next_step")
                if action == OPTION_ACTION_SAVE or (action is None and user_input.get(CONF_SOURCE_MODE) != current_mode):
                    return self.async_create_entry(title="", data=self._options)
                
                if action == OPTION_ACTION_SCAN:
                    return await self.async_step_scan_add()
                elif action == OPTION_ACTION_CUSTOM:
                    return await self.async_step_custom_add()
                elif action == OPTION_ACTION_DELETE:
                    return await self.async_step_delete_devices()
                elif action == OPTION_ACTION_MANAGE:
                    self._temp_trackers = self._config_entry.data.get(CONF_TRACKER_CONFIG, {}).copy()
                    return await self.async_step_manage_devices()
                else:
                    return self.async_create_entry(title="", data=self._options)

        schema = {
            vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): vol.Coerce(int),
            vol.Optional(CONF_ACT_BUFFER, default=current_buffer): vol.Coerce(int),
            vol.Required(CONF_SOURCE_MODE, default=current_mode): SelectSelector(
                SelectSelectorConfig(options=CONFIG_MODES, translation_key="config_mode")
            ),
        }
        
        if current_mode == MODE_UI:
            schema[vol.Optional("next_step", default=OPTION_ACTION_SAVE)] = SelectSelector(
                SelectSelectorConfig(options=ACTION_OPTIONS, translation_key="action_steps")
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors
        )

    async def async_step_scan_add(self, user_input=None):
        """Append new devices via router scan."""
        errors = {}
        current_config = self._config_entry.data.get(CONF_TRACKER_CONFIG, {})
        
        if user_input is None:
            self._temp_trackers = current_config.copy()
        
        if user_input is not None:
            selected_ips = user_input.get("selected_ips", [])
            ip_mode = user_input.get("ip_filter_mode", MODE_INCLUDE)
            selected_macs = user_input.get("selected_macs", [])
            mac_mode = user_input.get("mac_filter_mode", MODE_INCLUDE)
            
            if ip_mode == MODE_EXCLUDE or mac_mode == MODE_EXCLUDE:
                retry_success = False
                retry_strategy = [(1, 0.5), (3, 1.0), (5, 0)]
                
                try:
                    if await self._ensure_login_with_retry():
                        flow = IkuaiConfigFlow()
                        all_hosts, all_macs = {}, {}
                        
                        for attempt, (timeout_sec, wait_sec) in enumerate(retry_strategy):
                            try:
                                all_hosts, all_macs = await asyncio.wait_for(
                                    self.hass.async_add_executor_job(
                                        flow._fetch_lan_info, 
                                        self._login_data[CONF_HOST], 
                                        self._sess_key, 
                                        self._current_username
                                    ),
                                    timeout=timeout_sec
                                )
                                retry_success = True
                                break
                            except (asyncio.TimeoutError, Exception):
                                if attempt < 2: await asyncio.sleep(wait_sec)
                        
                        if retry_success:
                            self._temp_trackers = {}
                            default_buffer = 0
                            
                            if ip_mode == MODE_EXCLUDE:
                                for ip, label in all_hosts.items():
                                    if ip not in selected_ips:
                                        self._temp_trackers[ip] = {"type": "ip", "id": ip, "name": self._extract_name_from_label(label), "buffer": default_buffer}
                            else:
                                self._temp_trackers.update({k: v for k, v in current_config.items() if v["type"] == "ip"})
                                for item in selected_ips:
                                    if item not in self._temp_trackers:
                                        self._temp_trackers[item] = {"type": "ip", "id": item, "name": self._extract_name_from_label(all_hosts.get(item, item)), "buffer": 0}

                            if mac_mode == MODE_EXCLUDE:
                                for mac, label in all_macs.items():
                                    if mac not in selected_macs:
                                        self._temp_trackers[mac] = {"type": "mac", "id": mac, "name": self._extract_name_from_label(label), "buffer": default_buffer}
                            else:
                                self._temp_trackers.update({k: v for k, v in current_config.items() if v["type"] == "mac"})
                                for item in selected_macs:
                                    if item not in self._temp_trackers:
                                        self._temp_trackers[item] = {"type": "mac", "id": item, "name": self._extract_name_from_label(all_macs.get(item, item)), "buffer": 0}
                        else:
                            errors["base"] = "cannot_connect"
                    else:
                        errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "cannot_connect"
            else:
                for item in selected_ips:
                    if item not in self._temp_trackers:
                        display_name = self._extract_name_from_label(self._fetched_hosts.get(item, item))
                        self._temp_trackers[item] = {"type": "ip", "id": item, "name": display_name, "buffer": 0}
                for item in selected_macs:
                    if item not in self._temp_trackers:
                        display_name = self._extract_name_from_label(self._fetched_macs.get(item, item))
                        self._temp_trackers[item] = {"type": "mac", "id": item, "name": display_name, "buffer": 0}
            
            if not errors:
                return await self.async_step_manage_devices()
        
        if not self._fetched_hosts and not self._fetch_error:
            retry_success = False
            retry_strategy = [(1, 0.5), (3, 1.0), (5, 0)]
            try:
                if await self._ensure_login_with_retry():
                    flow = IkuaiConfigFlow()
                    hosts, macs = {}, {}
                    for attempt, (timeout_sec, wait_sec) in enumerate(retry_strategy):
                        try:
                            hosts, macs = await asyncio.wait_for(
                                self.hass.async_add_executor_job(flow._fetch_lan_info, self._login_data[CONF_HOST], self._sess_key, self._current_username),
                                timeout=timeout_sec
                            )
                            retry_success = True
                            break
                        except (asyncio.TimeoutError, Exception):
                            if attempt < 2: await asyncio.sleep(wait_sec)
                    if retry_success:
                        try:
                            hosts = dict(sorted(hosts.items(), key=lambda x: ipaddress.ip_address(x[0])))
                        except ValueError:
                            hosts = dict(sorted(hosts.items()))
                        macs = dict(sorted(macs.items()))
                        existing_keys = set(current_config.keys())
                        self._fetched_hosts = {k: v for k, v in hosts.items() if k not in existing_keys}
                        self._fetched_macs = {k: v for k, v in macs.items() if k not in existing_keys}
                    else:
                        errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "cannot_connect"
            except Exception as e:
                errors["base"] = "cannot_connect"
                self._fetch_error = str(e)
        
        schema = vol.Schema({
            vol.Required("ip_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("selected_ips", default=[]): cv.multi_select(self._fetched_hosts if self._fetched_hosts else {}),
            vol.Required("mac_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("selected_macs", default=[]): cv.multi_select(self._fetched_macs if self._fetched_macs else {}),
        })
        
        return self.async_show_form(
            step_id="scan_add", 
            data_schema=schema, 
            errors=errors,
            description_placeholders={"loading_hint": f"当前已配置 {len(current_config)} 个设备" if current_config else ""}
        )

    def _extract_name_from_label(self, label):
        """Extract name helper for options flow."""
        match = re.match(r'[^\(]+\((.+)\)$', label)
        if match: return match.group(1).strip()
        return label.strip()

    async def async_step_custom_add(self, user_input=None):
        """Append new devices manually in options flow."""
        errors = {}
        current_config = self._config_entry.data.get(CONF_TRACKER_CONFIG, {})
        default_buffer_fill = 0
        
        if user_input is not None:
            ip_text, subnet_text, mac_text = user_input.get("custom_ips", ""), user_input.get("custom_subnets", ""), user_input.get("custom_macs", "")
            ip_mode = user_input.get("ip_filter_mode")
            subnet_mode = user_input.get("subnet_filter_mode")
            mac_mode = user_input.get("mac_filter_mode")
            
            is_exclude = (ip_mode == MODE_EXCLUDE or mac_mode == MODE_EXCLUDE)

            if is_exclude:
                retry_success = False
                retry_strategy = [(1, 0.5), (3, 1.0), (5, 0)]
                all_hosts, all_macs = {}, {}

                for attempt, (timeout_sec, wait_sec) in enumerate(retry_strategy):
                    try:
                        all_hosts, all_macs = await asyncio.wait_for(
                            self.hass.async_add_executor_job(
                                self._fetch_lan_info, self._host_url, self._sess_key, self._current_username
                            ),
                            timeout=timeout_sec
                        )
                        retry_success = True
                        break
                    except (asyncio.TimeoutError, Exception):
                        if attempt < 2: await asyncio.sleep(wait_sec)

                if not retry_success:
                    errors["base"] = "cannot_connect"
                else:
                    self._temp_trackers = {} 
                    
                    if ip_mode == MODE_EXCLUDE:
                        for ip, label in all_hosts.items():
                            self._temp_trackers[ip] = {"type": "ip", "id": ip, "name": self._extract_name_from_label(label), "buffer": default_buffer_fill}
                    else:
                        self._temp_trackers.update({k: v for k, v in current_config.items() if v["type"] == "ip"})
                    
                    if mac_mode == MODE_EXCLUDE:
                        for mac, label in all_macs.items():
                            self._temp_trackers[mac] = {"type": "mac", "id": mac, "name": self._extract_name_from_label(label), "buffer": default_buffer_fill}
                    else:
                        self._temp_trackers.update({k: v for k, v in current_config.items() if v["type"] == "mac"})
            else:
                self._temp_trackers = {} 

            def parse_item(item_str):
                item_str = item_str.strip()
                addr, buff, name = None, None, None
                
                if '#' in item_str:
                    parts = item_str.split('#', 1)
                    addr = parts[0].strip()
                    rest = parts[1].strip()
                    if ':' in rest:
                        buff_str, name_str = rest.split(':', 1)
                        if buff_str.isdigit():
                            buff = int(buff_str)
                        name = name_str
                    else:
                        if rest.isdigit():
                            buff = int(rest)
                else:
                    mac_match = re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', item_str)
                    if mac_match:
                        addr = mac_match.group(0)
                        remaining = item_str[len(addr):]
                        if remaining.startswith(':'):
                            name = remaining[1:]
                    elif ':' in item_str:
                         parts = item_str.split(':', 1)
                         addr = parts[0].strip()
                         name = parts[1]
                    else:
                        addr = item_str
                final_buff = buff if buff is not None else 0
                return addr, final_buff, name

            valid_config = True
            if ip_text and not errors:
                for line in ip_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    try:
                        ipaddress.ip_address(addr)
                        if ip_mode == MODE_INCLUDE:
                            self._temp_trackers[addr] = {"type": "ip", "id": addr, "name": name or addr, "buffer": buff}
                        elif ip_mode == MODE_EXCLUDE:
                            if addr in self._temp_trackers: del self._temp_trackers[addr]
                    except ValueError: errors["custom_ips"], valid_config = "invalid_ip_format", False

            if subnet_text and not errors:
                for line in subnet_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    try:
                        net = ipaddress.ip_network(addr, strict=False)
                        if subnet_mode == MODE_INCLUDE:
                            for ip in net.hosts():
                                ip_str = str(ip)
                                if ip_str not in self._temp_trackers:
                                    self._temp_trackers[ip_str] = {"type": "ip", "id": ip_str, "name": name or ip_str, "buffer": buff}
                    except ValueError: errors["custom_subnets"], valid_config = "invalid_subnet_format", False

            if mac_text and not errors:
                for line in mac_text.replace("\n", ",").split(","):
                    line = line.strip()
                    if not line: continue
                    addr, buff, name = parse_item(line)
                    if not re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", addr): errors["custom_macs"], valid_config = "invalid_mac_format", False
                    else:
                        fmt_mac = addr.lower().replace("-", ":")
                        if mac_mode == MODE_INCLUDE:
                            self._temp_trackers[fmt_mac] = {"type": "mac", "id": fmt_mac, "name": name or fmt_mac, "buffer": buff}
                        elif mac_mode == MODE_EXCLUDE:
                            if fmt_mac in self._temp_trackers: del self._temp_trackers[fmt_mac]

            if valid_config and not errors: return await self.async_step_manage_devices()

        default_ip_text = []
        default_mac_text = []
        for k, v in current_config.items():
            entry_str = k
            entry_str += f"#{v.get('buffer', 0)}"
            
            if v.get("name") and v.get("name") != k:
                 entry_str += f":{v.get('name')}"
            
            if v["type"] == "ip":
                default_ip_text.append(entry_str)
            else:
                default_mac_text.append(entry_str)

        schema = vol.Schema({
            vol.Required("ip_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("custom_ips", default=", ".join(default_ip_text)): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required("subnet_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=[MODE_INCLUDE], translation_key="filter_mode")),
            vol.Optional("custom_subnets"): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required("mac_filter_mode", default=MODE_INCLUDE): SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, translation_key="filter_mode")),
            vol.Optional("custom_macs", default=", ".join(default_mac_text)): TextSelector(TextSelectorConfig(multiline=True)),
        })
        return self.async_show_form(step_id="custom_add", data_schema=schema, errors=errors)

    async def async_step_manage_devices(self, user_input=None):
        """Update existing device configuration in options flow."""
        errors = {}
        if user_input is not None:
            final_config = {}
            for target_id, info in self._temp_trackers.items():
                safe_key = target_id.replace(".", "_").replace(":", "_")
                new_name = user_input.get(f"name_{safe_key}", info.get("name", target_id))
                
                raw_buffer = user_input.get(f"buffer_{safe_key}")
                if raw_buffer is None or raw_buffer == "" or raw_buffer == "0":
                     new_buffer = 0
                else:
                    try:
                        new_buffer = int(raw_buffer)
                        if new_buffer < 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        errors[f"buffer_{safe_key}"] = "expected_int"
                        new_buffer = 0

                if not errors:
                    final_config[target_id] = {"type": info["type"], "name": new_name, "buffer": new_buffer}
            
            if not errors:
                new_data = {**self._config_entry.data, CONF_TRACKER_CONFIG: final_config}
                self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
                return self.async_create_entry(title="", data=self._options)

        schema = {}
        global_default = self._options.get(CONF_ACT_BUFFER, 2)
        for target_id, info in self._temp_trackers.items():
            safe_key = target_id.replace(".", "_").replace(":", "_")
            schema[vol.Required(f"name_{safe_key}", default=info.get("name", target_id))] = str
            
            val = info.get("buffer", info.get("custom_buffer", 0))
            default_val = "" if val == 0 else str(val)
            schema[vol.Optional(f"buffer_{safe_key}", default=default_val)] = str
            
        return self.async_show_form(
            step_id="manage_devices",
            data_schema=vol.Schema(schema),
            description_placeholders={"global_default": str(global_default)},
            errors=errors
        )

    async def async_step_delete_devices(self, user_input=None):
        """Handle device removal in options flow."""
        current_config = self._config_entry.data.get(CONF_TRACKER_CONFIG, {})
        DELETE_KEY = "device_list"
        
        if user_input is not None:
            selected_to_delete = user_input.get(DELETE_KEY, [])
            final_config = {k: v for k, v in current_config.items() if k not in selected_to_delete}
            new_data = {**self._config_entry.data, CONF_TRACKER_CONFIG: final_config}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return self.async_create_entry(title="", data=self._options)

        options = {k: f"{v.get('name', k)} ({k})" for k, v in current_config.items()}
        return self.async_show_form(step_id="delete_devices", data_schema=vol.Schema({vol.Optional(DELETE_KEY, default=[]): cv.multi_select(options)}), description_placeholders={"action": "请勾选要删除的设备，未被勾选的设备将继续保留。"})
