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
4. 网页操作：选择"智能模式"并点击**保存/生效**
5. 在网络列表中点击最新 `call` 请求，查看**载荷 (Payload)**
6. 确认 `func_name` 为 `stream_control`，复制 JSON 对象
7. 粘贴到 `const.py` 的 `"turn_on_body"` 中

### 3. 获取关闭指令 (turn_off_body)

1. 保持开发者工具开启
2. 网页操作：选择"关闭流控"或"禁用"并点击**保存/生效**
3. 在网络列表中找到最新 `call` 请求
4. 复制载荷 JSON，粘贴到 `"turn_off_body"`

### 4. 获取状态查询指令 (show_body)

Home Assistant 需要知道开关当前状态：

1. 按 **F5** 刷新网页，等待加载完成
2. 在网络列表中查找 `action` 为 `show` 且 `func_name` 为 `stream_control` 的`call`请求（通常在加载初期发起）
3. 复制请求载荷 JSON，粘贴到 `"show_body"`

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

## 🧠 举一反三

上述方法同样适用于修改 `SENSOR_TYPES` (传感器)：

### 修改 SENSOR_TYPES
如需添加监控特定接口流量的传感器：
1. 抓包找到网页上显示该数据的 `show` 请求
2. 在 `SENSOR_TYPES` 中配置 `name`, `label`, `unit_of_measurement`
3. 复杂数据提取可能需配合修改 `data_fetcher.py`

### 修改 SWITCH_TYPES
任何"开/关"功能都可添加为开关，例如"允许/禁止 Ping"：
- 抓取"允许 Ping" → `turn_on_body`
- 抓取"禁止 Ping" → `turn_off_body`
- 抓取查询设置 → `show_body`

