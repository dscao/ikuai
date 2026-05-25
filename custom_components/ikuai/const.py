"""Constants for the iKuai integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.const import (
    Platform,
    UnitOfDataRate,
    UnitOfInformation,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)

DOMAIN: Final = "ikuai"
PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.DEVICE_TRACKER,
]

# 配置键名
CONF_PASS: Final = "pas"
CONF_UPDATE_INTERVAL: Final = "update_interval_seconds"
CONF_ACT_BUFFER: Final = "act_buffer"
CONF_TRACKER_CONFIG: Final = "tracker_config"
CONF_SOURCE_MODE: Final = "source_mode"
CONF_CUSTOM_SWITCHES: Final = "custom_switches"

MODE_UI: Final = "mode_ui"
MODE_CONST: Final = "mode_const"

# API 路径
LOGIN_URL: Final = "/Action/login"
ACTION_URL: Final = "/Action/call"

@dataclass(frozen=True, kw_only=True)
class IkuaiSensorEntityDescription(SensorEntityDescription):
    """描述 iKuai 传感器."""

@dataclass(frozen=True, kw_only=True)
class IkuaiButtonEntityDescription(ButtonEntityDescription):
    """描述 iKuai 按钮逻辑."""
    action_body: dict

@dataclass(frozen=True, kw_only=True)
class IkuaiSwitchEntityDescription(SwitchEntityDescription):
    """描述 iKuai 开关逻辑."""
    turn_on_body: dict
    turn_off_body: dict
    show_body: dict
    show_on: dict
    show_off: dict

# 传感器定义
SENSOR_TYPES: Final[tuple[IkuaiSensorEntityDescription, ...]] = (
    IkuaiSensorEntityDescription(
        key="ikuai_uptime",
        name="Uptime",
        translation_key="uptime",
        icon="mdi:clock-time-eight",
        # device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_cpu",
        name="CPU Usage",
        translation_key="cpu_usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_cputemp",
        name="CPU Temperature",
        translation_key="cpu_temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_memory",
        name="Memory Usage",
        translation_key="memory_usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_online_user",
        name="Online Users",
        translation_key="online_users",
        icon="mdi:account-multiple",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_ap_online",
        name="AP Online",
        translation_key="ap_online",
        icon="mdi:access-point",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_total_up",
        name="Total Upload",
        translation_key="total_upload",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_total_down",
        name="Total Download",
        translation_key="total_download",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_upload",
        name="Upload Speed",
        translation_key="upload_speed",
        icon="mdi:wifi-arrow-up",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_download",
        name="Download Speed",
        translation_key="download_speed",
        icon="mdi:wifi-arrow-down",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_connect_num",
        name="Connection Count",
        translation_key="connection_count",
        icon="mdi:lan-connect",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_ip",
        name="Current Device IP",
        translation_key="ikuai_ip",
        icon="mdi:ip-network-outline",
    ),
    IkuaiSensorEntityDescription(
        key="ikuai_wan_uptime",
        name="WAN Uptime",
        translation_key="wan_uptime",
        icon="mdi:timer-sync-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
)

# 按钮定义
BUTTON_TYPES: Final[tuple[IkuaiButtonEntityDescription, ...]] = (
    IkuaiButtonEntityDescription(
        key="ikuai_restart",
        name="Restart Router",
        translation_key="restart_router",
        device_class=None,
        action_body={"func_name": "reboots", "action": "reboots"},
    ),
    IkuaiButtonEntityDescription(
        key="ikuai_reconnect_wan",
        name="Reconnect WAN",
        translation_key="reconnect_wan",
        icon="mdi:wan",
        action_body={"func_name": "wan", "action": "link_pppoe_reconnect", "param": {"id": 1}},
    ),
)
# 开关定义
SWITCH_TYPES: Final[tuple[IkuaiSwitchEntityDescription, ...]] = (
    IkuaiSwitchEntityDescription(
        key="ikuai_arp_filter",
        name="ARP Filter",
        translation_key="arp_filter",
        icon="mdi:account-lock",
        turn_on_body={"func_name": "arp", "action": "seting", "param": {"arp_filter": 1}},
        turn_off_body={"func_name": "arp", "action": "seting", "param": {"arp_filter": 0}},
        show_body={"func_name": "arp", "action": "show", "param": {"TYPE": "options"}},
        show_on={"arp_filter": 1},
        show_off={"arp_filter": 0},
    ),
    IkuaiSwitchEntityDescription(
        key="ikuai_stream_control",
        name="Stream Control",
        translation_key="stream_control",
        icon="mdi:network-outline",
        turn_on_body={"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 1}},
        turn_off_body={"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 0}},
        show_body={"func_name": "stream_control", "action": "show", "param": {"TYPE": "stream_ctl_mode"}},
        show_on={"stream_ctl_mode": 1},
        show_off={"stream_ctl_mode": 0},
    ),
)