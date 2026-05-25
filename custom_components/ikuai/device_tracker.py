"""Support for iKuai device tracker entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_TRACKER_CONFIG
from .coordinator import IKUAIDataUpdateCoordinator

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    
    # 原代码逻辑：如果模式是 MODE_CONST，尝试加载 const.py 中的 DEVICE_TRACKERS
    tracker_config = entry.data.get(CONF_TRACKER_CONFIG, {})
    
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
            _LOGGER.warning("DEVICE_TRACKERS not found in const.py")

    async_add_entities(IkuaiTracker(coordinator, tid, conf) for tid, conf in tracker_config.items())
    
    
class IkuaiTracker(CoordinatorEntity[IKUAIDataUpdateCoordinator], ScannerEntity):
    """iKuai 设备追踪器."""

    _attr_has_entity_name = True
    _attr_translation_key = "ikuai_tracker"

    def __init__(self, coordinator, target_id, info) -> None:
        super().__init__(coordinator)
        self._target_id = target_id
        self._attr_name = info.get("name")
        self._attr_unique_id = f"{DOMAIN}_tracker_{target_id}_{coordinator.host}"
        self._attr_device_info = coordinator.device_info

    @property
    def source_type(self) -> SourceType:
        """返回追踪来源类型."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """判断设备是否在线（包含缓冲逻辑）."""
        # 只要存在于 map 中，即视为在线（Coordinator 已处理缓冲逻辑）
        return self._target_id in self.coordinator.data.get("tracker_map", {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回设备详细信息."""
        data = self.coordinator.data.get("tracker_map", {}).get(self._target_id, {})
        if not data:
            return {}
            
        return {
            "ip_address": data.get("ip_addr"),
            "mac_address": data.get("mac"),
            "upload_speed": f"{data.get('upload', 0)} KB/s",
            "download_speed": f"{data.get('download', 0)} KB/s",
            "is_buffering": data.get("offline_buffering", False)
        }