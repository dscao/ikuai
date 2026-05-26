"""Support for iKuai switch entities."""
from __future__ import annotations

import time
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SWITCH_TYPES, IkuaiSwitchEntityDescription
from .coordinator import IKUAIDataUpdateCoordinator

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up iKuai switches."""
    coordinator: IKUAIDataUpdateCoordinator = entry.runtime_data
    entities = []

    for desc in SWITCH_TYPES:
        entities.append(IkuaiStaticSwitch(coordinator, desc))

    mac_controls = coordinator.data.get("mac_control_map", {})
    for mac_id in mac_controls:
        entities.append(IkuaiMacControlSwitch(coordinator, mac_id))

    async_add_entities(entities)

class IkuaiStaticSwitch(CoordinatorEntity[IKUAIDataUpdateCoordinator], SwitchEntity):
    """实现内置及自定义功能开关 (带状态保护)."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{coordinator.host}"
        self._attr_device_info = coordinator.device_info
        
        # 状态保护变量
        self._last_action_time = 0
        self._pending_state = None

    @property
    def is_on(self) -> bool:
        # 如果距离上次操作不足 5 秒，返回点击时的状态，不看协调器的数据
        if time.time() - self._last_action_time < 5:
            return self._pending_state == "on"
            
        states = self.coordinator.data.get("static_switches", {})
        return states.get(self.entity_description.key) == "on"

    async def async_turn_on(self, **kwargs) -> None:
        """打开开关."""
        self._last_action_time = time.time()
        self._pending_state = "on"
        self.async_write_ha_state() # 立即刷新 UI
        
        await self.coordinator.async_control_device(self.entity_description.turn_on_body)

    async def async_turn_off(self, **kwargs) -> None:
        """关闭开关."""
        self._last_action_time = time.time()
        self._pending_state = "off"
        self.async_write_ha_state()
        
        await self.coordinator.async_control_device(self.entity_description.turn_off_body)

    @callback
    def _handle_coordinator_update(self) -> None:
        # 当协调器更新时，只有不在保护期内才强制刷新 UI
        if time.time() - self._last_action_time >= 5:
            super()._handle_coordinator_update()

class IkuaiMacControlSwitch(CoordinatorEntity[IKUAIDataUpdateCoordinator], SwitchEntity):
    """动态 MAC 控制开关 (同样加入状态保护)."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, description, mac_id) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._mac_id = str(mac_id)
        self._attr_device_info = coordinator.device_info
        self._last_action_time = 0
        self._pending_on = False
        self._update_attr()

    def _update_attr(self, description):
        item = self.coordinator.data.get("mac_control_map", {}).get(self._mac_id, {})
        comment = item.get("comment") or "未备注"
        mac_addr = item.get("mac", "Unknown")
        self._attr_name = f"MAC访问控制: {comment} ({mac_addr})"
        self._attr_unique_id = f"{DOMAIN}_mac_ctrl_{self._mac_id}_{self.coordinator.host}"
        self._attr_translation_key = description.translation_key

    @property
    def is_on(self) -> bool:
        # 保护期延长至 15 秒，确保跨越 1.5 个轮询周期
        if time.time() - self._last_action_time < 15:
            return self._pending_state == "on"
            
        states = self.coordinator.data.get("static_switches", {})
        return states.get(self.entity_description.key) == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._last_action_time = time.time()
        self._pending_on = True
        self.async_write_ha_state()
        
        body = {"func_name": "acl_mac", "action": "up", "param": {"id": self._mac_id}}
        await self.coordinator.async_control_device(body)

    async def async_turn_off(self, **kwargs) -> None:
        self._last_action_time = time.time()
        self._pending_on = False
        self.async_write_ha_state()
        
        body = {"func_name": "acl_mac", "action": "down", "param": {"id": self._mac_id}}
        await self.coordinator.async_control_device(body)

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.time() - self._last_action_time >= 5:
            self._update_attr()
            super()._handle_coordinator_update()