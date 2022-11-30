"""Constants for the ikuai health code integration."""

DOMAIN = "ikuai"

######### CONF KEY
CONF_USERNAME = "username"
CONF_PASSWD = "passwd"
CONF_PASS = "pas"
CONF_HOST = "host"
CONF_TOKEN_EXPIRE_TIME = "token_expire_time"
COORDINATOR = "coordinator"
CONF_UPDATE_INTERVAL = "update_interval_seconds"

UNDO_UPDATE_LISTENER = "undo_update_listener"

##### IKUAI URL
LOGIN_URL = "/Action/login"
ACTION_URL = "/Action/call" 


### Sensor Configuration

SENSOR_TYPES = {
    "ikuai_uptime": {
        "icon": "mdi:clock-time-eight",
        "label": "iKuai启动时长",
        "name": "ikuai_uptime",
    },
     "ikuai_cpu": {
        "icon": "mdi:cpu-64-bit",
        "label": "CPU占用",
        "name": "ikuai_cpu",
        "unit_of_measurement": "%",
    },
     "ikuai_cputemp": {
        "icon": "mdi:thermometer",
        "label": "CPU温度",
        "name": "ikuai_cputemp",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
    },
    "ikuai_memory": {
        "icon": "mdi:memory",
        "label": "内存占用",
        "name": "ikuai_memory",
        "unit_of_measurement": "%",
    },
    "ikuai_online_user": {
        "icon": "mdi:account-multiple",
        "label": "在线终端数",
        "name": "ikuai_online_user",
    },
    "ikuai_ap_online": {
        "icon": "mdi:access-point",
        "label": "AP数",
        "name": "ikuai_ap_online",
    },    
    "ikuai_total_up": {
        "icon": "mdi:upload-network",
        "label": "上传总量",
        "name": "ikuai_totalup",
        "unit_of_measurement": "GB",
    },
    "ikuai_total_down": {
        "icon": "mdi:download-network",
        "label": "下载总量",
        "name": "ikuai_totaldown",
        "unit_of_measurement": "GB",
    },     
    "ikuai_upload": {
        "icon": "mdi:wifi-arrow-up",
        "label": "上传速度",
        "name": "ikuai_upload",
        "unit_of_measurement": "MB/s",
    },
    "ikuai_download": {
        "icon": "mdi:wifi-arrow-down",
        "label": "下载速度",
        "name": "ikuai_download",
        "unit_of_measurement": "MB/s",
    },
    "ikuai_wan_ip": {
        "icon": "mdi:ip-network-outline",
        "label": "WAN IP",
        "name": "ikuai_wan_ip",
    },
    "ikuai_wan_uptime": {
        "icon": "mdi:timer-sync-outline",
        "label": "WAN Uptime",
        "name": "ikuai_wan_uptime",
    },
    "ikuai_wan6_ip": {
        "icon": "mdi:ip-network",
        "label": "WAN IP6",
        "name": "ikuai_wan6_ip",
    },
}


BUTTON_TYPES = {
    "ikuai_restart": {
        "label": "Ikuai重启",
        "name": "ikuai_restart",
        "device_class": "restart",
        "action_body": {"func_name":"wan","action":"link_dhcp_reconnect","param":{"id":1}}
    },
    "ikuai_restart_reconnect_wan": {
        "label": "ikuai重连wan网络",
        "name": "ikuai_reconnect_wan",
        "device_class": "restart",
        "action_body": {"func_name":"wan","action":"link_dhcp_reconnect","param":{"id":1}}
    },
}