
# Research Agent Task API 文档

## 概述

本文档描述了 `research_agent_task` 的三个主要 API 端点，用于提交研究任务、查询任务状态和获取任务结果文件。

**实现位置**: [runner.py](sandbox/server/servlet/runner.py)

---

## 目录

- [1. POST /runner/submit - 提交研究任务](#1-post-runnersubmit---提交研究任务)
- [2. GET /runner/result - 获取任务状态和结果](#2-get-runnerresult---获取任务状态和结果)
- [3. GET /runner/result_source - 获取任务结果文件](#3-get-runnerresult_source---获取任务结果文件)
- [4. 数据模型](#4-数据模型)
- [5. 任务执行流程](#5-任务执行流程)
- [6. 错误码说明](#6-错误码说明)

---

## 1. POST /runner/submit - 提交研究任务

### 描述

创建一个新的研究任务并提交到任务队列。系统将使用多个专业化的 AI Agent（研究专家、数据分析师、报告撰写人）来完成任务。

### 端点

```
POST /runner/submit
```

### 请求体

```json
{
  "created_at": 0,
  "requested_at": 0,
  "parameter": {
    "task_name": "research_agent_task",
    "reset": true
  },
  "payload": {
    "code_input": {
      "workspace": "workspace",
      "userId": "user_123",
      "userFilesDir": "files",
      "userLogsDir": "logs",
      "logDetailPath": "logs/log_detail.jsonl",
      "logSummaryPath": "logs/log_summary.json",
      "logRunPath": "logs/log_run.log"
    },
    "topic": "请调研并研究安徽省数字资产交易如何在十五五计划中进一步发展推进，并生成包含图表的 PDF 报告。"
  }
}
```

### 请求参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `created_at` | number | 否 | 任务创建时间戳（系统自动设置） |
| `requested_at` | number | 否 | 任务请求时间戳（系统自动设置） |
| `parameter` | object | 是 | 任务参数配置 |
| `parameter.task_name` | string | 是 | 固定值：`"research_agent_task"` |
| `parameter.reset` | boolean | 否 | 是否重置已存在的任务（默认 true） |
| `payload` | object | 是 | 任务负载数据 |
| `payload.code_input` | object | 是 | 代码执行配置（见下方详细说明） |
| `payload.topic` | string | 是 | 研究主题描述 |

#### code_input 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `workspace` | string | 否 | - | 工作空间目录（相对或绝对路径），不填则默认为 `workspace/{userId}` |
| `userId` | string | **是** | - | 用户唯一标识符 |
| `userFilesDir` | string | 否 | `"files"` | 用户文件目录（相对 workspace） |
| `userLogsDir` | string | 否 | `"logs"` | 日志目录（相对 workspace） |
| `logDetailPath` | string | 否 | `"logs/log_detail.jsonl"` | 详细日志路径（相对 workspace） |
| `logSummaryPath` | string | 否 | `"logs/log_summary.json"` | 日志摘要路径（相对 workspace） |
| `logRunPath` | string | 否 | `"logs/log_run.log"` | 运行日志路径（相对 workspace） |

### 响应

#### 成功响应 (200)

```json
{
  "code": 200,
  "msg": "提交任务成功",
  "data": {
    "task_id": "abc123def456",
    "info": "pending",
    "finished": false
  }
}
```

#### 任务已存在 (非 reset 模式)

```json
{
  "code": 200,
  "msg": "提交任务成功",
  "data": {
    "task_id": "abc123def456",
    "info": "running",
    "finished": false
  }
}
```

#### 任务被拒绝 (409)

```json
{
  "code": 409,
  "msg": "任务被拒绝的具体原因",
  "data": {}
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | number | HTTP 状态码 |
| `msg` | string | 响应消息 |
| `data.task_id` | string | 任务唯一标识符（MD5 hash） |
| `data.info` | string | 任务状态：`pending`（等待中）|`running`（运行中）|`completed`（已完成）|
| `data.finished` | boolean | 任务是否已完成 |

### 示例代码

#### cURL

```bash
curl -X POST "http://localhost:8000/runner/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "parameter": {
      "task_name": "research_agent_task",
      "reset": true
    },
    "payload": {
      "code_input": {
        "workspace": "workspace",
        "userId": "user_123"
      },
      "topic": "调研人工智能在医疗领域的最新进展并生成报告"
    }
  }'
```

#### Python

```python
import requests
import json

url = "http://localhost:8000/runner/submit"

payload = {
    "parameter": {
        "task_name": "research_agent_task",
        "reset": True
    },
    "payload": {
        "code_input": {
            "workspace": "workspace",
            "userId": "user_123"
        },
        "topic": "调研人工智能在医疗领域的最新进展并生成报告"
    }
}

response = requests.post(url, json=payload)
result = response.json()

if result["code"] == 200:
    task_id = result["data"]["task_id"]
    print(f"任务已提交，ID: {task_id}")
else:
    print(f"提交失败: {result['msg']}")
```

---

## 2. GET /runner/result - 获取任务状态和结果

### 描述

查询任务的执行状态和结果元数据。返回包含任务状态、完成标志和结果路径的信息。

### 端点

```
GET /runner/result?task_id={task_id}
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | **是** | 任务唯一标识符（由 submit 接口返回） |

### 响应

#### 成功响应 (200)

```json
{
  "code": 200,
  "msg": "获取任务成功",
  "data": {
    "task_id": "abc123def456",
    "info": "completed",
    "finished": true,
    "result": {
            "result_path": "/Users/dmeck/project/agent-sandbox/app/sandbox/workspace4/user_789/logs/result.json",
            "log_detail_path": "/Users/dmeck/project/agent-sandbox/app/sandbox/workspace4/user_789/logs/log_detail.jsonl",
            "log_summary_path": "/Users/dmeck/project/agent-sandbox/app/sandbox/workspace4/user_789/logs/log_summary.json",
            "log_run_path": "/Users/dmeck/project/agent-sandbox/app/sandbox/workspace4/user_789/logs/log_run.log"
    }
  }
}
```

#### 任务进行中

```json
{
  "code": 200,
  "msg": "获取任务成功",
  "data": {
    "task_id": "abc123def456",
    "info": "running",
    "finished": false
  }
}
```

#### 任务不存在 (500)

```json
{
  "code": 500,
  "msg": "abc123def456: 任务不存在"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.task_id` | string | 任务 ID |
| `data.info` | string | 任务状态信息 |
| `data.finished` | boolean | 任务是否完成 |
| `data.result` | object | 任务结果（仅当任务完成时存在） |
| `data.result....` | string | 任务文件（field_name） |

### 示例代码

#### cURL

```bash
curl -X GET "http://localhost:8000/runner/result?task_id=abc123def456"
```

#### Python

```python
import requests
import time

task_id = "abc123def456"
url = f"http://localhost:8000/runner/result?task_id={task_id}"

# 轮询任务状态
while True:
    response = requests.get(url)
    result = response.json()

    if result["code"] == 500:
        print(f"错误: {result['msg']}")
        break

    data = result["data"]
    print(f"任务状态: {data['info']}, 完成: {data['finished']}")

    if data["finished"]:
        print("任务完成！结果:")
        print(json.dumps(data["result"], indent=2, ensure_ascii=False))
        break

    time.sleep(5)  # 每5秒查询一次
```

---

## 3. GET /runner/result_source - 获取任务结果文件

### 描述

下载任务生成的文件，如 PDF 报告、图表、数据文件等。

### 端点

```
GET /runner/result_source?task_id={task_id}&result_source_name={field_name}
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | **是** | 任务唯一标识符 |
| `result_source_name` | string | **是** | 结果字段名称（见下方支持的值） |

### 支持的 result_source_name 值

根据 `result` 对象的返回，`result_source_name` 可以是：

| 值 | 说明 |
|----|------|
| 通过 `/runner/result` 返回的 `result` 对象中的任意文件路径字段 | |

**注意**: 具体可用的字段名取决于任务实现。对于 research_agent_task，可能需要先调用 `/runner/result` 获取完整的 `result` 对象，然后根据需要下载其中的文件。

### 响应

#### 成功响应 (200)

返回文件的二进制内容，Content-Type 为 `multipart/form-data`。

#### 文件不存在 (500)

```json
{
  "code": 500,
  "msg": "/path/to/file: 读取文件失败"
}
```

#### 任务不存在 (500)

```json
{
  "code": 500,
  "msg": "{task_id}: 任务不存在"
}
```

### 示例代码

#### cURL（直接下载）

```bash
# 下载文件到本地
curl -X GET "http://localhost:8000/runner/result_source?task_id=abc123def456&result_source_name=report_path" \
  -o report.pdf
```

#### Python（下载文件）

```python
import requests

task_id = "abc123def456"

# 首先获取任务状态，找到文件路径
result_url = f"http://localhost:8000/runner/result?task_id={task_id}"
result_response = requests.get(result_url)
result_data = result_response.json()

if result_data["data"]["finished"]:
    # 假设结果中有文件路径
    # 这里需要根据实际的 result 结构来确定

    # 下载示例（需要根据实际字段名调整）
    file_url = f"http://localhost:8000/runner/result_source?task_id={task_id}&result_source_name=summary"

    file_response = requests.get(file_url)

    if file_response.status_code == 200:
        with open("downloaded_file.pdf", "wb") as f:
            f.write(file_response.content)
        print("文件下载成功")
    else:
        print(f"下载失败: {file_response.json()['msg']}")
```

---

## 4. 数据模型

### PayLoad

```typescript
interface PayLoad {
  created_at: number;        // 任务创建时间
  requested_at: number;      // 任务请求时间
  finished_at: number;       // 任务完成时间
  parameter: RunnerParameter;
  payload: ResearchAgentPayload;
}
```

### RunnerParameter

```typescript
interface RunnerParameter {
  task_name: string;         // 默认: "sandbox_eval_task"
  reset: boolean;            // 默认: true
}
```

### ResearchAgentPayload

```typescript
interface ResearchAgentPayload {
  code_input: ResearchAgentSandboxProcessorData;
  topic: string;
}
```

### ResearchAgentSandboxProcessorData

```typescript
interface ResearchAgentSandboxProcessorData {
  workspace: string;         // 可选，默认 "workspace/{userId}"
  userId: string;            // 必填
  userFilesDir: string;      // 默认 "files"
  userLogsDir: string;       // 默认 "logs"
  logDetailPath: string;     // 默认 "logs/log_detail.jsonl"
  logSummaryPath: string;    // 默认 "logs/log_summary.json"
  logRunPath: string;        // 默认 "logs/log_run.log"
}
```

### TaskRunnerResponse

```typescript
interface TaskRunnerResponse {
  code: number;
  msg: string;
  data: {
    task_id: string;
    info: string;
    finished: boolean;
    result?: object;
  };
}
```

### RunnerState

```typescript
interface RunnerState {
  task_id: string;
  runner_stat: string;
  nonce: string;
  state: string;
  finished: boolean;
  result: object;
}
```

### TokenUsage

```typescript
interface TokenUsage {
  steps: number;          // 对话步骤数（唯一消息ID数量）
  input_tokens: number;   // 输入token总数
  output_tokens: number;  // 输出token总数
  total_tokens: number;   // 总token数（input + output）
}
```

### ResearchAgentResult

```typescript
interface ResearchAgentResult {
  workspace: string;
  userId: string;
  topic: string;
  token_usage: TokenUsage;
  // ...其他可能的字段
}
```

---

## 5. 任务执行流程

```
┌─────────┐
│  用户   │
└────┬────┘
     │
     │ POST /runner/submit
     ├─────────────────────────┐
     │                         │
     ▼                         ▼
┌──────────────────────────────────────┐
│        任务队列                      │
└──────────────────┬───────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ Research Agent   │
         │   Processor     │
         └────────┬────────┘
                  │
                  ├─────────────────┬─────────────────┬──────────────────┐
                  │                 │                 │                  │
                  ▼                 ▼                 ▼                  ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐
         │  Researcher  │  │ Data Analyst │  │Report Writer│  │  Files/Logs   │
         │  Agent       │  │  Agent       │  │  Agent      │  │  Output       │
         └──────────────┘  └──────────────┘  └──────────────┘  └───────────────┘
                  │                 │                 │                  │
                  └─────────────────┴─────────────────┴──────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │   result.json   │
                          │   (metadata)    │
                          └─────────────────┘
                                    │
                   ┌────────────────┴────────────────┐
                   │                                  │
                   ▼                                  ▼
          ┌─────────────────┐              ┌─────────────────┐
          │ /runner/result  │              │/runner/result_  │
          │  (查询状态)      │              │ source (下载文件)│
          └─────────────────┘              └─────────────────┘
```

### 执行步骤

1. **任务提交**: 用户通过 `/runner/submit` 提交研究任务
2. **任务入队**: 任务被添加到队列，生成唯一 `task_id`
3. **Agent 执行**:
   - **Researcher Agent**: 使用 WebSearch 收集研究信息，写入 `files/research_notes/`
   - **Data Analyst Agent**: 读取研究笔记，提取数据，生成图表（`files/charts/`），查询数据库（如需要）
   - **Report Writer Agent**: 综合研究笔记、数据和图表，生成 PDF 报告（`files/reports/`）
4. **结果输出**: 生成 `result.json` 和各类日志文件
5. **结果查询**: 用户通过 `/runner/result` 查询任务状态
6. **文件下载**: 用户通过 `/runner/result_source` 下载生成的文件

### 输出文件结构

```
workspace/
└── {userId}/
    ├── files/
    │   ├── research_notes/    # 研究笔记
    │   ├── data/              # 数据分析结果
    │   ├── charts/            # 图表文件
    │   └── reports/           # PDF 报告
    └── logs/
        ├── log_detail.jsonl   # 详细工具调用日志
        ├── log_summary.json   # 日志摘要
        ├── log_run.log        # 运行日志
        └── result.json        # 任务结果元数据（含token使用统计）
```

### result.json 数据结构

任务完成后，`result.json` 文件包含任务的元数据和执行信息：

```json
{
  "workspace": "workspace/user_123",
  "userId": "user_123",
  "topic": "研究主题",
  "token_usage": {
    "steps": 5,
    "input_tokens": 12345,
    "output_tokens": 23456,
    "total_tokens": 35801
  }
}
```

#### token_usage 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `steps` | number | 对话步骤数（唯一消息ID数量，遵循"Same ID = Same Usage"原则） |
| `input_tokens` | number | 输入token总数（发送给Claude的token数） |
| `output_tokens` | number | 输出token总数（Claude生成的token数） |
| `total_tokens` | number | 总token数（input + output） |

**Token跟踪实现说明**:
- 基于 [Claude Agent SDK Cost Tracking](https://platform.claude.com/docs/en/agent-sdk/cost-tracking) 最佳实践
- 使用消息ID去重机制，避免并行工具调用重复计算
- 每个唯一消息ID只计数一次，确保准确的成本追踪
- 日志文件 `log_run.log` 中也会记录格式化的token使用信息

---

## 6. 错误码说明

| HTTP 状态码 | 说明 | 处理建议 |
|------------|------|----------|
| 200 | 成功 | 正常处理响应数据 |
| 401 | 未授权 | nonce 认证失败（内部接口） |
| 409 | 任务被拒绝 | 任务参数验证失败，检查请求格式 |
| 500 | 服务器错误 | 查看错误消息，可能是：<br>- 任务不存在<br>- 文件读取失败<br>- 处理器执行异常 |

### 常见错误场景

#### 1. 任务不存在

```json
{
  "code": 500,
  "msg": "abc123def456: 任务不存在"
}
```

**原因**: task_id 不正确或任务已过期

**解决**: 确认 task_id 是否正确，或重新提交任务

#### 2. 文件读取失败

```json
{
  "code": 500,
  "msg": "/app/sandbox/workspace/user_123/files/reports/report.pdf: 读取文件失败"
}
```

**原因**: 文件不存在或路径错误

**解决**: 先调用 `/runner/result` 确认任务已完成，检查返回的路径

#### 3. 任务被拒绝

```json
{
  "code": 409,
  "msg": "TaskRejectedError: 某种验证失败原因",
  "data": {}
}
```

**原因**: 任务参数验证失败

**解决**: 检查请求体格式，确保必填字段完整

--- 

## 附录

### 相关文件

- [runner.py](../sandbox/server/servlet/runner.py) - API 端点实现
- [research_agent_processor.py](../sandbox/processors/research_agent_processor.py) - 研究任务处理器
- [flow_data.py](../sandbox/server/model/flow_data.py) - 数据模型定义
- [result.py](../sandbox/server/model/result.py) - 响应模型定义

### 技术栈

- **Web 框架**: FastAPI
- **数据验证**: Pydantic
- **AI Agent**: Claude Agent SDK
- **报告生成**: reportlab
- **数据处理**: pandas, matplotlib

### 更新日志

- 2025-01-08: 添加 `token_usage` 字段到 `result.json`，记录Claude SDK token使用情况
- 2024-12-29: 初始版本，包含三个主要 API 端点的完整文档
