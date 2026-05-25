"""Support for iKuai device tracker entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_TRACKER_CONFIG
from .coordinator import IKUAIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up iKuai device tracker."""
    coordinator: IKUAIDataUpdateCoordinator = entry.runtime_data
    
    # 获取已配置的追踪列表
    tracker_config = dict(entry.data.get(CONF_TRACKER_CONFIG, {}))
    
    # 兼容模式：MODE_CONST 逻辑
    if entry.data.get("source_mode") == "mode_const":
        try:
            from .const import DEVICE_TRACKERS
            for key, info in DEVICE_TRACKERS.items():
                target = info.get("mac_address") or info.get("ip_address")
                if target and target not in tracker_config:
                    tracker_config[target] = {
                        "name": info.get("name", key),
                        "buffer": info.get("disconnect_refresh_times", 2)
                    }
        except ImportError:
            _LOGGER.debug("DEVICE_TRACKERS not found in const.py")

    if not tracker_config:
        return

    async_add_entities(
        IkuaiTracker(coordinator, tid, conf) 
        for tid, conf in tracker_config.items()
    )
    
class IkuaiTracker(CoordinatorEntity[IKUAIDataUpdateCoordinator], ScannerEntity):
    """iKuai 设备追踪器."""

    _attr_has_entity_name = True
    _attr_translation_key = "ikuai_tracker"

    def __init__(self, coordinator, target_id, info) -> None:
        super().__init__(coordinator)
        self._target_id = target_id
        
        # 获取实时数据中的名称
        data = coordinator.data.get("tracker_map", {}).get(target_id, {})
        # 优先使用实时抓到的 friendly_name，如果没有则使用配置时的名称
        self._attr_name = data.get("friendly_name") or info.get("name") or target_id
        # 唯一 ID
        self._attr_unique_id = f"{DOMAIN}_tracker_{target_id.replace(':', '_')}_{coordinator.host}"

    @property
    def device_info(self) -> DeviceInfo:
        """将实体链接到 iKuai 路由器设备."""
        # 必须直接返回协调器定义的 device_info，确保标识符一致
        return self.coordinator.device_info

    @property
    def source_type(self) -> SourceType:
        """返回追踪来源类型."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """判断设备是否在线."""
        # 从协调器处理好的 map 中查看是否存在
        return self._target_id in self.coordinator.data.get("tracker_map", {})

    @property
    def ip_address(self) -> str | None:
        """返回当前 IP."""
        data = self.coordinator.data.get("tracker_map", {}).get(self._target_id, {})
        return data.get("ip_addr")

    @property
    def mac_address(self) -> str | None:
        """返回当前 MAC."""
        if ":" in self._target_id:
            return self._target_id
        data = self.coordinator.data.get("tracker_map", {}).get(self._target_id, {})
        return data.get("mac")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回详细属性."""
        data = self.coordinator.data.get("tracker_map", {}).get(self._target_id, {})
        if not data:
            return {}
            
        return {
            "ip_address": data.get("ip_addr"),
            "mac_address": data.get("mac"),
            "device_name": data.get("friendly_name"), # 这里就是我们要的名称
            "hostname": data.get("hostname"),
            "upload_speed": f"{data.get('upload', 0)} KB/s",
            "download_speed": f"{data.get('download', 0)} KB/s",
        }