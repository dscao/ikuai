"""Constants for the ikuai integration."""

DOMAIN = "ikuai"

######### CONF KEY
CONF_USERNAME = "username"
CONF_PASSWD = "passwd"
CONF_PASS = "pas"
CONF_HOST = "host"
CONF_TOKEN_EXPIRE_TIME = "token_expire_time"
COORDINATOR = "coordinator"
CONF_UPDATE_INTERVAL = "update_interval_seconds"


CONF_ACT_BUFFER = "default_disconnect_times"
CONF_TRACKER_CONFIG = "tracker_config"
CONF_SOURCE_MODE = "source_mode"

MODE_UI = "ui"
MODE_CONST = "const"

UNDO_UPDATE_LISTENER = "undo_update_listener"

##### IKUAI URL
LOGIN_URL = "/Action/login"
ACTION_URL = "/Action/call" 


### Sensor Configuration

SENSOR_TYPES = {
    "ikuai_uptime": {
        "icon": "mdi:clock-time-eight",
        "label": "iKuai启动时长",
        "name": "Uptime",
    },
     "ikuai_cpu": {
        "icon": "mdi:cpu-64-bit",
        "label": "CPU占用",
        "name": "CPU",
        "unit_of_measurement": "%",
    },
     "ikuai_cputemp": {
        "icon": "mdi:thermometer",
        "label": "CPU温度",
        "name": "CPU_temperature",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
    },
    "ikuai_memory": {
        "icon": "mdi:memory",
        "label": "内存占用",
        "name": "Memory",
        "unit_of_measurement": "%",
    },
    "ikuai_online_user": {
        "icon": "mdi:account-multiple",
        "label": "在线终端数",
        "name": "Online_user",
        "unit_of_measurement": "个",
    },
    "ikuai_ap_online": {
        "icon": "mdi:access-point",
        "label": "AP数",
        "name": "Ap_online",
        "unit_of_measurement": "个",
    },    
    "ikuai_total_up": {
        "icon": "mdi:upload-network",
        "label": "上传总量",
        "name": "Totalup",
        "unit_of_measurement": "GB",
    },
    "ikuai_total_down": {
        "icon": "mdi:download-network",
        "label": "下载总量",
        "name": "Totaldown",
        "unit_of_measurement": "GB",
    },     
    "ikuai_upload": {
        "icon": "mdi:wifi-arrow-up",
        "label": "上传速度",
        "name": "Upload",
        "unit_of_measurement": "MB/s",
    },
    "ikuai_download": {
        "icon": "mdi:wifi-arrow-down",
        "label": "下载速度",
        "name": "Download",
        "unit_of_measurement": "MB/s",
    },
    "ikuai_connect_num": {
        "icon": "mdi:lan-connect",
        "label": "连接数",
        "name": "Connect_num",
        "unit_of_measurement": "个",
    },
    "ikuai_wan_ip": {
        "icon": "mdi:ip-network-outline",
        "label": "WAN IP",
        "name": "Wan_ip",
    },
    "ikuai_wan_uptime": {
        "icon": "mdi:timer-sync-outline",
        "label": "WAN Uptime",
        "name": "Wan_uptime",
    },
    "ikuai_wan6_ip": {
        "icon": "mdi:ip-network",
        "label": "WAN IP6",
        "name": "Wan6_ip",
    },
}


BUTTON_TYPES = {
    "ikuai_restart": {
        "label": "Ikuai重启",
        "name": "Restart",
        "device_class": "restart",
        "action_body": {"func_name":"reboots","action":"reboots"}
    },
    "ikuai_restart_reconnect_wan": {
        "label": "重连wan网络",
        "name": "Reconnect_wan",
        "device_class": "restart",
        "action_body": {"func_name":"wan","action":"link_pppoe_reconnect","param":{"id":1}}
    },
}


SWITCH_TYPES = {
    "ikuai_arp_filter": {
        "icon": "mdi:account-lock",
        "label": "iKuai非绑定MAC不允许上网",
        "name": "Arp_filter",
        "turn_on_body": {"func_name":"arp","action":"seting","param":{"arp_filter":1}},
        "turn_off_body": {"func_name":"arp","action":"seting","param":{"arp_filter":0}},
        "show_body": {"func_name":"arp","action":"show","param":{"TYPE":"options"}},
        "show_on": {'arp_filter': 1},
        "show_off": {'arp_filter': 0},
    },
    "ikuai_nas_port_flow_to_world": {
        "icon": "mdi:nas",
        "label": "NAS分流至科学上网",
        "name": "Nas_flow_to_world",
        "turn_on_body": {"func_name":"stream_ipport","action":"up","param":{"id":5}},
        "turn_off_body":{"func_name":"stream_ipport","action":"down","param":{"id":5}},
        "show_body": {"func_name":"stream_ipport","action":"show","param":{"TYPE":"data","limit":"0,20","ORDER_BY":"","ORDER":"","FINDS":"comment","KEYWORDS":"nas科学上网"}},
        "show_on": {'enabled':"yes"},
        "show_off": {'enabled':"no"},
    },
    "ikuai_stream_control": {
        "icon": "mdi:network-outline",
        "label": "iKuai流控模式",
        "name": "Stream control",
        "turn_on_body": {"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 1}},
        "turn_off_body": {"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 0}},
        "show_body": {"func_name":"stream_control","action":"show","param":{"TYPE":"stream_ctl_mode"}},
        "show_on": {"stream_ctl_mode": 1},
        "show_off": {"stream_ctl_mode": 0},
    },    
}

DEVICE_TRACKERS = {
}
