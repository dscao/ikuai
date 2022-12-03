"""
get ikuai info by token and sess_key
"""

import logging
import requests
import re
import asyncio
import json
import time
import datetime
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from .const import (
    LOGIN_URL,
    ACTION_URL,
    DEVICE_TRACKERS, 
)

_LOGGER = logging.getLogger(__name__)



class DataFetcher:
    """fetch the ikuai data"""

    def __init__(self, hass, host, username, passwd, pas):

        self._host = host
        self._username = username
        self._passwd = passwd
        self._pass = pas
        self._hass = hass
        self._session_client = async_create_clientsession(hass)
        self._data = {}
    
    def requestget_data(self, url, headerstr):
        responsedata = requests.get(url, headers=headerstr)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata
        
    def requestpost_data(self, url, headerstr, datastr):
        responsedata = requests.post(url, headers=headerstr, data = datastr, verify=False)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata
        
    def requestpost_json(self, url, headerstr, json_body):
        responsedata = requests.post(url, headers=headerstr, json = json_body, verify=False)
        _LOGGER.debug(responsedata)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata

    def requestpost_cookies(self, url, headerstr, json_body):
        responsedata = requests.post(url, headers=headerstr, json = json_body, verify=False)
        if responsedata.status_code != 200:
            return responsedata.status_code
        resdata = responsedata.cookies["sess_key"]
        return resdata         
        
    async def _login_ikuai(self):
        hass = self._hass
        host = self._host
        username =self._username
        passwd =self._passwd
        pas =self._pass
        header = {
            "Content-Type": "application/json;charset=UTF-8"
        }

        json_body =  {
            "username": username,
            "passwd": passwd,
            "pass": pas
        }  
        url =  host + LOGIN_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_cookies, url, header, json_body) 
                _LOGGER.debug(resdata)
                if isinstance(resdata, list):
                    _LOGGER.debug("iKuai Username or Password is wrong，please reconfig!")   
                    return resdata.get("Result")
                else:
                    _LOGGER.debug("login_successfully for IKUAI")                
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s", url)          
       
        return resdata
        
    
    def seconds_to_dhms(self, seconds):
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
        

    async def _get_ikuai_status(self, sess_key):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"homepage","action":"show","param":{"TYPE":"sysstat,ac_status"}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return
            
        self._data = {}

        self._data["sw_version"] = resdata["Data"]["sysstat"]["verinfo"]["verstring"]
        self._data["device_name"] = resdata["Data"]["sysstat"]["hostname"]
        
        
        if resdata["Data"]["sysstat"]["cputemp"]:
            self._data["ikuai_cputemp"] = resdata["Data"]["sysstat"]["cputemp"][0]
        else:
            self._data["ikuai_cputemp"] = ""
        
        self._data["ikuai_uptime"] = self.seconds_to_dhms(resdata["Data"]["sysstat"]["uptime"])        
        self._data["ikuai_cpu"] = resdata["Data"]["sysstat"]["cpu"][0].replace("%","")
        self._data["ikuai_memory"] = resdata["Data"]["sysstat"]["memory"]["used"].replace("%","")
        self._data["ikuai_memory_attrs"] = resdata["Data"]["sysstat"]["memory"]
        self._data["ikuai_online_user"] = resdata["Data"]["sysstat"]["online_user"]["count"]
        self._data["ikuai_online_user_attrs"] = resdata["Data"]["sysstat"]["online_user"]
        self._data["ikuai_upload"] = round(resdata["Data"]["sysstat"]["stream"]["upload"]/1024/1024, 3)
        self._data["ikuai_download"] = round(resdata["Data"]["sysstat"]["stream"]["download"]/1024/1024, 3)
        self._data["ikuai_total_up"] = round(resdata["Data"]["sysstat"]["stream"]["total_up"]/1024/1024/1024, 2)
        self._data["ikuai_total_down"] = round(resdata["Data"]["sysstat"]["stream"]["total_down"]/1024/1024/1024, 2)
        self._data["ikuai_ap_online"] = resdata["Data"]["ac_status"]["ap_online"]
        self._data["ikuai_ap_online_attrs"] = resdata["Data"]["ac_status"]
        
        querytime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._data["querytime"] = querytime
        
        return

    async def _get_ikuai_waninfo(self, sess_key):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"lan","action":"show","param":{"TYPE":"ether_info,snapshoot"}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return            

        if resdata["Data"].get("snapshoot_wan"):
            self._data["ikuai_internet"] = resdata["Data"]["snapshoot_wan"][0]["internet"]
            self._data["ikuai_count_pppoe"] = resdata["Data"]["snapshoot_wan"][0]["count_pppoe"]
            if self._data["ikuai_internet"] == 0 or self._data["ikuai_internet"] ==1 or self._data["ikuai_internet"] == 2:
                self._data["ikuai_wan_ip"] = resdata["Data"]["snapshoot_wan"][0]["ip_addr"]
                self._data["ikuai_wan_ip_attrs"] = resdata["Data"]["snapshoot_wan"][0]
                if resdata["Data"]["snapshoot_wan"][0]["updatetime"] == 0:
                    self._data["ikuai_wan_uptime"] = ""
                else:
                    self._data["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - resdata["Data"]["snapshoot_wan"][0]["updatetime"])) 
            else:
                self._data["ikuai_wan_ip"] = ""
                self._data["ikuai_wan_uptime"] = ""
        
        return
        
    async def _get_ikuai_showvlan(self, sess_key, vlan_internet):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"wan","action":"show","param":{"TYPE":"vlan_data,vlan_total","ORDER_BY":"vlan_name","ORDER":"asc","vlan_internet":2,"interface":"wan1","limit":"0,20"}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return            

        if resdata["Data"].get("vlan_data"):
            vlan_datas = resdata["Data"]["vlan_data"]
            for vlan_data in vlan_datas:
                if vlan_data["pppoe_updatetime"] != 0:
                    self._data["ikuai_wan_ip"] = vlan_data["pppoe_ip_addr"]
                    self._data["ikuai_wan_ip_attrs"] = vlan_data
                    self._data["ikuai_wan_uptime"] = self.seconds_to_dhms(int(time.time() - vlan_data["pppoe_updatetime"])) 
                    return
        else:
            self._data["ikuai_wan_ip"] = ""
            self._data["ikuai_wan_uptime"] = ""
        
        return
        
    async def _get_ikuai_wan6info(self, sess_key):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"ipv6","action":"show","param":{"TYPE":"lan_data,lan_total","limit":"0,20","ORDER_BY":"","ORDER":""}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return            
        if resdata["Data"].get("lan_data"):
            self._data["ikuai_wan6_ip"] = resdata["Data"]["lan_data"][0]["ipv6_addr"]
            self._data["ikuai_wan6_ip_attrs"] = resdata["Data"]["lan_data"][0]
        else:
            self._data["ikuai_wan6_ip"] = ""       
        return
        
    async def _get_ikuai_mac_control(self, sess_key):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"acl_mac","action":"show","param":{"TYPE":"total,data","limit":"0,100","ORDER_BY":"","ORDER":""}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return            
        if resdata["Data"].get("data"):
            self._data["mac_control"] = resdata["Data"].get("data")
        else:
            self._data["mac_control"] = ""
        return
        
        
    async def _get_ikuai_device_tracker(self, sess_key, macaddress):
        header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
        }
        
        json_body = {"func_name":"monitor_lanip","action":"show","param":{"TYPE":"data,total","ORDER_BY":"ip_addr_int","orderType":"IP","limit":"0,20","ORDER":"","FINDS":"ip_addr,mac,comment,username","KEYWORDS":macaddress}}
        

        url =  self._host + ACTION_URL
        
        try:
            async with timeout(10): 
                resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
        except (
            ClientConnectorError
        ) as error:
            raise UpdateFailed(error)
        _LOGGER.debug("Requests remaining: %s: %s", url, json_body)
        _LOGGER.debug(resdata)
        if resdata == 401:
            self._data = 401
            return
        if resdata["Result"] == 10014:
            self._data = 401
            return            
        if resdata["Data"].get("data"):
            _LOGGER.debug(resdata["Data"].get("data"))
            self._data["tracker"].append(resdata["Data"].get("data")[0])
        return
    
        
    async def get_data(self, sess_key):  
        threads = [            
            self._get_ikuai_status(sess_key)
        ]
        await asyncio.wait(threads)
        
        threads = [            
            self._get_ikuai_waninfo(sess_key),
            self._get_ikuai_wan6info(sess_key),
            self._get_ikuai_mac_control(sess_key),
        ]
        await asyncio.wait(threads)
        
        self._data["tracker"] = []
        threads = []
        for device_tracker in DEVICE_TRACKERS:
            threads.append(self._get_ikuai_device_tracker(sess_key, DEVICE_TRACKERS[device_tracker]["mac_address"]))
        await asyncio.wait(threads)
        if (self._data["ikuai_internet"] == 3 or self._data["ikuai_internet"] ==4) and int(self._data["ikuai_count_pppoe"])>0:
            threads = [            
            self._get_ikuai_showvlan(sess_key, self._data["ikuai_internet"])
            ]
            await asyncio.wait(threads)
        
        _LOGGER.debug(self._data)
        return self._data


class GetDataError(Exception):
    """request error or response data is unexpected"""
