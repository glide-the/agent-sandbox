from typing import Optional


class TaskRejectedError(RuntimeError):
    def __init__(self, message: str, 
                 running_task_ids: Optional[list] = None,
                 code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.running_task_ids = running_task_ids