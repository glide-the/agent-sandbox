# YuE2 / SheetSage2 任务服务

本实现将两个模型运行链绑定为独立任务，不在 API 进程中导入 GPU 模型：

- `yue2_task` → `yue2_processor` → `/root/yue-env`
- `sheetsage2_task` → `sheetsage2_processor` → `/root/sheetsage2-env`

部署配置位于 `sandbox.yaml`。YuE 代码固定放在 `/root/apps/YuE`，模型和 Hugging Face 缓存位于 `/root/checkpoint`，任务及上传文件位于 `/root/agent-sandbox-data`。Processor 只执行固定脚本和固定参数，客户端不能指定解释器、脚本、模型路径或服务器文件路径。

## API

所有音乐接口使用 `Authorization: Bearer <token>`。服务端密钥文件保存 SHA-256 摘要到用户主体的映射，例如：

```json
{
  "<sha256-of-token>": "user_demo"
}
```

文件应只允许服务账号读取。令牌、原文及鉴权头不会进入任务请求、命令行或产物。

## MCP 兼容入口

在 `bootstrap.runner_bootstrap_web.mcp.enabled=true` 时，同一 ASGI 服务挂载
Streamable HTTP `/mcp`，并且只暴露四个工具：`runner_upload`、
`runner_submit`、`runner_result` 和 `runner_result_source`。MCP 与 HTTP 共用
认证主体、资产库、幂等记录、队列、任务状态和结果文件，不创建第二种任务 ID，
也不直接运行模型脚本。

`runner_upload(file_path, client_os)` 只校验客户端路径元数据并签发一次性、
短效 `PUT /api/uploads/{token}` 地址及本地 `curl`/`curl.exe` 命令。服务端不会
打开 `file_path`，文件内容也不进入 MCP JSON。客户端在本机执行命令；只有 PUT
返回 `asset_id`、`sha256` 和 `size_bytes` 后才能提交任务。令牌在读取请求体前
消费，过期、复用、篡改、超限或中断后必须重新签发。

`runner_result_source` 的 `mode=auto/inline/link` 控制交付方式：小文件可无损
Base64 内联，较大文件返回原 `/runner/result_source` 的受控链接。链接不携带凭据，
下载时仍需 Runner Bearer token；链接或 Base64 返回只表示可传输，不表示调用侧
已经持久保存文件。

`mcp.public_base_url` 必须配置为反向代理后的可信公开 HTTP(S) origin，代理需同时
转发 `/mcp` 和 `/api/uploads/`。仓库默认关闭 MCP，示例占位地址不能用于部署。
SDK 固定为 MCP Python SDK 1.x 维护线，以兼容设计规定的 2025-11-25 协议基线。

### 上传输入

`POST /runner/upload` 使用 `multipart/form-data`，字段为 `file` 和 `user_id`。`user_id` 必须等于令牌主体。每次上传返回新的 `asset_id`、真实字节数和 SHA-256；同名文件不会覆盖。接口不解压文件，也不启动模型。

### 提交任务

`POST /runner/submit` 保留原有 `parameter + payload` 外壳。音乐请求必须携带 `Idempotency-Key`，相同用户、相同键和相同请求返回原任务；同键不同请求返回 HTTP 409。

`yue2_task` 支持：

- `generate`：文本生成，可通过 `abc_source` 引用上传的 ABC 或已有任务输出。
- `plan`：生成可编辑计划。
- `all_modes`：比较 full/melody/off；只接受文本请求。
- `decode`：通过 `source_task_id` 重解码同用户完整原生结果。
- `score_check`：执行 inspect、strip_chords 或 compare。

`sheetsage2_task` 仅支持 `transcribe`，输入字段为 `audio_asset_id`，转录模式为 `full`、`melody-full` 或 `melody-vocal`。

客户端不得发送 `_service`。该字段由 API 在鉴权、资源绑定和持久化任务 ID 创建之后注入；API 和 Worker 两次 `prepare` 必须得到同一个任务 ID。

### 查询与下载

`GET /runner/result?task_id=...` 返回真实状态。完成结果的 `artifacts` 只公开：

```json
{
  "result_source_name": "audio",
  "filename": "audio.flac",
  "media_type": "audio/flac",
  "size_bytes": 123,
  "sha256": "..."
}
```

使用 `GET /runner/result_source?task_id=...&result_source_name=audio` 下载。名称必须来自清单；服务会再次检查任务归属、路径、字节数和摘要。两个 GET 都是只读操作，不发布文件、不修复记录、也不重新采样。客户端下载应先写 `.part`，核对大小和 SHA-256 后再改名；临时网络错误可重试同一资源，不能重新提交生成。

任务输出作为后续输入时使用 `{task_id, result_source_name}`；用户修改后的文件重新上传并使用 `{asset_id}`。绝对路径不属于公共契约。

## 状态、恢复与清理

任务接受记录先原子写入磁盘，再进入内存队列。Worker 通过原有内部进度接口更新完整状态；模型产物先在 `work/native` 完成，校验后同文件系统移动到 `artifacts/native`，最后写入 `result-manifest.json`。

API 启动时会完成以下恢复：

- 已有完成 manifest 的任务校正为终态；
- 尚未开始的 `pending` 任务恢复入队；
- 已经执行但因服务重启中断的任务标记为 `interrupted`，不会自动重新采样。

Worker 意外退出且存在音乐运行任务时，服务暂停 Worker 重启和后续音乐派发，记录 `worker_crash`。处理遗留模型进程并重启服务后才恢复调度。已结束任务默认保留七天；内存状态清理不删除持久记录。

## 部署和验证

启动前应检查两套解释器、固定 YuE 代码目录、模型目录和缓存目录。生产部署默认 `max_ongoing_tasks=1`。离线子进程设置 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`，并清除服务进程的 `PYTHONHOME/PYTHONPATH` 继承。

本地非 GPU 测试：

```bash
python -m pytest -q tests/music
python -m pytest -q tests/mcp
```

测试使用临时解释器和假脚本验证进程、状态、产物、上传、鉴权、幂等与恢复；假音频带 `synthetic_fixture` 标记，不能视为模型效果验收。

AutoDL 环境检查只能探测解释器、包版本、目录、模型文件完整性和不触发模型的
HTTP/MCP 协议链路。在收到明确指令前，不得加载权重、初始化 CUDA、运行
YuE/SheetSage2 helper 或启动任务服务模型执行。模型文件存在只证明部署输入已准备，
不能将 YuE2 生成或音乐质量标记为已验证。
