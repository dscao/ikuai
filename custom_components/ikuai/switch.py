"""Support for iKuai switch entities."""
from __future__ import annotations

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

    # 1. 静态内置开关 (const.py)
    for desc in SWITCH_TYPES:
        entities.append(IkuaiStaticSwitch(coordinator, desc))

    # 2. YAML 自定义开关 (原代码功能)
    if hasattr(coordinator, 'yaml_custom_switches'):
        for key, conf in coordinator.yaml_custom_switches.items():
            desc = IkuaiSwitchEntityDescription(
                key=f"custom_{key}",
                name=conf["name"],
                icon=conf.get("icon"),
                turn_on_body=conf["turn_on_body"],
                turn_off_body=conf["turn_off_body"],
                # 对于自定义开关，状态读取通常需要对应的 show_body
                show_body=conf.get("show_body"),
                show_on=conf.get("show_on"),
            )
            entities.append(IkuaiStaticSwitch(coordinator, desc, is_custom=True))

    # 3. 动态 MAC 控制开关 (根据路由器数据生成)
    mac_controls = coordinator.data.get("mac_control_map", {})
    for mac_id in mac_controls:
        entities.append(IkuaiMacControlSwitch(coordinator, mac_id))

    async_add_entities(entities)

class IkuaiStaticSwitch(CoordinatorEntity[IKUAIDataUpdateCoordinator], SwitchEntity):
    """实现内置及自定义功能开关."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, description, is_custom=False) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{coordinator.host}"
        self._attr_device_info = coordinator.device_info
        self._is_custom = is_custom

    @property
    def is_on(self) -> bool:
        # 获取逻辑：从协调器预处理好的 static_switches 中取值
        return self.coordinator.data.get("static_switches", {}).get(self.entity_description.key) == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_control_device(self.entity_description.turn_on_body)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_control_device(self.entity_description.turn_off_body)

class IkuaiMacControlSwitch(CoordinatorEntity[IKUAIDataUpdateCoordinator], SwitchEntity):
    """动态 MAC 控制开关."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, mac_id) -> None:
        super().__init__(coordinator)
        self._mac_id = str(mac_id)
        self._attr_device_info = coordinator.device_info
        self._update_attr()

    def _update_attr(self):
        item = self.coordinator.data.get("mac_control_map", {}).get(self._mac_id, {})
        comment = item.get("comment") or "未备注"
        mac_addr = item.get("mac", "Unknown")
        self._attr_name = f"MAC访问控制: {comment} ({mac_addr})"
        self._attr_unique_id = f"{DOMAIN}_mac_ctrl_{self._mac_id}_{self.coordinator.host}"

    @property
    def is_on(self) -> bool:
        item = self.coordinator.data.get("mac_control_map", {}).get(self._mac_id, {})
        return item.get("enabled") == "yes"

    async def async_turn_on(self, **kwargs) -> None:
        body = {"func_name": "acl_mac", "action": "up", "param": {"id": self._mac_id}}
        await self.coordinator.async_control_device(body)

    async def async_turn_off(self, **kwargs) -> None:
        body = {"func_name": "acl_mac", "action": "down", "param": {"id": self._mac_id}}
        await self.coordinator.async_control_device(body)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attr()
        super()._handle_coordinator_update()