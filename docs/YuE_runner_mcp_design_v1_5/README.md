# YuE任务服务与Runner MCP封装设计 v1.6

本版修正MCP方向：将现有四个Runner能力对外暴露为MCP工具，不增加模型Task、Processor或外部执行后端。v1.4的相关设计撤回。

先读[交付说明](00_交付清单与阅读说明.md)，本次改动集中在[Runner接口MCP封装与文件传输](10_Runner接口MCP封装与文件传输.md)。原模型服务与Skill业务步骤保留。

仅设计交付，未修改业务代码或运行模型。静态检查见evidence/mcp-revision-checks.json；包完整性执行python tools/verify_delivery.py。
