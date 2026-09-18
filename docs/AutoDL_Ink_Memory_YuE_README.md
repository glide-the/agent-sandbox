# Ink & Memory + YuE Runner · AutoDL 镜像使用说明

本镜像同时提供 Ink & Memory Dream、Admin 与 YuE Runner。Dream 用于对话与智能体运行，Admin 管理身份、模型、资源策略和业务数据，YuE Runner 提供歌曲生成、音频转谱、乐谱检查与试听比较任务。

统一启动入口只启动已经发布的服务，不执行代码构建、数据库迁移、数据恢复、模型下载、权重加载或 GPU 检测。YuE2 和 SheetSage2 仅在收到对应任务后启动模型子进程。

## 快速开始

### 第一步：启动全部服务

登录 AutoDL 实例后执行：

```bash
bash /root/LaunchTool311/start_all.sh
```

脚本按以下顺序启动并检查服务：

1. Admin；
2. Dream 后端与前端；
3. YuE Runner；
4. 四个本机监听端口和健康端点。

服务已经正常运行时，脚本会保留现有进程，不会重复启动。

### 第二步：打开 Dream 和 Admin

在 AutoDL 实例页面直接点击：

- `WebUI-6006`：Dream；
- `WebUI-6008`：Admin。

实例公开地址由 AutoDL 每次创建实例时重新生成，不应写死在客户端或镜像文档中。

#### Admin 管理员登录

镜像已经初始化并验证以下 Admin 管理员：

- 账号：`dmeck@suoxya.com`；
- 初始密码：`InkAdm!2026-R9vK7mQ2`。

这是 Admin 管理后台账号，只用于 `WebUI-6008`，不是 AutoDL SSH、PostgreSQL 或 YuE Runner 的凭据。统一启动脚本不会创建、重置或覆盖该账号。首次登录后应通过既定的管理员密码恢复流程更换初始密码；如果镜像或本文档将提供给其他人，发布前必须同步轮换密码并更新或移除这里的初始凭据。

### 第三步：在 Admin 配置 Dream 默认模型

Dream 的默认对话／Claude Agent 模型不是镜像内置常量，首次使用前必须在 Admin 完成模型供应链和套餐默认值配置。`bash /root/LaunchTool311/start_all.sh` 只负责启动服务；即使四个健康检查全部通过，也不代表已有可调用的默认模型。

按以下顺序配置：

1. 打开 `WebUI-6008`，使用上面的管理员账号登录。
2. 进入 **AI 模型中心 → Provider**，新增或打开一个 Provider，配置实际的上游账号、Endpoint 和凭据，然后执行“连通测试”。同一产品接入多个上游账号时，应分别创建 Provider。
3. 进入 **AI 模型中心 → Models**，通过 Provider 卡片的“手工添加模型／模型”入口或“＋ 添加模型”注册模型。填写稳定模型 alias 与实际上游型号，启用所需能力和模型，并执行“验证配置”。Dream 和 Gateway 使用稳定 alias，不直接使用上游型号。
4. 进入 **AI 模型中心 → Pricing**，为该模型配置当前有效的价格。模型仅显示“已启用”不代表可以调用；Provider 凭据和有效 Pricing 也必须就绪。
5. 进入 **订阅中心 → 权益**，把该模型加入需要使用的套餐版本，至少启用 `messages:create`，打开“启用权益”，并把“默认模型”设为开启。同一套餐版本最多只能有一个默认模型。
6. 在 **订阅中心 → 版本** 发布配置完成的草稿版本。已发布版本不可覆盖；需要更换默认模型时，创建后继版本、配置权益后再发布。
7. 回到 Dream 的模型设置页面确认模型可见且可调用。用户已经保存并且仍可调用的模型优先；只有没有有效保存值时，Claude Agent 才使用已发布 Free 套餐版本中明确标记的默认模型。

配置完成需要同时满足：模型已启用、Provider 可路由且凭据有效、Pricing 当前有效、用户订阅与 Token 额度可用；套餐权益可进一步提供模型级范围和限制。缺少 Provider 或 Pricing 时，模型可能仍可见但会显示为维护或不可调用；没有可用的 Free 默认模型时，Dream 不会暗中选择其他模型，而会返回明确的模型不可用错误。

> **不要混淆两类模型：** `/root/checkpoint/YuE2-3B` 是 YuE Runner 的本地音乐生成权重；Admin“AI 模型中心”配置的是 Dream／Claude Agent 经 Gateway 调用的对话模型。配置或替换 YuE2 的 `model.safetensors` 不会自动创建 Dream 默认模型。

### 第四步：连接 YuE Runner

Runner 只监听实例的 `127.0.0.1:10000`。当 AutoDL 未给 10000 配置应用服务入口时，在本机建立端口转发：

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 11000:127.0.0.1:10000 \
  -p <AutoDL-SSH端口> root@<AutoDL-SSH主机>
```

本机随后使用：

- HTTP API：`http://127.0.0.1:11000`；
- Swagger：`http://127.0.0.1:11000/docs`；
- MCP：`http://127.0.0.1:11000/mcp`。

Runner 不启用应用层 Token，必须保持本机监听，或由 AutoDL 的访问控制代理保护。

## 相关服务

| 服务 | 实例内地址 | 进程监督 | 用途 |
| --- | --- | --- | --- |
| Dream 前端 | `http://127.0.0.1:6006` | `screen: ink-dream` | 对话界面与同源 API |
| Dream 后端 | `http://127.0.0.1:8765` | `screen: ink-dream` | FastAPI、Agent 与 SSE |
| Admin | `http://127.0.0.1:6008` | `screen: ink-admin` | 身份、模型、策略、Gateway 与 PostgreSQL |
| YuE Runner | `http://127.0.0.1:10000` | PID 文件 | HTTP、MCP、上传、任务和产物 |

常用路径：

| 内容 | 路径 |
| --- | --- |
| Admin release | `/root/ink-autodl/admin/current` |
| Dream release | `/root/ink-autodl/dream/current` |
| Runner 源码 | `/root/autodl-tmp/agent-sandbox` |
| YuE 源码 | `/root/apps/YuE` |
| YuE Conda 环境 | `/root/yue-envs` |
| Runner 任务数据 | `/root/agent-sandbox-data/tasks` |
| 统一启动日志 | `/root/LaunchTool311/log/ink-memory-yue-start.log` |
| Runner 日志 | `/root/LaunchTool311/log/yue-runner.log` |

`/root/yue-envs` 下包含三个独立环境：`yue-runner` 使用 Python 3.11，`yue-model` 使用 Python 3.12 与 PyTorch 2.10.0+cu128，`sheetsage2` 使用 Python 3.12、PyTorch 2.8.0+cu128 与 NumPy 1.26.4。SheetSage2 官方固定的 NumPy 1.24.3 没有 Python 3.12 预编译包，因此镜像采用同一 1.x API 范围内的兼容版本，并已通过 `pip check`、CUDA 导入和命令入口检查。

## YuE Runner 能力

Runner MCP 提供 `runner_upload`、`runner_submit`、`runner_result` 和 `runner_result_source`。`runner_submit` 可提交：

| Task | 用途 |
| --- | --- |
| `yue2_task` | 歌曲生成、计划、已有 latent 解码和比较 |
| `sheetsage2_task` | 音频转 ABC、MIDI 等乐谱产物 |
| `music_score_task` | ABC 检查、移除和弦、编辑前后比较 |
| `music_listen_task` | 为已完成任务生成试听比较包 |

客户端只能上传、提交、轮询和下载，不能提交服务器脚本、解释器、模型目录或 shell 命令。

## 配套 Claude Skill

配套 Skill／Claude plugin 仓库为 [glide-the/YuE2-skills](https://github.com/glide-the/YuE2-skills)。它是 YuE Runner 的纯客户端，负责连接 MCP、组织歌曲生成、音频转谱、改谱和试听工作流，并提供请求契约与领域参考；Skill 不包含模型处理脚本，也不在本机加载 YuE2 或 SheetSage2，所有任务仍由 AutoDL 上的 Runner Task／Processor 执行。

在 Claude Code 中安装：

```text
/plugin marketplace add glide-the/YuE2-skills
/plugin install yue2@yue2-skills
```

安装后通过 `/mcp` 确认 `yue2-runner` 已连接。插件默认连接 `http://127.0.0.1:11000/mcp`，因此必须先运行统一启动脚本，并按“第四步：连接 YuE Runner”建立本机 `11000` 到实例 `127.0.0.1:10000` 的 SSH 隧道。

### Runner 与 Skill 的调用规则

- `runner_upload` 只签发一次性上传地址，不会替客户端读取或传输本地文件；客户端必须执行返回的上传命令，并从成功的 PUT 响应取得 `asset_id`。
- 使用 `runner_submit` 提交任务后保存返回的 `task_id`，后续只用 `runner_result` 轮询，不能为了查询进度重复提交任务。
- 同一意图超时重试时必须复用原 `idempotency_key`；只有用户确实发起新一轮任务时才使用新 key。
- 任务完成后必须从 `artifacts` 读取真实的 `result_source_name`，再调用 `runner_result_source`；不要猜测产物名称。
- 音频、ZIP 等大文件使用 `runner_result_source` 的 `mode: "link"`；小型文本产物可使用 `mode: "auto"`。
- `music_listen_task` 的完整试听页面应下载 `comparison.zip`，以保留 HTML 引用的音频和元数据目录结构。

### 使用示例 1：根据风格和歌词生成歌曲

安装插件并连接 Runner MCP 后，可以直接对 Claude 说：

> 用 YuE2 生成一首 90 BPM 的中文女声爵士流行歌曲，包含钢琴、贝斯和轻柔鼓组；
> 歌词主题是雨夜重逢。使用 full 模式，生成后把音频链接发给我。

对应的核心 `runner_submit` 参数如下：

```json
{
  "parameter": {
    "task_name": "yue2_task",
    "reset": false,
    "user_multi_task": false
  },
  "payload": {
    "code_input": {
      "userId": "local",
      "workflow_id": "rainy-night-jazz"
    },
    "operation": "generate",
    "request": {
      "id": "rainy-night-jazz-v1",
      "style": "90 BPM Chinese female vocal jazz pop, piano, upright bass, soft drums",
      "lyrics": "[Verse]\n雨落在旧街灯下……\n[Chorus]\n我们在雨夜重逢……",
      "cot": "full",
      "seed": 831001
    }
  },
  "idempotency_key": "rainy-night-jazz-v1"
}
```

保存返回的 `task_id` 并使用 `runner_result` 轮询。完成后，从 `artifacts` 读取音频对应的 `result_source_name`，再调用 `runner_result_source`，音频使用 `mode: "link"` 获取下载链接。

### 使用示例 2：上传音频并转录为 ABC 乐谱

可以直接对 Claude 说：

> 把 `/Users/me/Music/demo.wav` 上传到 YuE2 Runner，用 SheetSage2 的 full 模式
> 转成 ABC 乐谱，完成后下载乐谱文件。

首先调用 `runner_upload`：

```json
{
  "file_path": "/Users/me/Music/demo.wav",
  "client_os": "darwin"
}
```

客户端执行 `runner_upload` 返回的上传命令，成功后从 PUT 响应取得 `asset_id`，然后提交转录任务：

```json
{
  "parameter": {
    "task_name": "sheetsage2_task",
    "reset": false,
    "user_multi_task": false
  },
  "payload": {
    "code_input": {
      "userId": "local",
      "workflow_id": "demo-transcription"
    },
    "operation": "transcribe",
    "audio_asset_id": "<PUT 响应返回的 asset_id>",
    "transcription": {
      "task": "full"
    }
  },
  "idempotency_key": "demo-transcription-v1"
}
```

使用返回的 `task_id` 调用 `runner_result`。任务完成后，从结果清单取得 ABC 对应的 `result_source_name`，再用 `runner_result_source` 的 `mode: "auto"` 读取或下载。不要把本机路径、服务器路径或模型路径放进任务提交参数。

## 模型与软链接

Runner 使用 `/root/checkpoint/YuE2-3B`。其中 `model.safetensors` 复用 AutoDL 公共模型文件，不在实例中重复下载：

```text
/root/checkpoint/YuE2-3B/model.safetensors
  -> /.autodl/09/bf/72/09bf72881ebdb7287327573913cc2e11
```

只读验证：

```bash
test -L /root/checkpoint/YuE2-3B/model.safetensors
test "$(readlink /root/checkpoint/YuE2-3B/model.safetensors)" = \
  '/.autodl/09/bf/72/09bf72881ebdb7287327573913cc2e11'
test -r /root/checkpoint/YuE2-3B/model.safetensors
test -r /root/checkpoint/YuE2-3B/config.json
find /root/checkpoint -type f -name '*.incomplete' -print
```

相关模型包括 YuE2-3B、YuE2-Vae、SheetSage2 和 MERT-v2-FullSong。YuE2 生成不需要 MERT；MERT-v2-FullSong 由 SheetSage2 使用。公共模型软链接的通用操作方式见 [AutoDL 公共模型说明](https://www.autodl.art/docs/app_model/)。

## 状态与日志

```bash
screen -ls
ss -ltnp | grep -E ':(6006|6008|8765|10000)\b'
curl -fsS http://127.0.0.1:6008/admin/login >/dev/null
curl -fsS http://127.0.0.1:6006/api/health
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:10000/openapi.json >/dev/null
tail -n 200 /root/ink-autodl/admin/logs/admin.log
tail -n 200 /root/ink-autodl/dream/logs/dream.log
tail -n 200 /root/LaunchTool311/log/yue-runner.log
```

## 出现问题时怎么处理

### 统一启动失败

先看统一启动日志，再看失败服务自己的日志：

```bash
tail -n 200 /root/LaunchTool311/log/ink-memory-yue-start.log
```

脚本遇到未知进程占用端口时会停止，不会替换该进程。核对 PID 和完整命令行后再处理，不要使用 `pkill -f python`、`killall node` 等模糊命令。

### Dream 或 Admin 无法打开

确认 6006、6008 和 8765 均在监听。实例迁移后，AutoDL 的公网地址会变化；Admin 与 Dream 的 runtime env 必须由当前实例的 `AutoDLService6006URL` 和 `AutoDLService6008URL` 重新生成，不能继续使用旧实例地址。

### Runner 的 MCP 地址返回 405 或 406

`/mcp` 是 Streamable HTTP 协议端点，不是网页。普通浏览器请求返回 405 或 406 不代表服务异常，应由 MCP 客户端执行 `initialize` 和 `tools/list`。

### 模型路径存在但生成失败

```bash
readlink /root/checkpoint/YuE2-3B/model.safetensors
stat -L /root/checkpoint/YuE2-3B/model.safetensors
find /root/checkpoint -type f -name '*.incomplete' -print
df -h / /root/autodl-tmp
tail -n 200 /root/LaunchTool311/log/yue-runner.log
```

先确认 `/root/yue-envs/yue-model/bin/python` 存在，再排除断链、缺少模型元数据、残留下载文件和磁盘空间不足。不要覆盖未知文件，也不要把模型复制进 Python 环境。

### CUDA 显存不足

```bash
nvidia-smi
ps -eo pid,cmd | grep -E '[Y]uE|[S]heetSage|[p]ython'
```

Runner 将模型任务并发限制为 1。只终止能够确认属于失败任务的模型子进程；Admin、Dream 与 Runner 主进程不应作为释放显存的目标。

## 单独停止 Runner

```bash
bash /root/autodl-tmp/agent-sandbox/deploy/autodl/stop_yue_runner.sh
```

该脚本会核对 PID 和完整命令行，只停止本部署的 Runner，不影响 Admin 或 Dream。数据库与用户任务数据不会因服务停止而删除。
