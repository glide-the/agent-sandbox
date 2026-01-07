# Agent Sandbox

一个基于 Python 的智能体沙箱执行环境，用于安全地运行和管理 AI Agent 任务，支持研究型 Agent 和通用代码评测。

## 项目简介

Agent Sandbox 是一个灵活的沙箱执行框架，旨在为 AI Agent 提供安全的执行环境。该项目支持多种任务类型，包括研究型 Agent（Research Agent）和代码评测任务，通过 Web API 提供服务，并支持任务状态跟踪、日志记录和结果管理。

## 主要特性

- **多任务支持**: 支持研究型 Agent、代码评测等多种任务类型
- **异步执行**: 基于 asyncio 的异步任务执行框架
- **Web API**: 基于 FastAPI 的 RESTful API 接口
- **任务追踪**: 实时任务状态监控和进度报告
- **日志管理**: 完善的日志记录系统，支持分级别日志输出
- **配置灵活**: 通过 YAML 配置文件管理任务和处理器
- **沙箱隔离**: 为每个任务提供独立的执行环境

## 项目结构

```
agent-sandbox/
├── sandbox/                  # 核心代码模块
│   ├── common/              # 通用工具类
│   │   ├── general.py       # 通用功能
│   │   ├── registry.py      # 注册表系统
│   │   ├── logs.py          # 日志配置
│   │   └── utils.py         # 工具函数
│   ├── load/                # 序列化相关
│   ├── server/              # Web 服务器
│   │   ├── bootstrap/       # 启动引导
│   │   ├── model/           # 数据模型
│   │   └── servlet/         # API 端点
│   ├── start/               # 启动入口
│   │   ├── core.py          # 核心逻辑
│   │   └── main.py          # 主入口
│   └── tasks/               # 任务定义
│       ├── base_task.py     # 基础任务类
│       ├── sanbox_eval_task.py    # 评测任务
│       └── research_agent_task.py # 研究型 Agent 任务
├── app/                     # 应用运行目录
│   └── sandbox/             # 沙箱工作空间
├── scripts/                 # 脚本工具
├── docs/                    # 文档
├── sandbox.yaml             # 配置文件
├── pyproject.toml           # 项目配置
└── README.md                # 项目说明
```

## 环境要求

- Python >= 3.10, < 3.12
- Poetry (用于依赖管理)

## 安装

### 1. 克隆项目

```bash
git clone <repository-url>
cd agent-sandbox
```

### 2. 安装依赖

使用 Poetry 安装依赖：

```bash
poetry install
```

或激活虚拟环境后手动安装：

```bash
poetry shell
pip install -r requirements.txt
```

## 配置

项目的主要配置文件为 [sandbox.yaml](sandbox.yaml)，包含以下配置项：

### preprocess（预处理器）

定义可用的任务处理器：

```yaml
preprocess:
  - sandbox_started_processor:
      name: "sandbox_started_processor"
      cwd: "/path/to/sandbox"
  - research_agent_processor:
      name: "research_agent_processor"
      cwd: "/path/to/sandbox"
```

### tasks（任务）

注册任务及其对应的处理器：

```yaml
tasks:
  - sandbox_eval_task:
      name: "sandbox_eval_task"
      preprocess:
        - sandbox_started_processor:
            processor: "sandbox_started_processor"
            processor_name: "Sandbox"
```

### bootstrap（启动配置）

Web 服务配置：

```yaml
bootstrap:
  - runner_bootstrap_web:
      name: "runner_bootstrap_web"
      host: "0.0.0.0"
      port: 10000
      max_ongoing_tasks: 10
      web_client_timeout: 1800
      finished_task_remove_timeout: 100
```

## 使用方法

### 启动模式

项目支持三种运行模式：

#### 1. Demo 模式

用于快速测试和演示：

```bash
python -m sandbox.start.main -m demo
```

#### 2. Web 模式

启动 Web API 服务器：

```bash
python -m sandbox.start.main -m web
```

#### 3. Web Runner 模式

启动任务执行器：

```bash
python -m sandbox.start.main -m web_runner --nonce <your-nonce>
```

### 命令行参数

- `-m, --mode`: 运行模式（demo/web/web_runner）
- `-v, --verbose`: 输出调试信息
- `--speakers-config-file`: 配置文件路径（默认: sandbox.yaml）
- `--nonce`: 用于 Web 服务器间通信的安全令牌

## Docker 部署

### 打包应用

使用 Poetry 打包项目：

```bash
poetry build
```

打包完成后会在 `dist/` 目录生成 `agent_sandbox-0.1.0-py3-none-any.whl` 文件。

### 复制打包文件到 Docker 目录

```bash
cp dist/agent_sandbox-0.1.0-py3-none-any.whl docker/sandbox/
cp sandbox.yaml docker/sandbox/
```

### 使用 Docker Compose

项目提供了 Docker Compose 配置文件，可以快速部署服务：

```bash
cd docker
docker-compose up -d
```

服务将在 `http://localhost:10000` 上运行。

### 手动构建 Docker 镜像

如果需要手动构建镜像：

```bash
cd docker/sandbox
docker build -t sandbox-service:1.0.0 .
```

### 配置说明

Docker 部署相关配置：
- **端口**: 默认映射 10000 端口
- **时区**: 默认设置为 Asia/Shanghai
- **数据卷**: 映射本地 `agent-sandbox` 目录到容器 `/app/sandbox/agent-sandbox`

环境变量可以在 `docker/docker-compose.yml` 中修改：

```yaml
environment:
  - TZ="Asia/Shanghai"
```

### 镜像仓库

镜像推送到私有仓库：
```bash
docker tag sandbox-service:1.0.0 10.50.104.66/agent-prod/sandbox-service:1.0.0
docker push 10.50.104.66/agent-prod/sandbox-service:1.0.0
```

## API 接口

### 提交任务

向 `/submit` 端点 POST 数据来提交新任务。

```json
{
  "code_input": {
    "userId": "user_123",
    "type": "Sandbox",
    "workspace": "/path/to/workspace",
    "config": {}
  }
}
```

### 查询任务状态

通过任务 ID 查询执行状态和结果。

### 任务执行流程

1. 接收任务请求
2. 创建 Runner 实例
3. 调用相应的 Processor 处理任务
4. 实时报告进度
5. 保存执行结果和日志
6. 返回最终结果

## 任务类型

### SandboxEvalTask

通用沙箱评测任务，支持代码执行和结果评测。

### ResearchAgentTask

研究型 Agent 任务，支持：
- 多步骤研究流程
- 数据分析和报告生成
- SQL 查询执行
- 向量检索（集成 Milvus）

## 开发指南

### 添加新的 Processor

1. 在 `sandbox/processors/` 下创建新的处理器类
2. 继承 `BaseProcessor`
3. 实现 `match()` 和 `__call__()` 方法
4. 在 [sandbox.yaml](sandbox.yaml) 中注册

### 添加新的 Task

1. 在 `sandbox/tasks/` 下创建新的任务类
2. 继承 `SandboxTaskAbstract`
3. 实现 `prepare()`, `dispatch()`, `complete()` 方法
4. 在注册表中注册任务

## 依赖说明

主要依赖包括：

- **FastAPI & Uvicorn**: Web 框架
- **Pydantic**: 数据验证
- **OpenAI**: LLM 接口
- **Claude Agent SDK**: Anthropic Agent 集成
- **PyMilvus**: 向量数据库
- **Elasticsearch**: 全文检索
- **Pandas & NumPy**: 数据处理
- **Jieba & NLTK**: 自然语言处理
- **Text2Vec**: 文本向量化

## 日志

日志文件存储在 `logs/` 目录下，按运行模式和时间戳组织：

- `web_<timestamp>/`: Web 服务日志
- `web_runner_<timestamp>/`: Runner 日志

## 常见问题

### 1. 端口被占用

修改 [sandbox.yaml](sandbox.yaml) 中的 `port` 配置。

### 2. 任务超时

调整 `web_client_timeout` 参数。

### 3. 工作目录权限

确保沙箱工作目录有正确的读写权限。

## 许可证

MIT License

## 作者

glide the <dmeck@suoxya.com>

## 贡献

欢迎提交 Issue 和 Pull Request！

## 相关资源

- [Claude Agent SDK 文档](https://docs.anthropic.com/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Poetry 文档](https://python-poetry.org/docs/)
