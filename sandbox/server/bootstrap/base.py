from collections import defaultdict, deque
import threading
from typing import Dict, List, Optional, Set

from sandbox.server.model.flow_data import BaseFlowData


class UserTaskStateIndex:
    """
    用户全局任务状态索引：
    - 记录每个 user 当前处于“运行中”的任务 ID 集合
    - 提供增删与查询接口
    - 线程安全（简单用 Lock 即可）
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._user_tasks: Dict[str, Set[str]] = defaultdict(set)

    def mark_running(self, user_id: str, task_id: str) -> None:
        """标记某个任务为该用户的运行中任务。"""
        if not user_id or not task_id:
            return
        with self._lock:
            self._user_tasks[user_id].add(task_id)

    def mark_finished(self, user_id: str, task_id: str) -> None:
        """当任务进入终止态（完成/失败/取消）时，从索引中移除。"""
        if not user_id or not task_id:
            return
        with self._lock:
            tasks = self._user_tasks.get(user_id)
            if not tasks:
                return
            tasks.discard(task_id)
            if not tasks:
                self._user_tasks.pop(user_id, None)

    def has_running(self, user_id: str) -> bool:
        """该用户是否有任意运行中任务。"""
        if not user_id:
            return False
        with self._lock:
            return bool(self._user_tasks.get(user_id))

    def get_running_tasks(self, user_id: str) -> Set[str]:
        """返回该用户当前所有运行中的任务 ID（只读副本）。"""
        if not user_id:
            return set()
        with self._lock:
            return set(self._user_tasks.get(user_id, ()))

    def clear_user(self, user_id: str) -> None:
        """清空某个用户的所有任务索引（用于补偿/异常场景）。"""
        if not user_id:
            return
        with self._lock:
            self._user_tasks.pop(user_id, None)


class Bootstrap:
    """Used by web module to decide which secret for securing"""
    _NONCE: str = ''
    """最大的任务队列"""
    _MAX_ONGOING_TASKS: int = 100

    """任务队列"""
    _QUEUE: deque = deque()
    """进行的任务数据"""
    _TASK_DATA: Dict[str, BaseFlowData] = {}
    """进行的任务状态"""
    _TASK_STATES = {}
    """正在进行的任务"""
    _ONGOING_TASKS: List[str] = []

    def __init__(self):
        self._version = "v0.0.1"
        self._user_task_state_index = UserTaskStateIndex()

    @classmethod
    def from_config(cls, cfg=None):
        return cls()

    @property
    def version(self):
        return self._version

    @property
    def max_ongoing_tasks(self) -> int:
        return self._MAX_ONGOING_TASKS

    @property
    def ongoing_tasks(self) -> List[str]:
        return self._ONGOING_TASKS

    @property
    def queue(self) -> deque:
        return self._QUEUE

    @property
    def task_data(self) -> Dict[str, BaseFlowData]:
        return self._TASK_DATA

    @property
    def task_states(self) -> dict:
        return self._TASK_STATES

    @property
    def nonce(self) -> str:
        return self._NONCE

    def set_nonce(self, nonce: str):
        self._NONCE = nonce

    def update_user_task_index(self, user_id: str, task_id: str, finished: bool) -> None:
        """
        在任务状态变更时调用：
        - 如果进入运行态：写入索引
        - 如果进入终止态：从索引中移除
        """
        if finished:
            self._user_task_state_index.mark_finished(user_id, task_id)
        else:
            self._user_task_state_index.mark_running(user_id, task_id)

    def user_has_running_task(self, user_id: str) -> bool:
        return self._user_task_state_index.has_running(user_id)

    def get_user_running_tasks(self, user_id: str) -> Set[str]:
        return self._user_task_state_index.get_running_tasks(user_id)

    @staticmethod
    def extract_user_id(payload: BaseFlowData) -> Optional[str]:
        payload_data = getattr(payload, "payload", None)
        code_input = None
        if hasattr(payload_data, "code_input"):
            code_input = payload_data.code_input
        elif isinstance(payload_data, dict):
            code_input = payload_data.get("code_input") or payload_data.get("fileData")
        if isinstance(code_input, dict):
            return code_input.get("userId") or code_input.get("user_id")
        if hasattr(code_input, "userId"):
            return code_input.userId
        if hasattr(code_input, "user_id"):
            return code_input.user_id
        return None

    @classmethod
    async def run(cls):
        raise NotImplementedError

    @classmethod
    async def destroy(cls):
        raise NotImplementedError
