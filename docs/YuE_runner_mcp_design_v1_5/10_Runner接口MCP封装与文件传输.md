# Runner 接口 MCP 封装与文件传输

**版本：1.6｜日期：2026-09-18｜修正远程上传边界；未实现或部署 MCP endpoint。**

## 1. 目标与边界

将 agent-sandbox 的四个 Runner 接口作为四个 MCP 工具对外暴露。MCP 是任务服务的另一种调用入口，位于 API 一侧，不是模型执行后端。v1.4 的外部执行链设计撤回，本版取代其 MCP 文档、配置、示例和第四张时序图。

```text
Claude plugin Skill
    → agent-sandbox /mcp
    → 四个 Runner 工具
    → 同一套 Runner 业务函数
    → 原有队列、Task、preprocess、模型环境与文件记录

已有 HTTP 调用 → 原 /runner/* 路由 → 同一套 Runner 业务函数
```

不因 MCP 新增 Task、Processor、模型环境、后端 job ID、文件桥接服务或第二个队列。MCP 只封装 agent-sandbox 已有 Runner 能力，不引入其他运行服务。

原模型绑定保持：

```text
yue2_task       → yue2_processor       → /root/yue-env/bin/python
sheetsage2_task → sheetsage2_processor → /root/sheetsage2-env/bin/python
```

这里的模型任务是前版已确定的待实施适配；本次没有将其标记为已上线。

## 2. 四个接口一一映射

工具名为本版拟议名称，均通过同一个 `/mcp` endpoint 的 `tools/call` 调用；不是再增加四条 HTTP 路由。

| 既有／已规划 HTTP 能力 | MCP 工具 | MCP 参数与返回 |
|---|---|---|
| `POST /runner/upload`（前版已规划） | `runner_upload` | `file_path`、`client_os`；返回一次性、短效 PUT URL 与本地 `curl` 命令；PUT 成功后返回 `asset_id/sha256/size_bytes` |
| `POST /runner/submit` | `runner_submit` | 保留原 `parameter`、`payload`；可选 `idempotency_key` 对应 HTTP 的请求键；返回相同 `task_id` 和接受状态 |
| `GET /runner/result` | `runner_result` | `task_id`；返回同一任务状态及 `data.result.artifacts` 资源清单 |
| `GET /runner/result_source` | `runner_result_source` | `task_id`、`result_source_name`；新增仅用于传输选择的 `mode=auto/inline/link`；返回原文件字节的编码或原下载入口的资源链接 |

`parameter/payload`、上传 `asset_id`、服务 `task_id`、清单 `result_source_name` 都不另起一套命名空间。MCP JSON-RPC `id` 只关联一次协议调用，不作为任务 ID、请求去重键或用户身份。协议工具发现、调用和结果结构依据官方 Tools 规范；上述工具名和参数是本项目设计，不是 MCP 内置方法。[MCP01]

## 3. 共用业务实现，不复制调度逻辑

将路由中需要复用的业务动作提取为内部函数，或直接复用已有等价函数。拟议名称为 `upload_input`、`submit_task`、`get_task_result`、`open_task_resource`；名称不代表源码中已经存在。

HTTP 路由和 MCP 工具均传入认证主体，调用同一业务函数。HTTP 层处理 multipart、查询参数、HTTP 状态和 FileResponse；MCP 层处理 JSON 参数、文件编码、工具结果及 `isError`。业务函数仍负责用户隔离、路径约束、参数校验、请求键、入队、状态和文件寻址。

下载业务函数返回经过授权的文件句柄／文件描述和元数据，由两种协议分别输出；不要把 FastAPI 的 `FileResponse` 对象直接塞进 MCP JSON。上传同样接受流或受控临时文件，不能把 JSON 字符串假装成跨机器可访问的路径。

适配器不得自行再运行一次 prepare、创建第二个任务标识、重新入队，或直接调用模型脚本。MCP 工具错误不能绕过原 HTTP 路由的认证及 Task 白名单。工具发现只列当前部署实际允许的工具，任务授权继续由原提交逻辑处理。

## 4. 上传适配：云端签发，本地客户端主动上传

### 4.1 agent-sandbox 目标流程

`runner_upload(file_path, client_os)` 不在 MCP 消息中传 Base64，也不让远程服务器读取调用方路径。工具只校验路径元数据，随后在 agent-sandbox 的 MCP HTTP 服务签发一次性、短效 PUT URL，并返回已经引用本地路径的 `curl` 或 `curl.exe` 命令。

```text
Claude plugin Skill → runner_upload(file_path, client_os)
agent-sandbox /mcp → 返回一次性、短效 PUT URL 与 curl 命令
本地 AI 客户端 → 执行 curl，读取本机文件并 PUT
/api/uploads/{token} → owner-only 临时文件 → Runner 共用 upload_input
Runner 资产库 → 返回 asset_id、sha256、size_bytes
Claude plugin Skill → 将 asset_id 写入 runner_submit
```

URL 采用五分钟有效期和单次使用语义；具体文件上限沿用 Runner 上传配置。token 本身就是上传授权，PUT 不附加 Authorization。服务先消费 token，再有界流式写入 owner-only 临时文件，并在所有退出路径清理临时目录。只有共用上传函数完成用户隔离、摘要计算和资产登记后，才返回资产信息。

### 4.2 Runner 对应适配

`runner_upload(file_path, client_os)` 的完整控制流如下：

```text
Claude plugin Skill → runner_upload(file_path, client_os)
agent-sandbox /mcp → 签发 /api/uploads/{token} 与 curl/curl.exe 命令
Skill 所在本地客户端 → 执行命令并直接读取本机文件
/api/uploads/{token} → 消费 token → owner-only 临时文件 → upload_input
Runner 资产库 → 按认证主体隔离并登记
PUT 响应 → asset_id、sha256、size_bytes
Claude plugin Skill → 将 asset_id 放入 runner_submit
```

`file_path` 只用于生成客户端命令和取得安全文件名；远程服务不打开该路径。`/api/uploads/{token}` 是同一 HTTP 应用的传输适配路由，不是第五个 Runner 业务接口。原 `POST /runner/upload` 继续供直接 HTTP 客户端使用，并与 PUT 路由共用上传函数、权限检查和资产登记。

只取得命令不算完成，临时落盘也不算完成；PUT 返回 `asset_id`、`sha256`、`size_bytes` 后资产才可提交。URL 已使用、过期、篡改、超限或传输失败时，重新调用 `runner_upload`；不能重跑旧命令、补 Authorization 或直接提交。反向代理必须同时转发 `/mcp` 与 `/api/uploads/`，并提供可信的完整公开 origin。

## 5. 下载适配：同一任务同一资源

先调用 `runner_result(task_id)` 取得资源清单，选择清单中的 `result_source_name`，再调用 `runner_result_source`。工具读取前仍检查用户归属、资源名称白名单、文件是否完整且可读取。不能以 `task_id` 可猜测、MCP 已连接或 URI 存在作为授权依据。

| `mode` | 行为 | 字节交付状态 |
|---|---|---|
| `auto`（默认） | 小于或等于内联上限返回 Base64；更大文件返回 `resource_link` | 结果中的 `delivery` 明确为 `inline` 或 `link` |
| `inline` | 对同一文件作有界读取，返回无损 Base64 与原文件元数据；超限报错 | `bytes_included=true`，不代表调用侧已保存到本地 |
| `link` | 返回指向原 `GET /runner/result_source?task_id=...&result_source_name=...` 的 HTTPS 资源链接及元数据 | `bytes_included=false`，不能报告“下载完成” |

内联结果放入 MCP `structuredContent`，字段包含 `code/msg/data`，`data` 内含 `delivery/encoding/content_base64` 和文件名、媒体类型、字节数、SHA256；为兼容仅显示文本结果的客户端，同步提供序列化 JSON 文本。该方式是本项目的工具数据契约，不是把任意文件误标成图片或音频内容块。

链接结果使用标准 `resource_link` 加结构化元数据，不创建额外 `/files` 路由或通用 `resources/read` 平台。链接由配置的公共服务基址与受控 query 参数构造，不信任入站 Host 头或调用方 URL。链接不携带长期凭据；调用侧访问原下载接口时使用该接口接受的认证凭据。不能假设每个 MCP 客户端会自动替资源链接带认证，缺少能力时明确显示“需要授权下载”。[MCP01]

完整音乐优先使用链接与原 HTTP 文件流。HTTP 下载保持正确媒体类型及文件名；调用侧写临时文件，核对实际大小与 SHA256 后完成本地保存。Base64 内联同样校验解码后的原始字节，不经过有损格式转换。元数据来自实际产物记录，不使用示例摘要冒充验证结果。

重复下载只读取同一文件；不调用 submit，不重新采样，不做隐式发布或修复。缺失、损坏、过期、无权限分别返回明确错误。Range、断点传输和自动持久下载均不在未验证时宣称支持。

## 6. 任务状态、错误与权限

`runner_submit` 接受后立即返回原 `task_id`；原 Runner 继续执行。`runner_result` 每次只查询一次，Skill 沿原有限等待规则组织查询，MCP 适配器不另建任务轮询队列。断开 MCP 或停止等待不等于取消服务端已接受的任务。

HTTP 与 MCP 对同一主体、同一请求键、同一规范化参数必须得到同一任务。MCP 的 `idempotency_key` 进入同一去重函数，不能把 JSON-RPC `id` 当键。请求键存在于前版设计，仍需业务实现与并发测试后才能承诺生效；禁止遇到协议错误自动改用 HTTP 再提交一次。

业务操作拒绝返回 `isError=true` 和原错误类别；鉴权失败在传输入口执行。合法状态查询即使读到任务 `info=error`，查询本身仍成功：`isError=false`，保留任务失败状态，不混淆协议失败与模型失败。非法工具名或协议参数按 SDK 协议错误处理。

下载链接模式也必须先授权。身份从每次请求的认证上下文取得，不从工具参数自证；工具 `user_id` 或 payload 中旧用户字段必须核对。同一主体跨 HTTP/MCP 能读取同一资产与任务，不同主体都被拒绝。只读工具的 annotations 仅用于描述，不代替权限控制。[MCP01]

## 7. MCP endpoint 与配置

推荐把官方 SDK 提供的 MCP HTTP 应用挂载到 agent-sandbox 现有 ASGI 应用的 `/mcp`，共用服务生命周期和业务函数。保持原 HTTP 路由；MCP 关闭时原任务服务仍可启动。正确组合子应用 lifespan 与路径前缀，避免重复变成 `/mcp/mcp`。这是部署设计，未实际完成挂载。

采用 Streamable HTTP；本版将 **2025-11-25** 作为一个明确的互操作测试基线，不声称它是当前最新版本或所有版本均兼容。具体协议协商、GET/SSE、会话及关闭行为由锁定 SDK 对应版本实现，不从不同版本拼装规则。上线前执行 TLS、Origin/Host、认证、请求大小、超时及资源权限测试。[MCP02]

现有依赖与 MCP SDK 的兼容性需要先在独立测试环境求解和回归；不能未经验证升级主服务，也不因为 MCP 新建一个模型环境。优先同应用挂载，若依赖检查不通过，明确保留部署阻塞而非默默引入另一执行架构。

配置只增加现有 bootstrap 配置项中的 `mcp`，不向 preprocess/tasks 增加注册：

```yaml
# 拟议增量；合并到已有 bootstrap 列表项，不覆盖原字段
bootstrap:
  - runner_bootstrap_web:
      name: runner_bootstrap_web
      mcp:
        enabled: true
        path: /mcp
        transport: streamable-http
        public_base_url: https://runner.example.invalid
        tools: [runner_upload, runner_submit, runner_result, runner_result_source]
        upload_capability_path: /api/uploads/{token}
        upload_ttl_seconds: 300
        max_request_bytes: 1048576
```

`public_base_url` 为占位部署地址；真实凭据复用 Runner 配置，不加入工具参数或下载 URI。这里所有 `mcp` 子字段均为拟新增。

## 8. 文件级实施清单

| 位置 | 状态与改动 | 必要性／兼容检查 |
|---|---|---|
| `sandbox/server/mcp_api.py` | **拟新增**；注册四个工具、Schema、文件编码及 MCP 结果映射 | 不创建任务执行器；每个工具只调用对应 Runner 业务函数 |
| `sandbox/server/runner_service.py` | **必要时拟新增**；提取原提交、查询、资源打开函数 | 已有等价函数则直接复用；HTTP/MCP 不重复 prepare、入队或校验 |
| `sandbox/server/servlet/runner.py` | **已有**；改为复用共同业务函数，保留三条已有路由 | 原 `code/msg/data` 与状态含义保持 |
| `sandbox/server/servlet/extract_file.py`、前版 `runner_assets.py` | **已有位置及前版拟新增模块**；通用上传和资产登记供两个入口共享 | 用户隔离、同名上传、完整写入后登记 |
| `sandbox/server/servlet/boot/runner_bootstrap.py`、`server_init.py` | **已有**；读取 mcp 配置，挂载与管理生命周期 | 关闭 MCP 的旧启动方式回归；正确认证和挂载前缀 |
| `sandbox.yaml` | **已有**；只在既有 bootstrap 项增加 mcp 字段 | preprocess/tasks 原模型绑定不变 |
| `pyproject.toml` 与依赖锁定文件 | **已有位置；锁文件是否存在实施时核对**；选择实际兼容 SDK | 先求解和回归，不照抄参考仓库版本 |
| Skill 的 `SKILL.md` 与 `references/service-api.md` | **前版封装规格**；增加 HTTP/MCP 一一映射和文件传输说明 | 原业务步骤不变；不增加调用方业务层 |
| `tests/mcp/test_runner_tools.py`、`test_runner_files.py`、`test_transport.py` | **拟新增测试** | 以下 M01–M12 |

## 9. 验证计划与验收条件

| 编号 | 验证内容 | 通过条件 |
|---|---|---|
| M01 | endpoint 启停、握手、tools/list | `/mcp` 可调用且仅暴露四个本项目工具；关闭后原 HTTP 服务正常 |
| M02 | HTTP 与 MCP 提交相同请求键 | 同主体得到同一个 task_id，只入队一次；不新增 Task 类型 |
| M03 | 跨入口上传与消费 | MCP 上传的资产可经 HTTP submit 使用，HTTP 上传可经 MCP submit 使用 |
| M04 | token 过期、复用、篡改、超限或中断 | 无可用半成品资产；失败后必须重新签发，且不启动模型 |
| M05 | 客户端路径、本地 PUT 与同名上传 | 远端不读取 `file_path`；本地上传逐字节一致；路径穿越被拒绝；同名新资产不覆盖旧文件 |
| M06 | 跨用户上传、查询、读取与链接 | HTTP/MCP 授权一致；不能伪造 user_id 或越权 task_id/resource name |
| M07 | 小文件内联下载 | 解码字节与原文件完全一致；大小、SHA256 正确；无转码 |
| M08 | 大文件链接下载 | 链接指向原 result_source；认证通过后流式获取同一文件；无服务器路径泄露 |
| M09 | 断连和文件下载重试 | 只查询或读取原任务；模型启动次数不增加；不自动跨协议重新提交 |
| M10 | 状态错误与操作错误 | 查询到模型失败不当作 MCP 调用失败；操作失败正确设置 isError |
| M11 | SDK、ASGI 和传输限制 | 依赖、lifespan、TLS、可信公开 origin 及代理后的 `/mcp`、`/api/uploads/` 路由通过 |
| M12 | 原业务完整流程 | 生成、转录翻唱、编辑在相同 Task/preprocess/environment 上完成；原稿与结果交接不变 |

拟新增测试实现后运行：

```bash
python -m pytest -q tests/mcp/test_runner_tools.py tests/mcp/test_runner_files.py tests/mcp/test_transport.py
```

上述测试未执行。本交付的 `tools/check_runner_mcp_design.py` 只校验文档示例、Schema、示例文件字节、配置和时序图结构，不启动 HTTP/MCP 服务，也不验证模型。

## 10. 来源与本次检查范围

本轮沿用 v1.3 包内已记录的 Runner 路由、用户隔离、状态与模型适配证据，没有重新审计整个仓库。源码定位见 [evidence/sources.md](evidence/sources.md)。上传能力签发、本地 PUT、临时文件和资产登记均作为 agent-sandbox 自身的拟议实现，不形成外部运行依赖。

本轮重新查阅官方 Tools 与 Streamable HTTP 规范，确认 JSON 工具调用、结构化结果和资源链接的表达方式。文件编码、内联阈值、四个工具名称和共享业务函数是本项目的拟议选择，均不冒充协议原生参数或已上线功能。

[MCP01]: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
[MCP02]: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
