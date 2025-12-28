# Agent Sandbox - AI Agent 指导文档

你是 Agent Sandbox 项目的专业开发助手。这是一个基于 Python 的 AI 智能体沙箱执行环境项目。

## 项目核心理解

### 架构模式
Agent Sandbox 采用 **任务-处理器** 分离架构：
- **Task（任务）**: 负责任务生命周期管理（prepare → dispatch → complete）
- **Processor（处理器）**: 负责具体业务逻辑执行
- **Runner（执行器）**: 任务执行单元，携带 task_id 和 flow_data

### 技术栈
- **异步框架**: asyncio + FastAPI
- **LLM 集成**: Claude Agent SDK, OpenAI API
- **数据存储**: PyMilvus（向量）, Elasticsearch（全文）
- **配置管理**: YAML + OmegaConf
- **包管理**: Poetry

## 关键设计模式

### 1. 注册表模式
使用装饰器注册组件：
```python
@registry.register_task("task_name")
class MyTask(SandboxTaskAbstract):
    pass

@registry.register_processor("processor_name")
class MyProcessor(BaseProcessor):
    pass
```

### 2. 数据流模式
```python
PayLoad (请求)
  ↓
prepare() → Runner (task_id, flow_data)
  ↓
dispatch() → Processor处理 → 结果
  ↓
save_task_write() → 保存文件
```

### 3. 异步执行模式
```python
async def dispatch(self, runner: Runner):
    await self.report_progress(state="processing")
    result = await processor.process()
    await self.save_task_write(result)
```

## 工作流程指导

### 当用户要求"添加新功能"时

1. **分析需求**：
   - 这是新 Task 还是新 Processor？
   - 需要修改哪些现有文件？
   - 是否需要更新配置文件？

2. **查找参考**：
   - 查看类似的现有实现
   - 阅读 [sandbox/tasks/](sandbox/tasks/) 中的示例
   - 理解 [sandbox/processors/](sandbox/processors/) 中的模式

3. **实现步骤**：
   - 继承正确的基类（SandboxTaskAbstract 或 BaseProcessor）
   - 实现必要的方法
   - 添加日志记录
   - 在配置文件中注册

4. **测试验证**：
   - 使用 demo 模式测试
   - 检查日志输出
   - 验证错误处理

### 当用户要求"修复 Bug"时

1. **定位问题**：
   - 查看错误日志（logs/ 目录）
   - 理解错误堆栈
   - 找到问题代码位置

2. **分析原因**：
   - 是配置问题？
   - 是逻辑错误？
   - 是异步处理不当？
   - 是资源泄漏？

3. **修复方案**：
   - 添加适当的错误处理
   - 修复逻辑错误
   - 添加必要的日志
   - 考虑边界情况

4. **验证修复**：
   - 本地测试
   - 检查日志
   - 确认没有引入新问题

### 当用户要求"优化性能"时

关注点：
1. **异步效率**：确保 I/O 操作使用 async/await
2. **资源管理**：及时清理资源，避免内存泄漏
3. **并发控制**：合理设置 `max_ongoing_tasks`
4. **日志优化**：避免过度日志影响性能

### 当用户要求"添加测试"时

1. 单元测试：测试 Task 和 Processor 的核心逻辑
2. 集成测试：测试完整的任务流程
3. 使用 pytest 框架
4. 添加必要的 mock 和 fixture

## 代码规范

### Python 风格
- 使用类型注解
- 遵循 PEP 8
- 使用有意义变量名
- 添加必要的注释

### 异步编程
```python
# 好的做法
async def process(self):
    result = await async_operation()
    return result

# 避免
def process(self):
    result = sync_operation()  # 在异步上下文中使用同步操作
    return result
```

### 错误处理
```python
try:
    await self.report_progress(state="processing")
    result = await processor(data)
    await self.save_task_write(result)
except Exception as e:
    self.logger.error(f"Task failed: {e}", exc_info=True)
    await self.report_progress(state="error")
    raise
```

### 日志记录
```python
# 开始
self.logger.info(f"Task {task_id} started")

# 进度
self.logger.info(f"Task {task_id} processing step {step}")

# 成功
self.logger.info(f"Task {task_id} completed successfully")

# 错误
self.logger.error(f"Task {task_id} failed: {error}", exc_info=True)
```

## 关键文件说明

### 入口文件
- [sandbox/start/main.py](sandbox/start/main.py): 命令行入口，处理启动参数

### 核心基类
- [sandbox/tasks/base_task.py](sandbox/tasks/base_task.py): 所有任务的基类
- [sandbox/processors/base_processor.py](sandbox/processors/base_processor.py): 所有处理器的基类

### 示例实现
- [sandbox/tasks/research_agent_task.py](sandbox/tasks/research_agent_task.py): 研究型 Agent 任务示例
- [sandbox/processors/research_agent_processor.py](sandbox/processors/research_agent_processor.py): 研究型 Agent 处理器示例

### 配置
- [sandbox.yaml](sandbox.yaml): 主配置文件

## 常见操作

### 修改配置
1. 编辑 [sandbox.yaml](sandbox.yaml)
2. 重启服务使配置生效

### 添加新依赖
1. 编辑 [pyproject.toml](pyproject.toml)
2. 运行 `poetry lock`
3. 运行 `poetry install`

### 调试任务
1. 启用详细模式：`-v` 参数
2. 查看日志：`logs/` 目录
3. 使用 demo 模式快速测试

### 查看 API 文档
启动 Web 服务后访问：`http://localhost:10000/docs`

## 重要提醒

⚠️ **注意事项**：
1. 所有任务执行都是异步的，注意 async/await 使用
2. 必须在配置文件中注册新的 Task 和 Processor
3. 确保正确的错误处理和日志记录
4. 测试时注意清理生成的文件和日志
5. 修改配置后需要重启服务

✅ **最佳实践**：
1. 修改代码前先阅读相关文件
2. 保持与现有架构模式一致
3. 添加适当的日志和错误处理
4. 使用 demo 模式快速测试
5. 检查日志验证功能

## 项目特性

- **任务类型**: SandboxEvalTask, ResearchAgentTask
- **处理器**: SandboxStartedProcessor, ResearchAgentProcessor
- **启动模式**: demo, web, web_runner
- **存储**: Milvus 向量数据库, Elasticsearch 全文检索
- **LLM**: 支持 Claude 和 OpenAI

## 快速参考

### 运行项目
```bash
# Demo 模式
python -m sandbox.start.main -m demo -v

# Web 服务
python -m sandbox.start.main -m web

# Runner 模式
python -m sandbox.start.main -m web_runner --nonce <token>
```

### 查看日志
```bash
# 实时查看最新日志
tail -f logs/web_*/start_logger.log

# 查看错误日志
grep ERROR logs/web_*/start_logger.log
```

### 代码检查
```bash
# 语法检查
ruff check sandbox/

# 格式化
ruff format sandbox/
```

记住：你是在帮助开发者理解和维护 Agent Sandbox 项目。始终保持代码质量和架构一致性！
