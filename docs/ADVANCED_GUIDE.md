# 高阶教程：抓包自定义 iKuai 开关实体

本教程指导高级用户通过浏览器抓包分析 iKuai Web 通信，在 `const.py` 中添加自定义开关实体，实现对任意功能的控制。

> **⚠️ 注意**：修改 `const.py` 后必须**重启 Home Assistant** 才能生效。

## 核心原理

Home Assistant 与 iKuai 的交互本质是模拟浏览器 API 请求：
- **开关 (SWITCH_TYPES)**：需知道"开启指令"、"关闭指令"及"状态查询指令"
- **传感器 (SENSOR_TYPES)**：需知道"数据查询指令"及如何从返回结果提取数据

只要通过浏览器抓取到这些参数，就能在 `const.py` 中添加任意功能实体。

---

## 准备工作

1. 打开集成文件路径：`custom_components/ikuai/const.py`
2. 定位到 `SWITCH_TYPES` 字典定义部分
3. 准备 Chrome 或 Edge 浏览器

---

## 操作步骤：以"智能流控模式"为例

### 1. 准备代码模板

在 `const.py` 的 `SWITCH_TYPES` 中复制现有配置作为模板，修改 `key`（键名）、`icon`（图标）、`label`（中文名称）和 `name`（英文名称）

```python
    "ikuai_stream_control": {
        "icon": "mdi:network-outline",
        "label": "iKuai流控模式",
        "name": "Stream control",
        # 下面的 body 参数将在后续步骤中获取
        "turn_on_body": {}, 
        "turn_off_body": {},
        "show_body": {},
        "show_on": {},
        "show_off": {},
    },

```

### 2. 获取开启指令 (turn_on_body)

1. 浏览器登录爱快后台，进入**网络设置 → 流控分流 → 智能流控**
2. 按 **F12** 打开开发者工具，切换到 **网络 (Network)** 选项卡
3. 过滤器输入 `call` 筛选请求
4. 网页操作：选择"智能模式"并点击**点击生效**
5. 在网络列表中点击最新 `call` 请求，查看**载荷 (Payload)**
6. 确认 `func_name` 为 `stream_control`，复制 JSON 对象
7. 粘贴到 `const.py` 的 `"turn_on_body"` 中
<img width="1407" height="630" alt="image" src="https://github.com/user-attachments/assets/3557213b-15b6-493c-ac35-fbc100b4514f" />

### 3. 获取关闭指令 (turn_off_body)

1. 保持开发者工具开启
2. 网页操作：选择"关闭流控"或"禁用"并点击**点击生效**
3. 在网络列表中找到最新 `call` 请求
4. 复制载荷 JSON，粘贴到 `"turn_off_body"`

### 4. 获取状态查询指令 (show_body)

Home Assistant 需要知道开关当前状态：

1. 按 **F5** 刷新网页，等待加载完成
2. 在网络列表中查找 `action` 为 `show` 且 `func_name` 为 `stream_control` 的`call`请求（通常在加载初期发起）
3. 复制请求载荷 JSON，粘贴到 `"show_body"`
<img width="1385" height="695" alt="image" src="https://github.com/user-attachments/assets/0fa659c1-46ec-4a99-b420-9ebfccd41527" />

### 5. 确定状态判断条件 (show_on / show_off)

根据查询数据判断开关状态：

1. 点击上一步的 `show` 请求，查看**响应 (Response)**
2. 找到代表状态的关键字段（如 `stream_ctl_mode`）
3. 对比开启/关闭返回值：
   - 开启时：`stream_ctl_mode: 1`
   - 关闭时：`stream_ctl_mode: 0`
4. 在 `const.py` 中填写：

```python
        "show_on": {"stream_ctl_mode": 1},
        "show_off": {"stream_ctl_mode": 0},

```

---

## 最终代码示例

```python
SWITCH_TYPES = {
    # ... 其他开关 ...
    
    "ikuai_stream_control": {
        "icon": "mdi:network-outline",
        "label": "iKuai流控模式",
        "name": "Stream control",
        "turn_on_body": {"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 1}},
        "turn_off_body": {"func_name": "stream_control", "action": "seting", "param": {"stream_ctl_mode": 0}},
        "show_body": {"func_name": "stream_control", "action": "show", "param": {"TYPE": "stream_ctl_mode"}},
        "show_on": {"stream_ctl_mode": 1},
        "show_off": {"stream_ctl_mode": 0},
    },
}
```

---

## 🧠 举一反三：自定义按键 (BUTTON_TYPES)

除了有“开/关”状态的开关外，iKuai 中还有许多**“单次触发”**的功能（如重启路由器、WAN 口重拨、清理缓存等）。这类功能在 Home Assistant 中对应为 **Button (按键)** 实体，配置在 `BUTTON_TYPES` 中。

**配置特点：**
相比开关，按键的配置更加简单，只需要抓取点击按钮时发送的**执行指令** (`action_body`)，不需要查询状态。

**抓包与配置示例：**
以“重连 WAN 网络”为例，抓取点击重连时的请求载荷，填入 `action_body` 即可：

```python
# custom_components/ikuai/const.py

BUTTON_TYPES = {
    # ... 其他按键 ...

    "ikuai_restart_reconnect_wan": {
        "label": "重连wan网络",        # HA 显示名称
        "name": "Reconnect_wan",      # 内部标识
        "device_class": "restart",    # 图标/类型样式
        
        # 填入抓包获取的执行参数
        "action_body": {"func_name": "wan", "action": "link_pppoe_reconnect", "param": {"id": 1}}
    },
}

```

## 自定义开关configuration配置 （推荐方式，升级或迁移不影响）
iKuai 集成同时支持通过 configuration.yaml 配置自定义开关。

### 配置方法
在您的 configuration.yaml 或者 packages 目录下任一yaml文件中添加以下配置：

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

```

### 配置参数说明

label: 仅用于代码中标识，方便编写人员识别 \
name: 开关的名称（用于与 iKuai API 通信，尽量用英文字母和下划线） \
turn_on_body: 打开开关时发送给 iKuai API 的请求体 \
turn_off_body: 关闭开关时发送给 iKuai API 的请求体 \

icon: 开关的图标（默认: mdi:toggle-switch） \
show_body: 查询开关状态时发送的请求体 \
show_on: 判断开关为"开启"状态的条件 \
show_off: 判断开关为"关闭"状态的条件


