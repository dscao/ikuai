# Home Assistant Custom Component: iKuai Router (爱快路由器)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![ha-ikuai version](https://img.shields.io/badge/ikuai-2026.1.16-blue.svg)](https://github.com/dscao/ikuai)
[![Maintainer](https://img.shields.io/badge/maintainer-dscao-orange)](https://github.com/dscao)

**iKuai Router** 集成允许将爱快路由器接入 Home Assistant，提供详细的传感器监控、网络控制开关、以及功能强大的设备追踪（Device Tracker）功能。

本集成支持 **UI 图形化配置**（推荐）与 **Const 代码模式**（旧版兼容），并支持极其灵活的设备在线状态追踪策略。

---

## ✨ 功能特性

1.  **全面监控**：
    * **系统信息**：CPU 温度/占用、内存占用、启动时长。
    * **网络状态**：上传/下载速度、总流量、连接数。
    * **接口信息**：WAN IP、WAN IPv6、WAN 在线时长。
    * **终端统计**：在线终端数、AP 在线数。
2.  **控制功能**：
    * **重启控制**：重启路由器、重新拨号 WAN 口。
    * **网络开关**：ARP 绑定限制、流控模式切换、NAS 分流开关。
    * **上网控制**：基于 MAC 地址的上网控制开关（自动发现）。
3.  **高级设备追踪 (Device Tracker)**：
    * 支持 **IP** 和 **MAC** 两种追踪方式。
    * 支持 **Include (包含)** 和 **Exclude (排除)** 两种筛选模式。
    * **独立防抖动**：可为每个设备单独设置“掉线缓冲次数”，防止因设备短暂休眠导致的误报（忽在忽离）。
    * **灵活配置**：支持扫描在线设备选择，或通过文本自定义批量添加。

### 📸 效果预览
![iKuai 仪表盘示例](https://user-images.githubusercontent.com/16587914/205011464-061dbef5-992c-435e-b2c6-b308252f2efe.jpg)

---

## 📦 安装方法

### 方式一：HACS (推荐)
1.  打开 HACS -> **Integrations (集成)**。
2.  点击右上角菜单（三个点） -> **Custom repositories (自定义存储库)**。
3.  添加本仓库地址：`https://github.com/dscao/ikuai`，类别选择 `Integration`。
4.  在 HACS 中搜索 "ikuai" 并下载安装。
5.  重启 Home Assistant。

### 方式二：手动安装
1.  下载本项目代码。
2.  将 `custom_components/ikuai` 文件夹放入你的 HA 配置目录 `config/` 下。
3.  重启 Home Assistant。

---

## ⚙️ 配置指南

集成安装重启后，在 Home Assistant 中点击 **配置** -> **设备与服务** -> **添加集成** -> 搜索 **iKuai**。

### 第一步：初始化连接
* **Host**: 路由器管理地址 (例如 `http://192.168.1.1`)。
* **Username**: 登录用户名。
* **Password**: 登录密码。
* **全局刷新间隔**: 默认为 10 秒。
* **全局默认掉线缓冲**: 默认为 2 次（即设备连续 2 次检测不到才判定为离线）。
* **配置模式**:
    * `UI 界面模式 (推荐)`：所有配置在 HA 界面完成，即时生效。
    * `Const 代码模式`：读取 `const.py` 文件中的配置（适合高级用户，需重启生效）。
<img width="363" height="626" alt="image" src="https://github.com/user-attachments/assets/c42aff64-81f5-4671-9c05-c57d28043555" />

---

## 🖥️ UI 模式配置详解 (推荐)

在初始化完成后，你可以点击集成卡片上的 **“选项 (CONFIGURE)”** 按钮进入主菜单，随时管理设备。

### 菜单功能概览
* **🚀 扫描并追加设备**: 从当前路由器在线列表中勾选设备。
* **📝 手动并追加设备**: 通过文本或网段规则添加设备。
* **⚙️ 管理设备 (修改参数)**: 修改已添加设备的名称和缓冲次数。
* **🗑️ 删除设备**: 移除不再追踪的设备。
* **全局设置**: 修改刷新间隔、全局默认缓冲、切换配置模式。
<img width="372" height="700" alt="image" src="https://github.com/user-attachments/assets/c720385c-dc44-4d25-8d35-c96cdddb2021" />


### 1. 🚀 扫描添加 (Scan Add)
系统会自动拉取当前在线的所有设备列表。
* **Include (包含) 模式**: 仅追踪你勾选的设备。
* **Exclude (排除) 模式**: 追踪 **除了** 你勾选的设备以外的所有设备（即反选）。
    * *注意*：IP 筛选与 MAC 筛选互不影响。例如，你在 IP 选择了排除，仅影响 IP 追踪列表；MAC 列表需单独配置。
<img width="539" height="596" alt="image" src="https://github.com/user-attachments/assets/a25af7eb-a506-4178-b633-a19673df65e9" />


### 2. 📝 自定义添加 (Custom Add)
支持通过特定语法快速批量添加设备，支持网段。

**语法格式说明：**
* **基本格式**: `地址` (使用全局默认缓冲)
* **指定缓冲**: `地址#次数`
* **指定名称**: `地址:名称`
* **全功能**: `地址#次数:名称`

> **关于缓冲次数 (Buffer)**：
> * 设置为 `0`：表示跟随**全局默认缓冲**设置。
> * 设置为 `>0`：表示该设备使用独立的缓冲次数。

**示例：**
```text
# IP 输入示例
192.168.1.5                      (仅IP，使用全局缓冲)
192.168.1.6#5                    (缓冲5次)
192.168.1.8#0:MyPC               (缓冲0即跟随全局，命名为MyPC)
192.168.1.100#10:Server          (缓冲10次，命名为Server)

# 网段输入示例 (仅支持 Include)
192.168.2.0/24#3                 (该网段所有IP均追踪，缓冲3次)

# MAC 输入示例
AA:BB:CC:DD:EE:FF
AA:BB:CC:DD:EE:01#5:MyPhone

```
<img width="494" height="847" alt="image" src="https://github.com/user-attachments/assets/b60ffbdd-3e05-4a18-98e6-113bf26d6563" />


### 3. ⚙️ 管理设备

在此页面，你可以看到所有已配置的设备。

* **第一个输入框**：修改设备在 HA 中的 `name` (实体 ID 会随之改变)。
* **第二个输入框**：修改缓冲次数。
* 留空 或 填 `0`：代表使用**全局默认缓冲**。
* 填入具体数字：代表使用独立缓冲。

---

## 🛠️ Const 代码模式 (高级用户)

如果你习惯通过代码管理配置，可以在初始化时选择 **Const 代码模式**。
你需要手动编辑 `custom_components/ikuai/const.py` 文件中的 `DEVICE_TRACKERS` 字典。

**注意**：修改 `const.py` 后必须**重启 Home Assistant** 才能生效。

```python
# custom_components/ikuai/const.py 示例

DEVICE_TRACKERS = {
    "redmi_k50": {
        "name": "iPhone13_dscao",
        "mac_address": "64:6d:2f:xx:xx:xx",
        "disconnect_refresh_times": 3  # 掉线缓冲次数
    },
    "pc_lan": {
        "name": "Desktop PC",
        "ip_address": "192.168.1.200",
        "disconnect_refresh_times": 2
    },
}

```

---

## ❓ 常见问题 (FAQ)

**Q: 什么是“掉线缓冲 (Disconnect Buffer)”？**
A: 手机等无线设备在锁屏后可能会间歇性断开 WiFi 以省电。如果不设置缓冲，HA 中的状态会频繁在“在家”和“离家”之间跳变。

* 默认缓冲为 2 次。假设刷新间隔 10 秒，设备需要连续 20 秒（2次检测）都离线，才会被判定为 `not_home`。
* 对于常驻供电的设备（如台式机），可以将缓冲设为 1-2 以提高灵敏度。
* 对于休眠频繁的手机，建议设置 3-5 次。

**Q: Exclude (排除) 模式是如何工作的？**
A:

* **IP 排除**: 追踪所有在线 IP，**除了** 你在列表中指定的 IP。
* **MAC 排除**: 追踪所有在线 MAC，**除了** 你在列表中指定的 MAC。
* 两者逻辑独立运行，互不干扰。

**Q: 我修改了 Const 文件，为什么没生效？**
A: Const 模式是硬编码模式，修改 python 文件后，必须**重启 Home Assistant** 才能重新加载配置。如果希望即时修改，请在集成选项中切换回 **UI 模式**。

**Q: 实体显示不可用 (Unavailable)？**
A:

1. 检查路由器是否在线。
2. 检查配置中的用户名密码是否正确。
3. 如果日志提示 `Result: 10001`，说明登录失败。
4. 如果是 Device Tracker 实体，本集成优化了逻辑：即使路由器短暂断连，Tracker 也会显示为“离家”而不是“不可用”，除非集成彻底卸载。

---

## 许可证

Apache License 2.0

