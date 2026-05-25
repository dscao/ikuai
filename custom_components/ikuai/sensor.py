"""Support for iKuai sensor entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TYPES, IkuaiSensorEntityDescription
from .coordinator import IKUAIDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iKuai sensor entities from a config entry."""
    # 从 runtime_data 获取协调器
    coordinator: IKUAIDataUpdateCoordinator = entry.runtime_data

    # 基于描述符批量创建实体
    async_add_entities(
        IkuaiSensor(coordinator, description)
        for description in SENSOR_TYPES
    )


class IkuaiSensor(CoordinatorEntity[IKUAIDataUpdateCoordinator], SensorEntity):
    """Define an iKuai sensor entity."""

    entity_description: IkuaiSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IKUAIDataUpdateCoordinator,
        description: IkuaiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        
        # 唯一 ID：由域名、描述符 key 和主机地址组成
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{coordinator.host}"
        
        # 引用协调器统一定义的设备信息
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> Any:
        """返回传感器的当前状态值."""
        if not self.coordinator.data:
            return None
            
        # 逻辑：直接通过描述符的 key 从清洗后的数据字典中取值
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回扩展属性."""
        attrs = {}
        data = self.coordinator.data
        if not data:
            return attrs

        attr_key = f"{self.entity_description.key}_attrs"
        if data.get(attr_key):
            attrs.update(data[attr_key])
            
        return attrs