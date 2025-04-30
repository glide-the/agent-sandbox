from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class SandboxProcessorData(BaseModel):
    """
      填写input_param.json标准答案和测试提交文件，例如：

      {
        "fileData":{
          "evaluatorDir":"", # 默认("eval", user_id)
          "evaluatorPath":"", # 默认("eval", user_id, "eval_result.json")
          "standardFileDir":"", # 默认("eval", user_id, "eval")
          "standardFilePath":"answer.txt",
          "userFileDir":"", # 默认("eval", user_id, "submit")
          "userFilePath":"submit.txt", # 程序自动填写
          "logDetailPath": "eval/log_detail.jsonl",
          "logSummaryPath": "eval/log_summary.json",
          "logRunPath": "eval/log_run.log"
        }
      }
    """
    evaluatorDir: str
    evaluatorPath: str
    standardFileDir: str
    standardFilePath: str
    userFileDir: str
    userFilePath: str
    userId: str
    userImagesDir: str = ""
    is_mm_eval: bool = False
    logDetailPath: str = "eval/log_detail.jsonl"
    logSummaryPath: str = "eval/log_summary.json"
    logRunPath: str = "eval/log_run.log"


class BaseFlowData(BaseModel):
    """任务创建时间"""
    created_at: float = Field(default=0)
    """任务请求时间"""
    requested_at: float = Field(default=0)
    """任务完成时间"""
    finished_at: float = Field(default=0)


class RunnerParameter(BaseModel):
    task_name: str = Field(default="sandbox_eval_task")
    reset: bool = Field(default=True)


class SandboxEvalFlowData(BaseModel):
    code_input: SandboxProcessorData


class PayLoad(BaseFlowData):
    parameter: RunnerParameter
    payload: Union[Dict, SandboxEvalFlowData]
