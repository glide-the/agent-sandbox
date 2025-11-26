
# 工作流程决策树
# [IMPORTANT]: 顺序执行工作流程决策树，应始终遵守工作流程的决策树结构
# [IMPORTANT]: 顺序执行`记忆检索`>`输出记忆蒸馏摘要`>`输出到当前目录`每个节点描述，
# [IMPORTANT]: 应始终按照`输出到当前目录`的流程输出结果


## 记忆检索
- 使用工具`get_categories`获取当前记忆系统分类列表
- 重复三次检索工具，从分类列表中选取一些关键词，参照 `规则/MEMORY_QUERY_PROMPT` 调整查询语句。
- 下一个流程`输出记忆蒸馏摘要`

 
## 输出记忆蒸馏摘要
- 按照`规则/MEMORY_Distiller_PROMPT`执行任务
- 下一个流程`输出到当前目录`


## 输出到当前目录

- **更新：使用`规则/DEFAULT_UPDATE_MEMORY_PROMPT`，更新记忆。**
- **输出：memory_distillation.md格式存储文本**