<!-- @format -->

# MQTT认证配置指南

## 概述

本程序支持两种MQTT认证方式，可以兼容大多数IoT平台的MQTT服务器。

## 方式一：私钥模式

这种方式主要兼容巴法云等使用私钥作为客户端ID的平台。

-   **适用平台**：巴法云、部分自定义MQTT服务器
-   **配置方式**：
    -   认证模式：选择"私钥模式"
    -   网站：填写MQTT服务器地址（如：bemfa.com）
    -   密钥：填写私钥
    -   端口：通常为9501（巴法云）
-   **连接原理**：使用私钥作为MQTT客户端ID进行连接，不设置用户名和密码

## 方式二：账号密码模式

这是标准的MQTT认证方式，适用于大多数IoT平台。

-   **适用平台**：阿里云IoT、腾讯云IoT、AWS IoT、华为云IoT、小米IoT、涂鸦智能等
-   **配置方式**：
    -   认证模式：选择"账号密码模式"
    -   网站：填写MQTT服务器地址
    -   用户名：填写平台提供的用户名/设备ID/AppID
    -   密码：填写平台提供的密码/密钥/SecretKey
    -   客户端ID：填写设备ID或留空使用用户名
    -   端口：根据平台要求（通常为1883或8883）

当私钥模式无法正常连接时，可以尝试使用这种方式。

-   **配置方式**：
    -   认证模式：选择"账号密码模式"
    -   网站：填写 `bemfa.com`
    -   用户名(appID)：填写您的appID
    -   密码(secretKey)：填写您的secretKey
    -   客户端ID：可选，可以自定义或留空
    -   端口：通常为 9501

## 配置文件示例

### 私钥模式配置

```json
{
	"broker": "bemfa.com",
	"secret_id": "your_private_key_here",
	"port": 9501,
	"auth_mode": "private_key"
}
```

### 账号密码模式配置

```json
{
	"broker": "bemfa.com",
	"secret_id": "your_private_key_here",
	"port": 9501,
```

## 常见IoT平台配置参考

### 阿里云IoT平台
```json
{
	"broker": "your_product_key.iot-as-mqtt.cn-shanghai.aliyuncs.com",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_device_name&your_product_key",
	"mqtt_password": "your_device_secret",
	"client_id": "your_product_key.your_device_name"
}
```

### 腾讯云IoT Hub
```json
{
	"broker": "your_product_id.iotcloud.tencentdevices.com",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_product_id;your_device_name",
	"mqtt_password": "your_device_secret",
	"client_id": "your_product_id;your_device_name"
}
```

### 华为云IoT平台
```json
{
	"broker": "your_platform_address",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_device_id",
	"mqtt_password": "your_device_secret",
	"client_id": "your_device_id"
}
```

## 使用说明

1. **GUI配置**：
    - 打开RC-GUI配置程序
    - 在"系统配置"区域选择合适的认证模式
    - 在"MQTT认证配置"区域填写相应的认证信息
    - 点击保存配置

2. **自动切换**：
    - 选择"私钥模式"时，账号密码配置会自动禁用
    - 选择"账号密码模式"时，账号密码配置会自动启用

3. **兼容性**：
    - 私钥模式兼容巴法云等特殊平台
    - 账号密码模式支持标准MQTT协议的各种IoT平台

## 故障排除

1. **连接失败**：
    - 检查网络连接是否正常
    - 确认服务器地址和端口正确
    - 验证认证信息是否正确

2. **认证失败**：
    - 私钥模式：确认私钥格式和内容正确
    - 账号密码模式：确认用户名密码正确

3. **主题订阅失败**：
    - 检查主题名称是否正确
    - 确认平台控制台中已创建对应主题
    - 注意不同平台的主题命名规范

## 注意事项

1. **安全性**：
    - 密码在配置文件中以明文存储，请妥善保管配置文件
    - 建议设置适当的文件权限

2. **端口选择**：
    - 巴法云通常使用9501端口
    - 其他平台通常使用1883端口（未加密）或8883端口（SSL加密）

3. **客户端ID**：
    - 私钥模式：客户端ID就是私钥值
    - 账号密码模式：客户端ID可以自定义，留空则使用用户名
    - 某些平台要求特定的客户端ID格式

4. **配置修改**：
    - 修改认证配置后需要重启程序才能生效
    - 建议先在对应平台的控制台测试连接
    - 私钥模式：客户端ID就是私钥值
    - 账号密码模式：客户端ID可以自定义，留空则使用用户名

4. **配置修改**：
    - 修改认证配置后需要重启程序才能生效
    - 建议先在巴法云控制台测试连接

4. **连接测试**：
    - 配置完成后，启动主程序观察日志
    - 连接成功会显示"MQTT 成功连接至 xxx"
    - 连接失败会显示相应的错误信息
