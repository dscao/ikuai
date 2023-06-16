"""PVE Entities"""
import logging
import time
import datetime
import json
import requests
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError

from homeassistant.components.switch import SwitchEntity

from .data_fetcher import DataFetcher

from .const import (
    COORDINATOR, 
    DOMAIN, 
    CONF_USERNAME,
    CONF_PASSWD,
    CONF_PASS,
    CONF_HOST, 
    ACTION_URL,
    SWITCH_TYPES,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add Switchentities from a config_entry."""      
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    host = config_entry.data[CONF_HOST]
    username = config_entry.data[CONF_USERNAME]
    passwd = config_entry.data[CONF_PASSWD]
    pas = config_entry.data[CONF_PASS]
    
    switchs = []
    switchsmac = []
    
    if SWITCH_TYPES:
        _LOGGER.debug("setup switchs")
        for switch in SWITCH_TYPES:
            switchs.append(IKUAISwitch(hass, switch, coordinator, host, username, passwd, pas))
            _LOGGER.debug(SWITCH_TYPES[switch]["name"])
        async_add_entities(switchs, False)
    
    if coordinator.data.get("mac_control"):
        listmacdata = coordinator.data.get("mac_control")
        if isinstance(listmacdata, list):
            _LOGGER.debug(listmacdata)
            for mac in listmacdata:
                _LOGGER.debug(mac)
                switchsmac.append(IKUAISwitchmac(hass, coordinator, host, username, passwd, pas, mac["id"]))                
            async_add_entities(switchsmac, False)
            
            

class IKUAISwitch(SwitchEntity):
    _attr_has_entity_name = True
    def __init__(self, hass, kind, coordinator, host, username, passwd, pas):
        """Initialize."""
        super().__init__()
        self.kind = kind
        self.coordinator = coordinator        
        self._state = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }
        self._attr_icon = SWITCH_TYPES[self.kind]['icon']
        self._attr_device_class = "switch"
        self._attr_entity_registry_enabled_default = True
        self._hass = hass
        self._token = ""
        self._token_expire_time = 0
        self._allow_login = True    
        self._fetcher = DataFetcher(hass, host, username, passwd, pas)
        self._host = host
        self._name = SWITCH_TYPES[self.kind]['name']
        self._turn_on_body = SWITCH_TYPES[self.kind]['turn_on_body']
        self._turn_off_body = SWITCH_TYPES[self.kind]['turn_off_body']
        self._change = True
        self._switchonoff = None
        
        listswitch = self.coordinator.data.get("switch")
        
        for switchdata in listswitch:
            if switchdata["name"] == self._name:
                self._switchonoff = switchdata["onoff"]
                
        self._is_on = self._switchonoff == "on"
        self._state = "on" if self._is_on == True else "off"

        
    async def get_access_token(self):
        if time.time() < self._token_expire_time:
            return self._token
        else:
            if self._allow_login == True:
                self._token = await self._fetcher._login_ikuai()
                if self._token == 10001:
                    self._allow_login = False
                self._token_expire_time = time.time() + 60*60*2          
                return self._token
            else:
                return
   
    @property
    def name(self):
        """Return the name."""
        return f"{self._name}"

    @property
    def unique_id(self):
        return f"{DOMAIN}_switch_{self.coordinator.host}_{self._name}"

        
    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return False

    @property
    def is_on(self):
        """Check if switch is on."""        
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn switch on."""
        self._is_on = True
        self._change = False
        json_body = self._turn_on_body
        await self._switch(json_body)
        self._switchonoff = "on"


    async def async_turn_off(self, **kwargs):
        """Turn switch off."""
        self._is_on = False
        self._change = False
        json_body = self._turn_off_body
        await self._switch(json_body)
        self._switchonoff = "off"

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update entity."""
        await self.coordinator.async_request_refresh()

        listswitch = self.coordinator.data.get("switch")
        
        for switchdata in listswitch:
            if switchdata["name"] == self._name:
                self._switchonoff = switchdata["onoff"]
                
        self._is_on = self._switchonoff == "on"
        self._state = "on" if self._is_on == True else "off"
        self._change = True


    def requestpost_json(self, url, headerstr, json_body):
        responsedata = requests.post(url, headers=headerstr, json = json_body, verify=False)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata   
        
    async def _switch(self, action_body): 
        if self._allow_login == True:            
            sess_key = await self.get_access_token()          
            header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
            }
            
            json_body = action_body            

            url =  self._host + ACTION_URL
            
            try:
                async with timeout(10): 
                    resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
            except (
                ClientConnectorError
            ) as error:
                raise UpdateFailed(error)
            _LOGGER.debug("Requests remaining: %s", url)
            _LOGGER.debug(resdata)
            if resdata == 401:
                self._data = 401
                return
            if resdata["Result"] == 10014:
                self._data = 401
                return    
                        
        _LOGGER.info("操作ikuai: %s ", json_body)    
        return "OK"



class IKUAISwitchmac(SwitchEntity):
    _attr_has_entity_name = True
    def __init__(self, hass, coordinator, host, username, passwd, pas, macid):
        """Initialize."""
        super().__init__()
        self.coordinator = coordinator        
        self._state = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }
        self._attr_icon = "mdi:network-pos"
        self._attr_device_class = "switch"
        self._attr_entity_registry_enabled_default = True
        self._hass = hass
        self._token = ""
        self._token_expire_time = 0
        self._allow_login = True    
        self._fetcher = DataFetcher(hass, host, username, passwd, pas)
        self._host = host
        self._macid = macid
        self._change = True
        
        listmacswitch = coordinator.data.get("mac_control")
        if isinstance(listmacswitch, list):
            #_LOGGER.debug(listvmdata)
            for macswitch in listmacswitch:
                if macswitch["id"] == macid:
                    _LOGGER.debug(macswitch)
                    self._mac_address = macswitch["mac"]
                    self._mac = str(self._mac_address).replace(":","")
                    if macswitch.get("comment"):
                        self._name = "Mac_control_" + self._mac[-6:] +"("+macswitch["comment"]+")"
                    else:
                        self._name = "Mac_control_" + self._mac[-6:] +"(未备注)"                    
                    self._is_on = macswitch["enabled"] == "yes"
                    self._state = "on" if self._is_on == True else "off"
                    self._querytime = self.coordinator.data["querytime"]
        
    async def get_access_token(self):
        if time.time() < self._token_expire_time:
            return self._token
        else:
            if self._allow_login == True:
                self._token = await self._fetcher._login_ikuai()
                if self._token == 10001:
                    self._allow_login = False
                self._token_expire_time = time.time() + 60*60*2          
                return self._token
            else:
                return
   
    @property
    def name(self):
        """Return the name."""
        return f"{self._name}"

    @property
    def unique_id(self):
        return f"{DOMAIN}_switch_{self.coordinator.host}_{self._mac}"

        
    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return True

    @property
    def extra_state_attributes(self):
        """Return device state attributes."""
        attrs = {}
        attrs["mac_address"] = self._mac_address
        attrs["querytime"] = self._querytime
        
        return attrs
        
    @property
    def is_on(self):
        """Check if switch is on."""        
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn switch on."""
        self._is_on = True
        self._change = False
        mac_json_body = {"func_name":"acl_mac","action":"up","param":{"id":str(self._macid)}}
        await self._mac_control_switch(mac_json_body) 


    async def async_turn_off(self, **kwargs):
        """Turn switch off."""
        self._is_on = False
        self._change = False
        mac_json_body = {"func_name":"acl_mac","action":"down","param":{"id":str(self._macid)}}
        await self._mac_control_switch(mac_json_body)

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update entity."""
        #await self.coordinator.async_request_refresh()
        listmacswitch = self.coordinator.data.get("mac_control")
        if isinstance(listmacswitch, list):
            #_LOGGER.debug(listvmdata)
            for macswitch in listmacswitch:
                if macswitch["id"] == self._macid:
                    _LOGGER.debug(macswitch)
                    if self._change == True:
                        self._is_on = macswitch["enabled"] == "yes"
                        self._state = "on" if self._is_on == True else "off"
                    self._querytime = self.coordinator.data["querytime"]
                    self._change = True


    def requestpost_json(self, url, headerstr, json_body):
        responsedata = requests.post(url, headers=headerstr, json = json_body, verify=False)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata   
        
    async def _mac_control_switch(self, action_body): 
        if self._allow_login == True:            
            sess_key = await self.get_access_token()          
            header = {
            'Cookie': 'Cookie: username=admin; login=1; sess_key='+sess_key,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.40 Safari/537.36',
            }
            
            json_body = action_body            

            url =  self._host + ACTION_URL
            
            try:
                async with timeout(10): 
                    resdata = await self._hass.async_add_executor_job(self.requestpost_json, url, header, json_body)
            except (
                ClientConnectorError
            ) as error:
                raise UpdateFailed(error)
            _LOGGER.debug("Requests remaining: %s", url)
            _LOGGER.debug(resdata)
            if resdata == 401:
                self._data = 401
                return
            if resdata["Result"] == 10014:
                self._data = 401
                return    
                        
        _LOGGER.info("操作ikuai: %s ", json_body)    
        return "OK"
