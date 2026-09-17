# Sandbox Eval Task API 文档

## 概述

本文档描述了 `sandbox_eval_task` 的完整 API 使用方法，包括文件提取、任务提交和结果获取。该任务用于代码评测场景，支持标准答案和用户提交文件的比对评估。

**实现位置**:
- [runner.py](../sandbox/server/servlet/runner.py) - Runner API 端点
- [extract_file.py](../sandbox/server/servlet/extract_file.py) - 文件提取处理
- [sanbox_eval_task.py](../sandbox/tasks/sanbox_eval_task.py) - 任务定义

---

## 目录

- [1. POST /extract_standard_file - 提取标准答案文件](#1-post-extract_standard_file---提取标准答案文件)
- [2. POST /extract_submit_file - 提取用户提交文件](#2-post-extract_submit_file---提取用户提交文件)
- [3. POST /runner/submit - 提交评测任务](#3-post-runnersubmit---提交评测任务)
- [4. GET /runner/result - 获取任务状态和结果](#4-get-runnerresult---获取任务状态和结果)
- [5. GET /runner/result_source - 获取任务结果文件](#5-get-runnerresult_source---获取任务结果文件)
- [6. 数据模型](#6-数据模型)
- [7. 任务执行流程](#7-任务执行流程)
- [8. 错误码说明](#8-错误码说明)

---

## 1. POST /extract_standard_file - 提取标准答案文件

### 描述

上传并解压标准答案文件（zip 格式）。该文件应包含评测所需的标准答案数据，会被解压到用户的评估目录中。

**端点**:
```
POST /extract_standard_file
```

### 请求参数 (multipart/form-data)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | **是** | 上传的 zip 文件 |
| `rank_id` | string | **是** | 排名/竞赛标识符 |
| `user_id` | string | **是** | 用户唯一标识符 |

### 请求示例

#### cURL

```bash
curl -X POST "http://localhost:8000/extract_standard_file" \
  -F "file=@standard_answer.zip" \
  -F "rank_id=competition_001" \
  -F "user_id=user_123"
```

#### Python

```python
import requests

url = "http://localhost:8000/extract_standard_file"

files = {
    'file': open('standard_answer.zip', 'rb')
}

data = {
    'rank_id': 'competition_001',
    'user_id': 'user_123'
}

response = requests.post(url, files=files, data=data)
result = response.json()

print(result)
```

### 响应

#### 成功响应 (200)

```json
{
  "id": "competition_001_1745225547",
  "filename": "standard_answer.zip",
  "bytes": 12345,
  "created_at": "competition_001_1745225547",
  "object": "file",
  "purpose": "standard"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 文件唯一标识符（格式：`{rank_id}_{timestamp}`） |
| `filename` | string | 原始文件名 |
| `bytes` | number | 文件大小（字节） |
| `created_at` | string | 创建时间标识 |
| `object` | string | 固定值：`"file"` |
| `purpose` | string | 固定值：`"standard"` |

### 文件处理逻辑

1. **清理旧数据**: 删除 `/app/sandbox/eval/{user_id}/` 目录
2. **创建新目录**: 创建用户评估目录
3. **保存上传文件**: 保存为 `{rank_id}_{timestamp}{extension}`
4. **解压外层 zip**: 提取到 `eval/{user_id}/`
5. **解压内层 zip**: 提取 `eval.zip` 到同一目录

**最终目录结构**:
```
/app/sandbox/eval/{user_id}/
├── standard_answer.zip          # 上传的原始文件
├── eval.zip                      # 内层评测文件
├── eval/                         # 解压后的标准答案文件
│   ├── answer.txt                # 标准答案
│   └── ...
└── input_param.json              # (后续生成)
```

---

## 2. POST /extract_submit_file - 提取用户提交文件

### 描述

上传用户提交的评测文件（支持任意格式）。该文件会被保存到提交目录，用于与标准答案比对。

**端点**:
```
POST /extract_submit_file
```

### 请求参数 (multipart/form-data)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | **是** | 用户提交文件（如 .xlsx, .zip, .txt 等） |
| `rank_id` | string | **是** | 排名/竞赛标识符 |
| `user_id` | string | **是** | 用户唯一标识符 |

### 请求示例

#### cURL

```bash
curl -X POST "http://localhost:8000/extract_submit_file" \
  -F "file=@submission.xlsx" \
  -F "rank_id=competition_001" \
  -F "user_id=user_123"
```

#### Python

```python
import requests

url = "http://localhost:8000/extract_submit_file"

files = {
    'file': open('submission.xlsx', 'rb')
}

data = {
    'rank_id': 'competition_001',
    'user_id': 'user_123'
}

response = requests.post(url, files=files, data=data)
result = response.json()

print(result)
```

### 响应

#### 成功响应 (200)

```json
{
  "id": "competition_001_1745225547",
  "filename": "submission.xlsx",
  "bytes": 5678,
  "created_at": "competition_001_1745225547",
  "object": "file",
  "purpose": "submit"
}
```

### 文件处理逻辑

1. **清理旧数据**: 删除 `/app/sandbox/eval/{user_id}/submit/` 目录
2. **创建新目录**: 创建用户提交目录
3. **保存文件**: 保存为 `{rank_id}_{timestamp}{extension}`

**最终目录结构**:
```
/app/sandbox/eval/{user_id}/
└── submit/
    └── competition_001_1745225547.xlsx    # 用户提交文件
```

---

## 3. POST /runner/submit - 提交评测任务

### 描述

创建一个新的评测任务并提交到队列。系统会执行评测脚本（`evaluate.py`）对比标准答案和用户提交。

**端点**:
```
POST /runner/submit
```

### 请求体

```json
{
  "created_at": 0,
  "requested_at": 0,
  "parameter": {
    "task_name": "sandbox_eval_task",
    "reset": true
  },
  "payload": {
    "code_input": {
      "evaluatorDir": "eval/user_id",
      "evaluatorPath": "eval_result.json",
      "standardFileDir": "eval/user_id/eval",
      "standardFilePath": "submit.jsonl",
      "userFileDir": "eval/user_id/submit",
      "userFilePath": "rank_id_1745225547.xlsx",
      "userId": "user_id",
      "logDetailPath": "eval/log_detail.jsonl",
      "logSummaryPath": "eval/log_summary.json",
      "logRunPath": "eval/log_run.log"
    }
  }
}
```

### 请求参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `created_at` | number | 否 | 任务创建时间戳（系统自动设置） |
| `requested_at` | number | 否 | 任务请求时间戳（系统自动设置） |
| `parameter` | object | 是 | 任务参数配置 |
| `parameter.task_name` | string | 是 | 固定值：`"sandbox_eval_task"` |
| `parameter.reset` | boolean | 否 | 是否重置已存在的任务（默认 true） |
| `payload` | object | 是 | 任务负载数据 |
| `payload.code_input` | object | 是 | 评测文件路径配置 |

#### code_input 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `evaluatorDir` | string | **是** | - | 评测结果输出目录（相对 `/app/sandbox`） |
| `evaluatorPath` | string | **是** | - | 评测结果文件名 |
| `standardFileDir` | string | **是** | - | 标准答案目录 |
| `standardFilePath` | string | **是** | - | 标准答案文件名 |
| `userFileDir` | string | **是** | - | 用户提交目录 |
| `userFilePath` | string | **是** | - | 用户提交文件名 |
| `userId` | string | **是** | - | 用户唯一标识符 |
| `logDetailPath` | string | 否 | `"eval/log_detail.jsonl"` | 详细日志路径（相对 evaluatorDir） |
| `logSummaryPath` | string | 否 | `"eval/log_summary.json"` | 日志摘要路径（相对 evaluatorDir） |
| `logRunPath` | string | 否 | `"eval/log_run.log"` | 运行日志路径（相对 evaluatorDir） |

### 响应

#### 成功响应 (200)

```json
{
  "code": 200,
  "msg": "提交任务成功",
  "data": {
    "task_id": "user_id_1234567890_abc123def456",
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
    "task_id": "user_id_1234567890_abc123def456",
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

### Task ID 生成规则

```python
task_id = f'{userId}_{created_at}_{md5_hash(code_input)}'
```

- **userId**: 用户标识符
- **created_at**: 任务创建时间戳
- **md5_hash**: `code_input` 对象的 MD5 哈希值

### 示例代码

#### Python

```python
import requests
import json

url = "http://localhost:8000/runner/submit"

payload = {
    "parameter": {
        "task_name": "sandbox_eval_task",
        "reset": True
    },
    "payload": {
        "code_input": {
            "evaluatorDir": "eval/user_123",
            "evaluatorPath": "eval_result.json",
            "standardFileDir": "eval/user_123/eval",
            "standardFilePath": "submit.jsonl",
            "userFileDir": "eval/user_123/submit",
            "userFilePath": "competition_001_1745225547.xlsx",
            "userId": "user_123"
        }
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

## 4. GET /runner/result - 获取任务状态和结果

### 描述

查询评测任务的执行状态和结果元数据。

**端点**:
```
GET /runner/result?task_id={task_id}
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | **是** | 任务唯一标识符（由 submit 接口返回） |

### 响应

#### 成功响应 (200) - 任务完成

```json
{
  "code": 200,
  "msg": "获取任务成功",
  "data": {
    "task_id": "user_id_1234567890_abc123def456",
    "info": "finished",
    "finished": true,
    "result": {
      "result_path": "/app/sandbox/eval/user_123/eval_result.json",
      "log_detail_path": "/app/sandbox/eval/user_123/log_detail.jsonl",
      "log_summary_path": "/app/sandbox/eval/user_123/log_summary.json",
      "log_run_path": "/app/sandbox/eval/user_123/log_run.log"
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
    "task_id": "user_id_1234567890_abc123def456",
    "info": "running",
    "finished": false
  }
}
```

#### 任务不存在 (500)

```json
{
  "code": 500,
  "msg": "user_id_1234567890_abc123def456: 任务不存在"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.task_id` | string | 任务 ID |
| `data.info` | string | 任务状态：`pending` \| `running` \| `finished` \| `error` |
| `data.finished` | boolean | 任务是否完成 |
| `data.result` | object | 任务结果路径（仅当任务完成时存在） |
| `data.result.result_path` | string | 评测结果 JSON 文件路径 |
| `data.result.log_detail_path` | string | 详细日志文件路径 |
| `data.result.log_summary_path` | string | 日志摘要文件路径 |
| `data.result.log_run_path` | string | 运行日志文件路径 |

### 示例代码

#### Python (轮询任务状态)

```python
import requests
import time

task_id = "user_id_1234567890_abc123def456"
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

## 5. GET /runner/result_source - 获取任务结果文件

### 描述

下载任务生成的文件，如评测结果 JSON、日志文件等。

**端点**:
```
GET /runner/result_source?task_id={task_id}&result_source_name={field_name}
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | **是** | 任务唯一标识符 |
| `result_source_name` | string | **是** | 结果字段名称（见下方支持的值） |

### 支持的 result_source_name 值

根据 `/runner/result` 返回的 `result` 对象：

| 值 | 说明 |
|----|------|
| `result_path` | 评测结果 JSON 文件 |
| `log_detail_path` | 详细日志文件 |
| `log_summary_path` | 日志摘要文件 |
| `log_run_path` | 运行日志文件 |

### 响应

#### 成功响应 (200)

返回文件的二进制内容，Content-Type 为 `multipart/form-data`。

#### 文件不存在 (500)

```json
{
  "code": 500,
  "msg": "/app/sandbox/eval/user_123/eval_result.json: 读取文件失败"
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

#### cURL

```bash
# 下载评测结果
curl -X GET "http://localhost:8000/runner/result_source?task_id=user_id_1234567890_abc123def456&result_source_name=result_path" \
  -o eval_result.json

# 下载详细日志
curl -X GET "http://localhost:8000/runner/result_source?task_id=user_id_1234567890_abc123def456&result_source_name=log_detail_path" \
  -o log_detail.jsonl

# 下载运行日志
curl -X GET "http://localhost:8000/runner/result_source?task_id=user_id_1234567890_abc123def456&result_source_name=log_run_path" \
  -o log_run.log
```

#### Python

```python
import requests

task_id = "user_id_1234567890_abc123def456"

# 首先获取任务状态
result_url = f"http://localhost:8000/runner/result?task_id={task_id}"
result_response = requests.get(result_url)
result_data = result_response.json()

if result_data["data"]["finished"]:
    result_paths = result_data["data"]["result"]

    # 下载评测结果
    for field_name, file_path in result_paths.items():
        file_url = f"http://localhost:8000/runner/result_source?task_id={task_id}&result_source_name={field_name}"

        file_response = requests.get(file_url)

        if file_response.status_code == 200:
            filename = file_path.split("/")[-1]
            with open(filename, "wb") as f:
                f.write(file_response.content)
            print(f"下载成功: {filename}")
        else:
            print(f"下载失败: {file_response.json()['msg']}")
```

---

## 6. 数据模型

### PayLoad

```typescript
interface PayLoad {
  created_at: number;        // 任务创建时间
  requested_at: number;      // 任务请求时间
  finished_at: number;       // 任务完成时间
  parameter: RunnerParameter;
  payload: SandboxEvalPayload;
}
```

### RunnerParameter

```typescript
interface RunnerParameter {
  task_name: string;         // 默认: "sandbox_eval_task"
  reset: boolean;            // 默认: true
}
```

### SandboxEvalPayload

```typescript
interface SandboxEvalPayload {
  code_input: SandboxProcessorData;
}
```

### SandboxProcessorData

```typescript
interface SandboxProcessorData {
  evaluatorDir: string;      // 评测结果目录
  evaluatorPath: string;     // 评测结果文件名
  standardFileDir: string;   // 标准答案目录
  standardFilePath: string;  // 标准答案文件名
  userFileDir: string;       // 用户提交目录
  userFilePath: string;      // 用户提交文件名
  userId: string;            // 用户 ID
  logDetailPath?: string;    // 默认: "eval/log_detail.jsonl"
  logSummaryPath?: string;   // 默认: "eval/log_summary.json"
  logRunPath?: string;       // 默认: "eval/log_run.log"
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
    result?: {
      result_path: string;
      log_detail_path: string;
      log_summary_path: string;
      log_run_path: string;
    };
  };
}
```

---

## 7. 任务执行流程

```
┌────────────────────────────────────────────────────────────────┐
│                        用户端                                   │
└────────────────────────────┬───────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌────────────────────┐ ┌──────────────────┐ ┌────────────────────┐
│ 1. 提取标准答案    │ │ 2. 提取用户提交  │ │ 3. 提交评测任务    │
│ extract_standard_ │ │ extract_submit_  │ │ POST /runner/submit│
│     file          │ │     file         │ │                    │
└─────────┬──────────┘ └────────┬─────────┘ └─────────┬──────────┘
          │                     │                      │
          ▼                     ▼                      │
┌─────────────────────────────────────┐                │
│  文件存储到 eval/{user_id}/         │                │
│  ├── eval.zip (标准答案)            │                │
│  └── submit/ (用户提交)             │                │
└─────────────────────────────────────┘                │
                                                        │
                            ┌──────────────────────────┘
                            │
                            ▼
                  ┌─────────────────────┐
                  │   任务队列           │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ SandboxEvalTask     │
                  │   prepare()         │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ 生成 input_param.json│
                  │ 验证文件存在性       │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ 执行 evaluate.py    │
                  │ (评测脚本)          │
                  └──────────┬──────────┘
                             │
             ┌───────────────┼───────────────┐
             │               │               │
             ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ eval_result. │ │ log_detail.  │ │ log_summary. │
    │   json       │ │   jsonl      │ │    json      │
    └──────────────┘ └──────────────┘ └──────────────┘
             │               │               │
             └───────────────┴───────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  4. 查询任务状态     │
                  │  GET /runner/result │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  5. 下载结果文件     │
                  │  GET /runner/result_│
                  │      source         │
                  └─────────────────────┘
```

### 执行步骤详解

1. **提取标准答案文件** (`POST /extract_standard_file`):
   - 上传包含标准答案的 zip 文件
   - 系统解压到 `eval/{user_id}/eval/`
   - 验证文件结构

2. **提取用户提交文件** (`POST /extract_submit_file`):
   - 上传用户提交的评测文件
   - 保存到 `eval/{user_id}/submit/`

3. **提交评测任务** (`POST /runner/submit`):
   - 生成唯一 `task_id`
   - 验证文件存在性
   - 创建 `input_param.json`
   - 任务入队

4. **任务执行** (异步):
   - 执行 `evaluate.py` 脚本
   - 生成评测结果和日志
   - 实时监控输出（60秒超时）

5. **查询结果** (`GET /runner/result`):
   - 轮询任务状态
   - 获取结果路径

6. **下载文件** (`GET /runner/result_source`):
   - 下载评测结果
   - 下载日志文件

### 文件目录结构

```
/app/sandbox/
└── eval/
    └── {user_id}/
        ├── standard_answer.zip          # 上传的标准答案
        ├── eval.zip                     # 内层评测文件
        ├── eval/                        # 解压后的标准答案
        │   ├── answer.txt
        │   ├── test_cases.json
        │   └── ...
        ├── submit/                      # 用户提交目录
        │   └── {rank_id}_{timestamp}.xlsx
        ├── input_param.json             # 评测输入参数
        ├── evaluate.py                  # 评测脚本（需预先存在）
        ├── eval_result.json             # 评测结果
        ├── log_detail.jsonl             # 详细日志
        ├── log_summary.json             # 日志摘要
        └── log_run.log                  # 运行日志
```

### 评测脚本接口

`evaluate.py` 需要接受以下参数：

```bash
python evaluate.py <input_param_path> <result_output_path>
```

**input_param.json 格式**:
```json
{
  "fileData": {
    "evaluatorDir": "/app/sandbox/eval/user_123",
    "evaluatorPath": "eval_result.json",
    "standardFileDir": "/app/sandbox/eval/user_123/eval",
    "standardFilePath": "/app/sandbox/eval/user_123/eval/answer.txt",
    "userFileDir": "/app/sandbox/eval/user_123/submit",
    "userFilePath": "/app/sandbox/eval/user_123/submit/submission.xlsx",
    "userId": "user_123",
    "logDetailPath": "/app/sandbox/eval/user_123/log_detail.jsonl",
    "logSummaryPath": "/app/sandbox/eval/user_123/log_summary.json",
    "logRunPath": "/app/sandbox/eval/user_123/log_run.log"
  }
}
```

**输出格式** (eval_result.json):
```json
{
  "score": 95.5,
  "passed": true,
  "details": {
    "test_cases": 10,
    "passed_cases": 9,
    "failed_cases": 1
  },
  "message": "评测通过"
}
```

---

## 8. 错误码说明

| HTTP 状态码 | 说明 | 处理建议 |
|------------|------|----------|
| 200 | 成功 | 正常处理响应数据 |
| 401 | 未授权 | nonce 认证失败（内部接口） |
| 409 | 任务被拒绝 | 任务参数验证失败，检查请求格式 |
| 500 | 服务器错误 | 查看错误消息 |

### 常见错误场景

#### 1. 标准答案文件不存在

```json
{
  "code": 500,
  "msg": "RuntimeError: standard file not found"
}
```

**原因**: 标准答案文件路径错误或未调用 `/extract_standard_file`

**解决**: 先调用 `/extract_standard_file` 上传标准答案

#### 2. 用户提交文件不存在

```json
{
  "code": 500,
  "msg": "RuntimeError: user file not found"
}
```

**原因**: 用户提交文件路径错误或未调用 `/extract_submit_file`

**解决**: 先调用 `/extract_submit_file` 上传用户提交

#### 3. 评测脚本执行失败

```json
{
  "code": 500,
  "msg": "RuntimeError: Evaluate script failed or was terminated due to silence."
}
```

**原因**: `evaluate.py` 执行出错或 60 秒无输出

**解决**: 检查 `log_run.log` 查看详细错误信息

#### 4. 任务不存在

```json
{
  "code": 500,
  "msg": "{task_id}: 任务不存在"
}
```

**原因**: task_id 不正确或任务已过期

**解决**: 确认 task_id 是否正确

#### 5. 文件读取失败

```json
{
  "code": 500,
  "msg": "/path/to/file: 读取文件失败"
}
```

**原因**: 文件不存在或路径错误

**解决**: 先调用 `/runner/result` 确认任务已完成

---

## 附录

### 相关文件

- [runner.py](../sandbox/server/servlet/runner.py) - API 端点实现
- [extract_file.py](../sandbox/server/servlet/extract_file.py) - 文件提取处理
- [sanbox_eval_task.py](../sandbox/tasks/sanbox_eval_task.py) - 任务定义
- [sanbox_started.py](../sandbox/processors/sanbox_started.py) - 评测处理器
- [flow_data.py](../sandbox/server/model/flow_data.py) - 数据模型定义

### 技术栈

- **Web 框架**: FastAPI
- **数据验证**: Pydantic
- **异步执行**: asyncio, anyio
- **文件处理**: zipfile, shutil

### 完整工作流示例

```python
import requests
import time
import json

# 配置
BASE_URL = "http://localhost:8000"
USER_ID = "user_123"
RANK_ID = "competition_001"

# 1. 上传标准答案
print("1. 上传标准答案...")
files = {'file': open('standard_answer.zip', 'rb')}
data = {'rank_id': RANK_ID, 'user_id': USER_ID}
response = requests.post(f"{BASE_URL}/extract_standard_file", files=files, data=data)
print(f"   标准: {response.json()}")

# 2. 上传用户提交
print("2. 上传用户提交...")
files = {'file': open('submission.xlsx', 'rb')}
data = {'rank_id': RANK_ID, 'user_id': USER_ID}
response = requests.post(f"{BASE_URL}/extract_submit_file", files=files, data=data)
user_filename = response.json()['id']
print(f"   提交: {response.json()}")

# 3. 提交评测任务
print("3. 提交评测任务...")
payload = {
    "parameter": {
        "task_name": "sandbox_eval_task",
        "reset": True
    },
    "payload": {
        "code_input": {
            "evaluatorDir": f"eval/{USER_ID}",
            "evaluatorPath": "eval_result.json",
            "standardFileDir": f"eval/{USER_ID}/eval",
            "standardFilePath": "submit.jsonl",
            "userFileDir": f"eval/{USER_ID}/submit",
            "userFilePath": f"{user_filename}.xlsx",
            "userId": USER_ID
        }
    }
}
response = requests.post(f"{BASE_URL}/runner/submit", json=payload)
task_id = response.json()['data']['task_id']
print(f"   任务 ID: {task_id}")

# 4. 轮询任务状态
print("4. 等待任务完成...")
while True:
    response = requests.get(f"{BASE_URL}/runner/result?task_id={task_id}")
    result = response.json()
    data = result['data']

    print(f"   状态: {data['info']}")

    if data['finished']:
        print("   任务完成!")
        break

    time.sleep(3)

# 5. 下载评测结果
print("5. 下载评测结果...")
result_paths = data['result']
for field, path in result_paths.items():
    response = requests.get(
        f"{BASE_URL}/runner/result_source",
        params={'task_id': task_id, 'result_source_name': field}
    )

    if response.status_code == 200:
        filename = path.split('/')[-1]
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"   已下载: {filename}")

        # 如果是 JSON 文件，打印内容
        if filename.endswith('.json'):
            print(f"   内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

print("\n完成!")
```

### 更新日志

- 2024-12-29: 初始版本，包含完整 API 文档
