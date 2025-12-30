import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from sandbox.common.registry import registry
from sandbox.processors import (
    BaseProcessor,
    ProcessorData,
    ResearchAgentSandboxProcessorData,
)

from sandbox.common.research_agent.utils.subagent_tracker import SubagentTracker
from sandbox.common.research_agent.utils.transcript import TranscriptWriter
from sandbox.common.research_agent.utils.message_handler import process_assistant_message
from sandbox.common.research_agent import load_prompt
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition, HookMatcher

logger = logging.getLogger(__name__)


class SandboxTranscriptWriter(TranscriptWriter):
    """
    扩展 TranscriptWriter，额外把写出的内容缓存到内存里，
    方便后面生成 log_summary_path 的概要信息。
    """

    def __init__(self, transcript_file: Path):
        super().__init__(transcript_file)
        self._buffer = []

    @property
    def buffer(self) -> str:
        return "".join(self._buffer)

    def write(self, text: str, end: str = "", flush: bool = True):
        self._buffer.append(text + end)
        super().write(text, end=end, flush=flush)

    def write_to_file(self, text: str, end: str = "", flush: bool = True):
        self._buffer.append(text + end)
        super().write_to_file(text, flush=flush)


@registry.register_processor("research_agent_processor")
class ResearchAgentProcessor(BaseProcessor):
    """
    直接在 sandbox 中执行 research_agent 的业务逻辑，
    无需子进程。
    """

    _client: Optional["ClaudeSDKClient"] = None
    _options: Optional["ClaudeAgentOptions"] = None
    _client_lock = asyncio.Lock()

    def __init__(self, cwd: str, prompts: Optional[Dict[str, str]] = None):
        """
        :param cwd: sandbox 的工作根目录（由 YAML 配置中的 cwd 控制）
        :param prompts: 可选的 prompt 覆盖配置
            示例：
            prompts:
              lead_agent: /path/to/lead_agent.txt
              researcher: /path/to/researcher.txt
              data_analyst: /path/to/data_analyst.txt
              report_writer: /path/to/report_writer.txt
        """
        super().__init__()
        self.cwd = cwd
        self.prompt_overrides = prompts or {}
        load_dotenv()

    @classmethod
    def from_config(cls, cfg=None):
        if cfg is None:
            raise RuntimeError("from_config cfg is None.")

        cwd = cfg.get("cwd", "/app/sandbox")

        prompts = {}
        if "prompts" in cfg:
            prompts = dict(cfg.prompts)

        return cls(cwd=cwd, prompts=prompts)

    def match(self, data: ProcessorData):
        return getattr(data, "type", "") == "ResearchAgentSandbox"

    def init_paths(self, code_input: ResearchAgentSandboxProcessorData, task_id: str) -> dict:
        """
        利用现有 _init_workspace 逻辑，基于 code_input 初始化：
        - workspace 目录
        - 日志目录（logDetailPath / logSummaryPath / logRunPath）
        - result.json 路径
        """
        workspace = self._init_workspace(code_input)

        log_detail_file = Path(code_input.logDetailPath)
        log_summary_file = Path(code_input.logSummaryPath)
        log_run_file = Path(code_input.logRunPath)

        result_path = (log_summary_file.parent / "result.json").as_posix()
        Path(result_path).parent.mkdir(parents=True, exist_ok=True)

        return {
            "result_path": result_path,
            "log_detail_path": log_detail_file.as_posix(),
            "log_summary_path": log_summary_file.as_posix(),
            "log_run_path": log_run_file.as_posix(),
        }

    async def __call__(self, code_input: ResearchAgentSandboxProcessorData, topic: str):
        result_path, log_detail_path, log_summary_path, log_run_path = await self._run_research(
            code_input=code_input, topic=topic
        )
        return result_path, log_detail_path, log_summary_path, log_run_path

    async def _ensure_client(self, options: "ClaudeAgentOptions") -> "ClaudeSDKClient":
        if ResearchAgentProcessor._client is not None:
            return ResearchAgentProcessor._client

        async with self._client_lock:
            if ResearchAgentProcessor._client is None:
                client = ClaudeSDKClient(options=options)
                ResearchAgentProcessor._client = await client.__aenter__()
                ResearchAgentProcessor._options = options

        return ResearchAgentProcessor._client

    def _resolve_prompt(self, default_filename: str, override_key: str) -> str:
        override_path = self.prompt_overrides.get(override_key)
        if override_path:
            prompt_path = Path(override_path)
            with prompt_path.open("r", encoding="utf-8") as handle:
                return handle.read().strip()

        return load_prompt(default_filename)

    def _init_workspace(self, code_input: ResearchAgentSandboxProcessorData) -> Path:
        cwd = Path(self.cwd)

        if code_input.workspace:
            workspace = Path(code_input.workspace)
            if not workspace.is_absolute():
                workspace = cwd / workspace / code_input.userId
        else:
            workspace = cwd / "workspace" / code_input.userId

        workspace.mkdir(parents=True, exist_ok=True)

        user_files_dir = workspace / code_input.userFilesDir
        user_files_dir.mkdir(parents=True, exist_ok=True)

        user_logs_dir = workspace / code_input.userLogsDir
        user_logs_dir.mkdir(parents=True, exist_ok=True)

        code_input.logDetailPath = (workspace / code_input.logDetailPath).as_posix()
        code_input.logSummaryPath = (workspace / code_input.logSummaryPath).as_posix()
        code_input.logRunPath = (workspace / code_input.logRunPath).as_posix()

        import sandbox.common.research_agent as research_agent
        project_root = Path(research_agent.__file__).resolve().parent
        claude_src = project_root / ".claude"
        mcp_src = project_root / ".mcp.json"

        claude_dst = workspace / ".claude"
        mcp_dst = workspace / ".mcp.json"

        if claude_src.exists() and not claude_dst.exists():
            shutil.copytree(claude_src, claude_dst)
        if mcp_src.exists() and not mcp_dst.exists():
            shutil.copy(mcp_src, mcp_dst)

        return workspace

    async def _run_research(self, code_input: ResearchAgentSandboxProcessorData, topic: str):
        workspace = self._init_workspace(code_input)

        original_cwd = Path.cwd()
        os.chdir(workspace)

        log_detail_file = Path(code_input.logDetailPath)
        log_summary_file = Path(code_input.logSummaryPath)
        log_run_file = Path(code_input.logRunPath)

        try:
            transcript_writer = SandboxTranscriptWriter(log_run_file)

            session_dir = log_detail_file.parent
            session_dir.mkdir(parents=True, exist_ok=True)
            tracker = SubagentTracker(transcript_writer=transcript_writer, session_dir=session_dir)

            lead_agent_prompt = self._resolve_prompt("lead_agent_sql.txt", "lead_agent")
            researcher_prompt = self._resolve_prompt("researcher_exa_search.txt", "researcher")
            data_analyst_prompt = self._resolve_prompt("data_analyst_sql.txt", "data_analyst")
            report_writer_prompt = self._resolve_prompt("report_writer.txt", "report_writer")

            agents = {
                "researcher": AgentDefinition(
                    description=(
                        "Use this agent when you need to gather research information on any topic. "
                        "The researcher uses web search to find relevant information, articles, and sources "
                        "from across the internet. Writes research findings to files/research_notes/ "
                        "for later use by report writers. Ideal for complex research tasks "
                        "that require deep searching and cross-referencing."
                    ),
                    tools=["Write", "mcp__data-analyst-mcp__vanna_chat_once", 
                           "mcp__exa-search-mcp__get_code_context_exa",
                           "mcp__exa-search-mcp__web_search_exa"],
                    prompt=researcher_prompt,
                    model="sonnet",
                ),
                "data-analyst": AgentDefinition(
                    description=(
                        "Use this agent AFTER researchers have completed their work to generate quantitative "
                        "analysis and visualizations. The data-analyst reads research notes from files/research_notes/, "
                        "extracts numerical data (percentages, rankings, trends, comparisons), and, when required, "
                        "queries databases via the vanna_chat_once SQL tool to obtain missing or up-to-date figures. "
                        "The agent generates charts using Python/matplotlib via Bash, saves charts to files/charts/, "
                        "and writes a data summary to files/data/. If the vanna_chat_once service returns 'images' or "
                        "'links', the agent MUST download the corresponding files and store them locally for later "
                        "reference. Use this agent before the report-writer to add visual and data-driven insights."
                    ),
                    tools=["Glob", "Read", "Bash", "Write", "mcp__data-analyst-mcp__vanna_chat_once"],
                    prompt=data_analyst_prompt,
                    model="sonnet",
                ),
                "report-writer": AgentDefinition(
                    description=(
                        "Use this agent when you need to create a formal research report document. "
                        "The report-writer reads research findings from files/research_notes/, data analysis "
                        "from files/data/, and charts from files/charts/, then synthesizes them into clear, "
                        "concise, professionally formatted PDF reports in files/reports/ using reportlab. "
                        "Ideal for creating structured documents with proper citations, data, and embedded visuals. "
                        "Does NOT conduct web searches - only reads existing research notes and creates PDF reports."
                    ),
                    tools=["Skill", "Write", "Glob", "Read", "Bash"],
                    prompt=report_writer_prompt,
                    model="haiku",
                ),
            }

            hooks = {
                "PreToolUse": [
                    HookMatcher(
                        matcher=None,
                        hooks=[tracker.pre_tool_use_hook],
                    )
                ],
                "PostToolUse": [
                    HookMatcher(
                        matcher=None,
                        hooks=[tracker.post_tool_use_hook],
                    )
                ],
            }

            if ResearchAgentProcessor._options is None:
                options = ClaudeAgentOptions(
                    permission_mode="bypassPermissions",
                    cwd=workspace.as_posix(),
                    setting_sources=["project"],
                    system_prompt=lead_agent_prompt,
                    allowed_tools=["Task", "mcp__data-analyst-mcp__vanna_chat_once"],
                    agents=agents,
                    hooks=hooks,
                    model="haiku",
                )
            else:
                options = ResearchAgentProcessor._options

            client = await self._ensure_client(options)

            transcript_writer.write_to_file(f"\nYou: {topic}\n")

            await client.query(prompt=topic)

            transcript_writer.write("\nAgent: ", end="")

            async for msg in client.receive_response():
                if type(msg).__name__ == "AssistantMessage":
                    process_assistant_message(msg, tracker, transcript_writer)

            transcript_writer.write("\n")
            transcript_writer.write("\n\nGoodbye!\n")

            transcript_writer.close()
            tracker.close()

            tool_log_default = session_dir / "tool_calls.jsonl"
            if tool_log_default.exists():
                if tool_log_default.resolve() != log_detail_file.resolve():
                    if log_detail_file.exists():
                        log_detail_file.unlink()
                    tool_log_default.rename(log_detail_file)

            summary = {
                "topic": topic,
                "workspace": str(workspace),
                "reports_dir": str(workspace / code_input.userFilesDir / "reports"),
                "logs": {
                    "detail": code_input.logDetailPath,
                    "summary": code_input.logSummaryPath,
                    "run": code_input.logRunPath,
                },
                "assistant_summary": transcript_writer.buffer,
            }
            with log_summary_file.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)

            result_path = (log_summary_file.parent / "result.json").as_posix()
            Path(result_path).parent.mkdir(parents=True, exist_ok=True)

            result_payload = {
                "topic": topic,
                "workspace": str(workspace),
                "reports_dir": str(workspace / code_input.userFilesDir / "reports"),
                "logs": {
                    "detail": code_input.logDetailPath,
                    "summary": code_input.logSummaryPath,
                    "run": code_input.logRunPath,
                },
            }

            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result_payload, handle, ensure_ascii=False, indent=2)

            return result_path, code_input.logDetailPath, code_input.logSummaryPath, code_input.logRunPath

        finally:
            os.chdir(original_cwd)
