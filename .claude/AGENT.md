# Agent Sandbox 项目说明

## 项目概述

Agent Sandbox 是一个基于 Python 的 AI 智能体沙箱执行环境，旨在为 AI Agent 提供安全、可控的执行环境。该项目支持多种任务类型，包括研究型 Agent（Research Agent）和通用代码评测。

## 核心架构

### 1. 组件层次

```
用户请求 → Web API → Bootstrap → Task → Processor → 实际执行
                ↓
           状态报告
           日志记录
```

### 2. 关键概念

- **Runner**: 任务执行器实例，包含 `task_id` 和 `flow_data`
- **FlowData**: 任务数据载体，根据任务类型有不同的子类
- **Task**: 任务类，负责任务的生命周期管理
- **Processor**: 处理器，负责具体的业务逻辑执行
- **Bootstrap**: 启动引导器，管理 Web 服务和任务调度

### 3. 任务执行流程

```python
# 1. Prepare 阶段
def prepare(cls, payload: PayLoad) -> Runner:
    # 解析请求参数
    # 创建 FlowData
    # 生成 task_id
    # 返回 Runner 实例

# 2. Dispatch 阶段
async def dispatch(self, runner: Runner) -> None:
    # 报告初始状态
    # 调用 Processor 处理
    # 报告进度
    # 保存结果

# 3. Complete 阶段
def complete(self, runner: Runner):
    # 清理资源
```

## 项目结构

```
agent-sandbox/
├── sandbox/                    # 核心代码
│   ├── tasks/                  # 任务定义
│   │   ├── base_task.py       # 基础任务类
│   │   ├── sanbox_eval_task.py    # 评测任务
│   │   └── research_agent_task.py # 研究型 Agent 任务
│   ├── processors/             # 处理器
│   │   ├── base_processor.py  # 基础处理器
│   │   ├── research_agent_processor.py
│   │   └── sanbox_started.py
│   ├── server/                 # Web 服务
│   │   ├── servlet/           # API 端点
│   │   ├── bootstrap/         # 启动引导
│   │   └── model/             # 数据模型
│   ├── common/                # 通用工具
│   │   ├── registry.py        # 注册表
│   │   ├── logs.py            # 日志配置
│   │   └── utils.py           # 工具函数
│   └── start/                 # 启动入口
│       └── main.py            # 主入口
├── app/sandbox/               # 运行时目录
├── sandbox.yaml               # 配置文件
└── logs/                      # 日志输出
```

## 配置文件说明

### sandbox.yaml

```yaml
# 预处理器定义
preprocess:
  - sandbox_started_processor:
      name: "sandbox_started_processor"
      cwd: "/path/to/sandbox"

# 任务定义
tasks:
  - sandbox_eval_task:
      name: "sandbox_eval_task"
      preprocess:
        - sandbox_started_processor:
            processor: "sandbox_started_processor"
            processor_name: "Sandbox"

# 启动配置
bootstrap:
  - runner_bootstrap_web:
      name: "runner_bootstrap_web"
      host: "0.0.0.0"
      port: 10000
      max_ongoing_tasks: 10
```

## 启动模式

### 1. Demo 模式
用于快速测试和演示，不启动 Web 服务。

```bash
python -m sandbox.start.main -m demo -v
```

### 2. Web 模式
启动 Web API 服务器。

```bash
python -m sandbox.start.main -m web
```

### 3. Web Runner 模式
启动任务执行器，处理实际的任务请求。

```bash
python -m sandbox.start.main -m web_runner --nonce <token>
```

## 开发指南

### 添加新的 Processor

1. 在 `sandbox/processors/` 创建新文件
2. 继承 `BaseProcessor`
3. 实现 `match()` 和 `__call__()` 方法
4. 在 `sandbox/processors/__init__.py` 中注册

示例：

```python
from sandbox.processors import BaseProcessor, registry

@registry.register_processor("my_processor")
class MyProcessor(BaseProcessor):
    def match(self, sandbox_input):
        # 判断是否支持该输入
        return sandbox_input.type == "MyType"

    def __call__(self, sandbox_input, topic=""):
        # 执行具体逻辑
        result_path = self.do_work(sandbox_input)
        log_path = self.generate_logs()
        return result_path, log_path, log_summary, log_run
```

### 添加新的 Task

1. 在 `sandbox/tasks/` 创建新文件
2. 继承 `SandboxTaskAbstract`
3. 实现 `prepare()`, `dispatch()`, `complete()` 方法
4. 使用 `@registry.register_task()` 注册

示例：

```python
from sandbox.tasks import SandboxTaskAbstract, registry
from sandbox.server.model.flow_data import PayLoad

@registry.register_task("my_task")
class MyTask(SandboxTaskAbstract):
    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        # 构建任务
        pass

    async def dispatch(self, runner: Runner) -> None:
        # 执行任务
        pass

    def complete(self, runner: Runner):
        # 清理工作
        pass
```

## 常用命令

### 安装依赖
```bash
poetry install
```

### 运行测试
```bash
poetry run pytest
```

### 代码检查
```bash
poetry run ruff check sandbox/
```

### 查看日志
```bash
tail -f logs/web_<timestamp>/start_logger.log
```

## 调试技巧

1. **启用详细日志**: 使用 `-v` 参数
2. **查看日志文件**: 检查 `logs/` 目录
3. **检查配置**: 确认 `sandbox.yaml` 配置正确
4. **验证依赖**: 使用 `poetry check` 检查依赖
5. **逐步测试**: 先用 demo 模式测试，再启动 Web 服务

## 重要注意事项

1. **异步编程**: 所有任务执行都是异步的，注意使用 `async/await`
2. **错误处理**: 捕获异常并上报 error 状态
3. **日志记录**: 使用 `self.logger` 记录重要信息
4. **资源清理**: 在 `complete()` 方法中清理资源
5. **状态报告**: 使用 `report_progress()` 上报任务状态

## 依赖说明

- **FastAPI**: Web 框架
- **Claude Agent SDK**: Anthropic Agent 集成
- **PyMilvus**: 向量数据库
- **Elasticsearch**: 全文检索
- **OpenAI**: LLM 接口
- **Pydantic**: 数据验证
- **Pandas/NumPy**: 数据处理

## 常见问题

### Q: 端口被占用怎么办？
A: 修改 `sandbox.yaml` 中的 `port` 配置

### Q: 如何添加新的环境变量？
A: 在 `.env` 文件或系统环境变量中添加

### Q: 任务执行超时？
A: 调整 `web_client_timeout` 参数

### Q: 如何查看任务日志？
A: 检查 `logs/` 目录下对应时间戳的日志文件

## API 示例

### 提交研究任务

```bash
curl -X POST http://localhost:10000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "parameter": {
      "task_name": "research_agent_task",
      "reset": true
    },
    "payload": {
      "code_input": {
        "userId": "user_123",
        "type": "ResearchAgentSandbox",
        "workspace": "/app/sandbox/workspace/user_123"
      },
      "topic": "研究 AI 技术发展趋势"
    }
  }'
```

### 查询任务状态

```bash
curl http://localhost:10000/status/{task_id}
```

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交变更
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License
