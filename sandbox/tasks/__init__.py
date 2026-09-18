from typing import List

import numpy as np

from sandbox.common.registry import registry
from sandbox.tasks.base_task import BaseTask, FlowData, Runner, SandboxTaskAbstract
from sandbox.tasks.sanbox_eval_task import SandboxEvalFlowData
from sandbox.tasks.research_agent_task import ResearchAgentFlowData, ResearchAgentTask  # noqa: F401
from sandbox.tasks.agent_sandbox_task import (
    AgentMem0FlowData,
    AgentWorkspaceL2FlowData,
    AgentWorkspaceL3FlowData,
)
from sandbox.tasks.sheetsage2_task import SheetSage2FlowData, SheetSage2Task
from sandbox.tasks.yue2_task import YuE2FlowData, YuE2Task
from sandbox.tasks.music_utility_task import (
    MusicListenFlowData,
    MusicListenTask,
    MusicScoreFlowData,
    MusicScoreTask,
)

__all__ = [
    "BaseTask",
    "SandboxTaskAbstract",
    "SandboxEvalFlowData",
    "ResearchAgentFlowData",
    "AgentMem0FlowData",
    "AgentWorkspaceL2FlowData",
    "AgentWorkspaceL3FlowData",
    "YuE2FlowData",
    "YuE2Task",
    "SheetSage2FlowData",
    "SheetSage2Task",
    "MusicScoreFlowData",
    "MusicScoreTask",
    "MusicListenFlowData",
    "MusicListenTask",
    "Runner",
    "FlowData",
    "load_task",
    "get_task",
    "tasks_cache"
]

tasks_cache = {}


def load_task(config: dict = None):
    """
    Load preprocessor configs and construct preprocessors.

    If no preprocessor is specified, return BaseProcessor, which does not do any preprocessing.

    Args:
        config (dict): preprocessor configs.

    Returns:
        vits_processors (dict): preprocessors for vits inputs.
        rvc_processors (dict): preprocessors for rvc inputs.

    """

    if config is None:
        raise RuntimeError("Load preprocessor configs is None.")

    def _build_task_from_cfg(cfg):
        return (
            registry.get_task_class(cfg.name).from_config(cfg)
            if cfg is not None
            else BaseTask()
        )
    for task in config:
        for key, task_cfg in task.items():  # 使用 .items() 方法获取键值对
            processors = _build_task_from_cfg(task_cfg)
            tasks_cache[key] = processors


def get_task(key: str) -> BaseTask:

    if not tasks_cache.get(key):
        raise ValueError(f'Could not find task for: "{key}". '
                         f'Choose from the following: %s' % ','.join(tasks_cache))

    return tasks_cache[key]
