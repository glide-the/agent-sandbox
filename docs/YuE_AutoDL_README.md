# YuE2 Runner · AutoDL 镜像使用说明

本镜像集成 **YuE2、SheetSage2、Agent Sandbox Runner 与 Runner MCP**。它可以把歌词和风格描述生成完整歌曲，也可以把已有音频转成可编辑的 ABC 乐谱，再用于翻唱或二次编曲。

> Runner 启动后只提供任务队列、HTTP 与 MCP 接口，不会预先加载 YuE2，也不会占用模型显存。只有提交生成或转谱任务时，模型子进程才会启动；乐谱检查和试听比较是服务端轻量任务，不加载模型。

## 快速开始

### 1. 启动 Runner

登录 AutoDL 实例后执行：

```bash
bash /root/autodl-tmp/agent-sandbox/deploy/autodl/start_yue_runner.sh
```

检查服务：

```bash
ss -ltnp | grep ':10000\b'
curl -fsS http://127.0.0.1:10000/openapi.json >/dev/null
tail -n 100 /root/LaunchTool311/log/yue-runner.log
```

这些命令只启动并检查 Runner，不会运行 YuE2 或 SheetSage2 模型。

### 2. 从本机建立 SSH 隧道

Runner 只监听实例的 `127.0.0.1`。在本机执行：

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 11000:127.0.0.1:10000 \
  -p <AutoDL-SSH端口> root@<AutoDL-SSH主机>
```

保持该终端运行。本机随后使用：

- HTTP API：`http://127.0.0.1:11000`
- Swagger：`http://127.0.0.1:11000/docs`
- MCP：`http://127.0.0.1:11000/mcp`

## 服务关系

```text
HTTP / MCP 客户端
        │  SSH 隧道，无应用层 Token
        ▼
Agent Sandbox Runner :10000
        │  持久任务、幂等、文件能力 URL
        ├──────────────► YuE2 子进程（Python 3.12）
        ├──────────────► SheetSage2 子进程（Python 3.11）
        ├──────────────► ABC 检查任务（abc_tools.py）
        └──────────────► 试听比较任务（listen.py）
                              │
                              ▼
                    ABC 乐谱可回传给 YuE2
```

Runner 与两个模型环境相互隔离。任务并发数为 `1`，确保 YuE2 和 SheetSage2 在同一张 GPU 上串行运行。

| 组件 | 路径或地址 | 用途 |
| --- | --- | --- |
| Runner | `http://127.0.0.1:10000` | HTTP、上传、任务状态与结果 |
| Runner MCP | `http://127.0.0.1:10000/mcp` | 4 个兼容工具 |
| Runner 环境 | `/root/autodl-tmp/envs/yue-runner` | Conda Python 3.11 |
| YuE2 环境 | `/root/autodl-tmp/envs/yue-model` | Conda Python 3.12 |
| SheetSage2 环境 | `/root/autodl-tmp/envs/sheetsage2` | Conda Python 3.11 |
| YuE 源码 | `/root/apps/YuE` | 官方 YuE2 代码与本服务适配脚本 |
| 服务源码 | `/root/autodl-tmp/agent-sandbox` | Agent Sandbox Runner |
| 任务数据 | `/root/agent-sandbox-data/tasks` | 输入、日志、原生产物和交付产物 |
| 启动日志 | `/root/LaunchTool311/log/yue-runner.log` | Runner 与 worker 日志 |

## MCP 客户端

Runner MCP 暴露以下静态工具：

| 工具 | 用途 |
| --- | --- |
| `runner_upload` | 获取一次性上传能力 URL |
| `runner_submit` | 提交生成、转录、乐谱检查或试听比较任务 |
| `runner_result` | 查询持久任务状态和结果清单 |
| `runner_result_source` | 读取小文件或获取大文件下载 URL |

客户端不需要配置 Token 或发送 `Authorization` 请求头。连接后可先执行只读检查：

> 列出 Runner MCP 工具并报告服务状态，不要上传文件、提交任务或启动模型。

四个 MCP 工具是统一传输接口，不等于只有四类模型调用。`runner_submit` 可提交：

| Task | 服务端脚本 | 用途 |
| --- | --- | --- |
| `yue2_task` | `run_yue2.py` | 生成、规划、全模式与解码 |
| `sheetsage2_task` | `transcribe.py` | 音频转 ABC |
| `music_score_task` | `abc_tools.py` | inspect、strip_chords、compare |
| `music_listen_task` | `listen.py` | 为已完成任务生成试听比较包 |

Claude Skill 只负责上传、提交、轮询和下载，不能在客户端直接执行这些脚本或加载模型。

## 模型与软链接

模型入口统一位于 `/root/checkpoint`。YuE2-3B 的大文件实际放在数据盘，通过软链接接入：

```text
/root/checkpoint/YuE2-3B
  -> /root/autodl-tmp/checkpoint/YuE2-3B
```

检查模型，不加载权重：

```bash
readlink -e /root/checkpoint/YuE2-3B
test -r /root/checkpoint/YuE2-3B/config.json
test -r /root/checkpoint/YuE2-3B/model.safetensors
find /root/autodl-tmp/checkpoint/YuE2-3B -type f -name '*.incomplete' -print
```

部署需要的资源：

| 模型 | 用途 |
| --- | --- |
| `YuE2-3B` | 歌曲生成、规划、翻唱和编辑 |
| `YuE2-Vae` | 默认音频解码器 |
| `SheetSage2` | 音频转 ABC 乐谱 |
| `MERT-v2-FullSong` | SheetSage2 编码器 |

YuE2 生成不需要额外加载 MERT2；MERT2 只用于 SheetSage2。不要将模型重复复制到 Conda 环境中。

## 环境验证（不启动模型）

```bash
/root/autodl-tmp/envs/yue-runner/bin/python --version
/root/autodl-tmp/envs/yue-model/bin/python --version
/root/autodl-tmp/envs/sheetsage2/bin/python --version

/root/autodl-tmp/envs/yue-model/bin/python -c \
  'import torch, yue2; print(torch.__version__, torch.cuda.is_available())'

/root/autodl-tmp/envs/sheetsage2/bin/python -c \
  'import torch, transformers; print(torch.__version__, torch.cuda.is_available())'

nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
```

导入检查不应创建 YuE2 模型进程，`nvidia-smi` 中也不应出现新增的大显存占用。

## 停止 Runner

```bash
bash /root/autodl-tmp/agent-sandbox/deploy/autodl/stop_yue_runner.sh
```

停止脚本会先核对 PID 和命令行，只终止本部署的 Runner，不会按模糊进程名批量结束进程。

## 出现问题时怎么处理

### `10000` 没有监听

```bash
tail -n 200 /root/LaunchTool311/log/yue-runner.log
test -x /root/autodl-tmp/envs/yue-runner/bin/python
```

确认没有未知进程占用端口后，再重新运行启动脚本。

### MCP 浏览器访问返回 `405` 或 `406`

`/mcp` 是 Streamable HTTP 协议端点，不是普通网页。浏览器 GET 或简单 `curl` 的 `405`/`406` 不代表服务异常；应通过 MCP 客户端完成 `initialize` 与 `tools/list`。

### 模型路径存在但任务失败

```bash
readlink -e /root/checkpoint/YuE2-3B
find /root/checkpoint /root/autodl-tmp/checkpoint -type f -name '*.incomplete' -print
df -h / /root/autodl-tmp
tail -n 200 /root/LaunchTool311/log/yue-runner.log
```

文件出现不代表下载完成。先排除断链、`.incomplete`、空间不足和环境路径错误，再考虑重新下载；不要直接覆盖未知模型目录。

### CUDA 显存不足

本部署只允许一个模型任务执行。确认没有外部进程占用 GPU：

```bash
nvidia-smi
ps -eo pid,cmd | grep -E '[Y]uE|[S]heetSage|[p]ython'
```

不要使用模糊的 `pkill -f python`。确认 PID 和完整命令行属于失败的模型子进程后，再进行定向处理。

### 服务重启后的未完成任务

任务状态会持久化。服务重启时，已产生完整结果清单的任务会恢复为完成；被中断且没有完整结果的任务会标记为 `interrupted`，不会自动重新采样。

## 安全与许可

- Runner 默认只监听本机，通过 SSH 隧道访问；
- 服务不启用应用层 Token，必须保持 `127.0.0.1` 监听并通过 SSH 隧道访问；
- 本部署使用固定的本地任务主体 `local`，请求中的 `code_input.userId` 使用 `local`；
- 上传能力 URL 单次使用并有过期时间；
- 模型子进程固定参数列表执行，不拼接 shell 命令；
- YuE2 代码采用 Apache-2.0；模型权重许可与商业使用条件以官方模型许可证为准。

官方资料：[YuE2 仓库与快速开始](https://github.com/multimodal-art-projection/YuE)、[模型与资源](https://github.com/multimodal-art-projection/YuE#models-and-resources)。
