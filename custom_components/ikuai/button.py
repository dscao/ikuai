"""Support for iKuai button entities."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BUTTON_TYPES, IkuaiButtonEntityDescription
from .coordinator import IKUAIDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iKuai button entities."""
    coordinator: IKUAIDataUpdateCoordinator = entry.runtime_data
    async_add_entities(IkuaiButton(coordinator, desc) for desc in BUTTON_TYPES)

class IkuaiButton(CoordinatorEntity[IKUAIDataUpdateCoordinator], ButtonEntity):
    """iKuai 操作按钮."""
    entity_description: IkuaiButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{coordinator.host}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """执行按钮动作."""
        await self.coordinator.async_control_device(self.entity_description.action_body)