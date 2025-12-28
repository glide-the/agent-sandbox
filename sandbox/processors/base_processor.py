"""
 Copyright (c) 2022, salesforce.com, inc.
 All rights reserved.
 SPDX-License-Identifier: BSD-3-Clause
 For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
"""

from abc import abstractmethod

from omegaconf import OmegaConf

from sandbox.load.serializable import Serializable


class ProcessorData(Serializable):
    """
    The base abstract ProcessorData class.
    """

    @property
    @abstractmethod
    def type(self) -> str:
        """Type of the Message, used for serialization."""

    @property
    def lc_serializable(self) -> bool:
        """Whether this class is Processor serializable."""
        return True


class BaseProcessor:
    """
    音频处理器有抽象处理器Processor，通过单独的Processor配置，
    通过from_config工厂方法预加载音频处理器
    """
    def __init__(self):
        self.transform = lambda x: x
        return

    def __call__(self, data: ProcessorData):
        return self.transform(data)

    @classmethod
    def match(cls, data: ProcessorData):
        """
        匹配处理器
        :param data:
        :return:
        """
        raise NotImplementedError

    def init_paths(self, code_input: ProcessorData, task_id: str) -> dict:
        """
        初始化任务相关的输出 / 日志路径，返回统一结构的路径字典：
        {
            'result_path': str,
            'log_detail_path': str,
            'log_summary_path': str,
            'log_run_path': str,
        }

        默认实现抛异常，具体 Processor 里按各自逻辑实现。
        :param code_input: 当前任务的输入数据（通常是 SandboxProcessorData / ResearchAgentSandboxProcessorData）
        :param task_id: 当前任务 id，用于需要按任务维度隔离目录的场景
        """
        raise NotImplementedError("init_paths must be implemented in subclasses of BaseProcessor")

    @classmethod
    def from_config(cls, cfg=None):
        return cls()

    def build(self, **kwargs):
        cfg = OmegaConf.create(kwargs)

        return self.from_config(cfg)
