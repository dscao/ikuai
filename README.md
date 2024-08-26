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


![1](https://user-images.githubusercontent.com/16587914/202218050-66b21a3d-60c8-4081-bfd0-406fcec1a019.jpg)

![2](https://user-images.githubusercontent.com/16587914/202218076-b0189994-d7de-491c-8a19-dbe0defeafe9.jpg)

![3](https://user-images.githubusercontent.com/16587914/205011464-061dbef5-992c-435e-b2c6-b308252f2efe.jpg)
