[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![ha-inkwavemap version](https://img.shields.io/badge/ikuai-2024.8.26-blue.svg)](https://github.com/dscao/ikuai)

### ha custom_component iKuai

iKuai router Obtains data generating entities through the Web.

1. Sensor entities such as network information
2. Restart ikuai and reconnect to the network function
3. Behavior control—MAC enable and disable switch in the MAC access control list
4. The device_tracker entity that supports whether the terminal device is online or not, configure the mac address in const.py.

iKuai路由器通过Web获取数据生成实体。

1. 网络信息等传感器实体
2. 重启ikuai并重新连接网络功能
3. 行为控制—MAC访问控制列表中的MAC开启禁用开关
4. 支持终端设备是否在线的device_tracker实体，在const.py中配置mac地址。
5. 更多自定义的开关实体可在 const.py中配置，只需要参考填写抓包中的对应参数。

#### 设备跟踪器配置

支持通过 configuration.yaml 显式配置设备跟踪器。配置后需要重启 Home Assistant

##### 配置示例

在你的 configuration.yaml 中添加：

```yaml
ikuai:
  device_trackers:
    my_phone:
      name: "iPhone13"
      mac_address: "01:02:03:04:05:06"
      icon: "mdi:cellphone"
      disconnect_refresh_times: 2
```

##### 参数说明

- **设备ID** (如 `my_phone`): 唯一标识符，用于内部识别
- **name**: Home Assistant 中显示的实体名称（必需）
- **mac_address**: 设备MAC地址（必需）
- **icon**: 图标，默认为 `mdi:cellphone`（可选）
- **disconnect_refresh_times**: 断线刷新次数，默认为 2（可选）
- **label**: 设备标签，仅用于用户参考（可选）

#### iKuai 自定义开关配置

iKuai 集成现在支持通过 `configuration.yaml` 配置自定义开关。

##### 配置方法

在您的 `configuration.yaml` 文件中添加以下配置：

```yaml
ikuai:
  custom_switches:
    # 自定义开关示例 - NAS 分流
    nas_flow_to_world:
      label: "NAS分流"
      name: "Nas_flow_to_world"
      icon: "mdi:nas"
      turn_on_body:
        func_name: "stream_ipport"
        action: "up"
        param:
          id: 5
      turn_off_body:
        func_name: "stream_ipport"
        action: "down"
        param:
          id: 5
      show_body:
        func_name: "stream_ipport"
        action: "show"
        param:
          TYPE: "data"
          limit: "0,20"
          ORDER_BY: ""
          ORDER: ""
          FINDS: "comment"
          KEYWORDS: "nasflow"
      show_on:
        enabled: "yes"
      show_off:
        enabled: "no"
    
    # 另一个自定义开关示例
    custom_rule_example:
      label: "自定义规则示例"
      name: "Custom_rule"
      icon: "mdi:toggle-switch"
      turn_on_body:
        func_name: "your_function"
        action: "enable"
        param:
          setting: 1
      turn_off_body:
        func_name: "your_function"
        action: "disable"
        param:
          setting: 0
```

## 配置参数说明

### 必需参数

- `label`: 开关在 Home Assistant 中显示的友好名称
- `name`: 开关的内部名称（用于与 iKuai API 通信）
- `turn_on_body`: 打开开关时发送给 iKuai API 的请求体
- `turn_off_body`: 关闭开关时发送给 iKuai API 的请求体

### 可选参数

- `icon`: 开关的图标（默认: `mdi:toggle-switch`）
- `show_body`: 查询开关状态时发送的请求体
- `show_on`: 判断开关为"开启"状态的条件
- `show_off`: 判断开关为"关闭"状态的条件

![1](https://user-images.githubusercontent.com/16587914/202218050-66b21a3d-60c8-4081-bfd0-406fcec1a019.jpg)

![2](https://user-images.githubusercontent.com/16587914/202218076-b0189994-d7de-491c-8a19-dbe0defeafe9.jpg)

![3](https://user-images.githubusercontent.com/16587914/205011464-061dbef5-992c-435e-b2c6-b308252f2efe.jpg)
