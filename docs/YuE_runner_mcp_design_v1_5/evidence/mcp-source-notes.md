# v1.6 修订依据

本轮需求明确要求将四个Runner HTTP能力封装为MCP工具，取代v1.4错误的外部执行链。

Runner 源码事实及模型参数沿用包内 `evidence/sources.md` 记录的固定提交，不声称本轮再次读取整个仓库。MCP 上传、签发 URL、临时落盘与资产登记均为 agent-sandbox 自身的拟议实现，不依赖或引入其他运行服务。

本轮重新查阅官方规范：
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

2025-11-25仅为明确的互操作测试基线；不声称是最新版本或已测试版本。项目自定义字段为拟议工具契约。
