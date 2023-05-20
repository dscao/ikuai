"""IKUAI Entities"""
import logging
import time
import datetime
import json
import re
import requests
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError

from homeassistant.helpers.device_registry import DeviceEntryType

from homeassistant.components.button import ButtonEntity

from .const import (
    COORDINATOR, 
    DOMAIN, 
    BUTTON_TYPES, 
    CONF_USERNAME,
    CONF_PASSWD,
    CONF_PASS,
    CONF_HOST, 
    ACTION_URL,
)

from .data_fetcher import DataFetcher

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add bjtoon_health_code entities from a config_entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    host = config_entry.data[CONF_HOST]
    username = config_entry.data[CONF_USERNAME]
    passwd = config_entry.data[CONF_PASSWD]
    pas = config_entry.data[CONF_PASS]

    buttons = []
    for button in BUTTON_TYPES:
        buttons.append(IKUAIButton(hass, button, coordinator, host, username, passwd, pas))

    async_add_entities(buttons, False)


class IKUAIButton(ButtonEntity):
    """Define an bjtoon_health_code entity."""
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
        self._attr_device_class = "restart"
        self._attr_entity_registry_enabled_default = True
        self._hass = hass
        self._token = ""
        self._token_expire_time = 0
        self._allow_login = True
        self._fetcher = DataFetcher(hass, host, username, passwd, pas)
        self._host = host
        
        
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
        return f"{BUTTON_TYPES[self.kind]['name']}"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.kind}_{self.coordinator.host}"
        
    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return True

    @property
    def state(self):
        """Return the state."""
        return self._state

        
    @property
    def device_class(self):
        """Return the unit_of_measurement."""
        if BUTTON_TYPES[self.kind].get("device_class"):
            return BUTTON_TYPES[self.kind]["device_class"]
           
        
    def press(self) -> None:
        """Handle the button press."""

    async def async_press(self) -> None:
        """Handle the button press."""        
        await self._ikuai_action(BUTTON_TYPES[self.kind]["action_body"])
        

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update Bjtoon health code entity."""
        #await self.coordinator.async_request_refresh()        
        
        
    def requestpost_json(self, url, headerstr, json_body):
        responsedata = requests.post(url, headers=headerstr, json = json_body, verify=False)
        if responsedata.status_code != 200:
            return responsedata.status_code
        json_text = responsedata.content.decode('utf-8')
        resdata = json.loads(json_text)
        return resdata        
        
    async def _ikuai_action(self, action_body): 
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
                        
        self._state = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _LOGGER.info("操作ikuai: %s ", json_body)    
        return "OK"
        
