# 四个Runner工具的MCP设计示例

本目录是协议契约样例，不是服务器实现。`tools.list.json`中只有四个工具；`01`至`04`是对应的tools/call请求。提交保留原parameter/payload；幂等键是额外的协议映射参数。

`transfer-fixture.abc` 仅供文件字节校验，非模型产物。上传示例先签发一次性 PUT URL，再由本地 `curl` 读取该文件；签发成功不等于上传完成。下载的 inline 结果仍可用 Base64 还原原文件；link 结果明确 `bytes_included=false`，示例 `.invalid` 地址不可访问。

调用侧负责执行上传命令、下载解码和文件保存。上传文件不进入 MCP JSON；服务端 PUT 路由有界接收并在登记后返回资产信息。下载不得在 MCP 消息中无界内联。

继承的音乐Schema仅用于验证音乐部署样例，不能代替实际Runner按部署授权开放的任务注册表。认证来自传输上下文；填写user_id不代表获得该身份。
