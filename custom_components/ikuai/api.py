"""API Client for iKuai integration."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import ClientSession, ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import ACTION_URL, LOGIN_URL

_LOGGER = logging.getLogger(__name__)

class IkuaiError(Exception):
    """iKuai 基础错误."""

class IkuaiAuthError(IkuaiError):
    """认证失败（用户名密码错误）."""

class IkuaiConnectionError(IkuaiError):
    """网络连接问题."""

class IkuaiSessionError(IkuaiError):
    """Session 失效或登录超时."""


class IkuaiAPI:
    """iKuai API 异步客户端 (兼容 3.0 和 4.0)."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        host: str, 
        username: str, 
        passwd_md5: str, 
        passwd_base64: str
    ) -> None:
        """Initialize the API client."""
        self._hass = hass
        self._host = host.rstrip("/")
        self._username = username
        self._passwd_md5 = passwd_md5
        self._passwd_base64 = passwd_base64
        self._session: ClientSession = async_get_clientsession(hass, verify_ssl=False)
        self._sess_key: str | None = None
        self._semaphore = asyncio.Semaphore(3)  # 限制并发请求数，避免过载

    async def _async_request(self, url: str, body: dict[str, Any], headers: dict | None = None) -> Any:
        """核心请求方法：增加多编码探测以兼容 iKuai 3.0 的 GBK 编码."""
        async with self._semaphore: 
            try:
                await asyncio.sleep(0.05)  # 小延迟，避免过快连续请求导致 iKuai 连接重置
                async with asyncio.timeout(15):  # 增加超时保护
                    async with self._session.post(url, json=body, headers=headers) as response:
                        if response.status != 200:
                            _LOGGER.error("iKuai returned status %s", response.status)
                            return None
                        
                        # 关键逻辑：读取原始字节流并尝试解码
                        content = await response.read()
                        
                        # 尝试编码顺序：UTF-8 (4.0默认) -> GBK (3.0常用) -> GB18030 (保底)
                        for encoding in ["utf-8", "gbk", "gb18030"]:
                            try:
                                text = content.decode(encoding)
                                return json.loads(text), response.cookies
                            except (UnicodeDecodeError, ValueError):
                                continue
                        
                        _LOGGER.error("Failed to decode iKuai response with known encodings")
                        return None
            except (asyncio.TimeoutError, ClientResponseError) as err:
                raise IkuaiConnectionError(f"Connection to iKuai failed: {err}") from err
            except Exception as err:
                _LOGGER.error("Unexpected error during iKuai request: %s", err)
                return None

    async def login(self) -> str:
        """登录 iKuai 并获取 sess_key."""
        url = f"{self._host}{LOGIN_URL}"
        body = {
            "username": self._username,
            "passwd": self._passwd_md5,
            "pass": self._passwd_base64, # 必须包含 salt_11
            "remember": 0 
        }
        
        result = await self._async_request(url, body)
        if not result:
            raise IkuaiConnectionError("Failed to connect for login")
        
        res_json, cookies = result
        
        # 1. 检查密码错误 (iKuai 即使错误有时也返回 200)
        if res_json.get("Result") == 10001:
            raise IkuaiAuthError("Invalid username or password")

        # 2. 提取 sess_key (尝试 JSON 和 Cookies)
        # 4.0 倾向于 JSON 返回，3.0 倾向于 Cookie 返回
        key = res_json.get("sess_key")
        if not key and "sess_key" in cookies:
            key = cookies["sess_key"].value
        
        if key:
            self._sess_key = key
            _LOGGER.debug("iKuai login successful, sess_key obtained")
            return key
        
        _LOGGER.error("iKuai login failed, full response: %s", res_json)
        raise IkuaiAuthError(f"No sess_key found in response. Error: {res_json.get('ErrMsg', 'Unknown')}")

    async def call_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用 iKuai API 动作 (核心数据抓取)."""
        if not self._sess_key:
            await self.login()

        url = f"{self._host}{ACTION_URL}"
        headers = {
            "Cookie": f"username={self._username}; login=1; sess_key={self._sess_key}",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*"
        }

        result = await self._async_request(url, payload, headers=headers)
        if not result:
            return {}
        
        res_json, _ = result

        # 处理 Session 过期 (iKuai 错误码 10014)
        res_code = res_json.get("Result")
        if res_code == 10014:
            _LOGGER.debug("iKuai session expired, retrying login")
            self._sess_key = None
            return await self.call_action(payload)

        # --- 核心兼容性处理：提取数据块 ---
        # 成功状态：code: 0 (新版/4.0) 或 Result: 30000 (旧版/3.0)
        res_status = res_json.get("code")
        if res_status == 0 or res_code == 30000:
            # 数据存放：results (新版) 或 Data (旧版)
            return res_json.get("results") or res_json.get("Data") or {}
        
        _LOGGER.warning("iKuai API returned non-success result: %s", res_json)
        return {}

    async def get_system_status(self) -> dict[str, Any]:
        """获取系统状态 (sysstat, ac_status)."""
        payload = {
            "func_name": "homepage",
            "action": "show",
            "param": {"TYPE": "sysstat,ac_status"}
        }
        return await self.call_action(payload)

    async def get_lan_devices(self) -> list[dict[str, Any]]:
        """获取所有 LAN 终端列表."""
        payload = {
            "func_name": "monitor_lanip",
            "action": "show",
            "param": {"TYPE": "data,total", "limit": "0,1000"}
        }
        data = await self.call_action(payload)
        return data.get("data", [])

    async def get_wan_info(self) -> list[dict[str, Any]]:
        """获取 WAN 接口物理快照."""
        payload = {
            "func_name": "lan",
            "action": "show",
            "param": {"TYPE": "snapshoot"}
        }
        data = await self.call_action(payload)
        return data.get("snapshoot_wan", [])

    async def get_ipv6_lan(self) -> list[dict[str, Any]]:
        """获取 LAN IPv6."""
        payload = {
            "func_name": "ipv6",
            "action": "show",
            "param": {"TYPE": "lan_data,lan_total"}
        }
        data = await self.call_action(payload)
        return data.get("lan_data", [])

    async def get_ipv6_wan(self) -> list[dict[str, Any]]:
        """获取 WAN IPv6."""
        payload = {
            "func_name": "ipv6",
            "action": "show",
            "param": {"TYPE": "data,total"}
        }
        data = await self.call_action(payload)
        return data.get("data", [])        

    async def get_wan_vlan(self) -> list[dict[str, Any]]:
        """获取 PPPoE/VLAN 拨号详细数据."""
        payload = {
            "func_name": "wan",
            "action": "show",
            "param": {
                "TYPE": "vlan_data,vlan_total",
                "limit": "0,20"
            }
        }
        data = await self.call_action(payload)
        return data.get("vlan_data", [])

    async def get_mac_acl(self) -> list[dict[str, Any]]:
        """获取 MAC 访问控制列表."""
        payload = {
            "func_name": "acl_mac",
            "action": "show",
            "param": {"TYPE": "data,total", "limit": "0,100"}
        }
        data = await self.call_action(payload)
        return data.get("data", [])
        
    async def async_execute_action(self, action_body: dict[str, Any]) -> dict[str, Any]:
        """执行通用动作 (供按钮和开关调用)."""
        return await self.call_action(action_body)