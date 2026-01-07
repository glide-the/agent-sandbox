import asyncio
import json
import logging
import os
import shutil
import subprocess
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
from sandbox.common.research_agent.utils.message_handler import (
    process_assistant_message,
)
from sandbox.common.research_agent import load_prompt
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    HookMatcher,
)

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

    def init_paths(
        self, code_input: ResearchAgentSandboxProcessorData, task_id: str
    ) -> dict:
        """
        利用现有 _init_workspace 逻辑，基于 code_input 初始化：
        - workspace 目录
        - 日志目录（logDetailPath / logSummaryPath / logRunPath）
        - result.json 路径
        - 初始化 log_summary_file 结构
        """
        workspace = self._init_workspace(code_input, task_id)

        log_detail_file = Path(code_input.logDetailPath)
        log_summary_file = Path(code_input.logSummaryPath)
        log_run_file = Path(code_input.logRunPath)

        result_path = (log_summary_file.parent / "result.json").as_posix()
        Path(result_path).parent.mkdir(parents=True, exist_ok=True)

        # 使用通用方法构建初始 summary 结构
        initial_summary = self._build_summary_structure(
            workspace=workspace, code_input=code_input, topic="", assistant_summary=""
        )

        # 写入初始结构到 log_summary_file
        with log_summary_file.open("w", encoding="utf-8") as handle:
            json.dump(initial_summary, handle, ensure_ascii=False, indent=2)

        return {
            "result_path": result_path,
            "log_detail_path": log_detail_file.as_posix(),
            "log_summary_path": log_summary_file.as_posix(),
            "log_run_path": log_run_file.as_posix(),
            "workspace": str(workspace),
        }

    async def __call__(
        self, code_input: ResearchAgentSandboxProcessorData, task_id: str, topic: str
    ):
        (
            result_path,
            log_detail_path,
            log_summary_path,
            log_run_path,
        ) = await self._run_research(
            code_input=code_input, task_id=task_id, topic=topic
        )
        return result_path, log_detail_path, log_summary_path, log_run_path

    async def _create_client(self, options: "ClaudeAgentOptions") -> "ClaudeSDKClient":
        """
        创建新的 Claude SDK 客户端实例（每个任务独立）

        Args:
            options: Claude SDK 客户端配置选项

        Returns:
            已连接的 Claude SDK 客户端实例
        """
        client = ClaudeSDKClient(options=options)
        logger.info(f"Creating new Claude SDK client with cwd: {options.cwd}")
        await client.__aenter__()
        logger.info("Claude SDK client created and connected successfully")
        return client

    def _resolve_prompt(self, default_filename: str, override_key: str) -> str:
        override_path = self.prompt_overrides.get(override_key)
        if override_path:
            prompt_path = Path(override_path)
            with prompt_path.open("r", encoding="utf-8") as handle:
                return handle.read().strip()

        return load_prompt(default_filename)

    def _build_directory_structure(self, workspace: Path, user_files_dir: str) -> dict:
        """
        构建目录结构元数据（通用方法）

        :param workspace: 工作区路径
        :param user_files_dir: 用户文件目录名
        :return: 目录结构字典
        """
        return {
            "files/research_notes/": {
                "path": str(workspace / user_files_dir / "research_notes"),
                "purpose": "输入源：存放待读取的 Markdown 研究笔记。",
                "type": "input",
            },
            "files/charts/": {
                "path": str(workspace / user_files_dir / "charts"),
                "purpose": "输出/存图：存放生成的 Python 图表及 SSE 下载的图片资源。",
                "type": "output",
            },
            "files/data/": {
                "path": str(workspace / user_files_dir / "data"),
                "purpose": "输出/存数：存放生成的 data_summary.md、下载的数据文件（CSV/XLSX等）。",
                "type": "output",
            },
            "files/assets/": {
                "path": str(workspace / user_files_dir / "assets"),
                "purpose": "备用存图：存放非图表类的通用图片或资源。",
                "type": "storage",
            },
            "files/reports/": {
                "path": str(workspace / user_files_dir / "reports"),
                "purpose": "输出/报告：存放生成的 PDF 研究报告。",
                "type": "output",
            },
        }

    def _build_summary_structure(
        self,
        workspace: Path,
        code_input: ResearchAgentSandboxProcessorData,
        topic: str = "",
        assistant_summary: str = "",
    ) -> dict:
        """
        构建 summary/result 结构（通用方法）

        :param workspace: 工作区路径
        :param code_input: 处理器数据输入
        :param topic: 研究主题（可选）
        :param assistant_summary: 助手摘要（可选）
        :return: 完整的摘要结构字典
        """
        directory_tree = self._generate_directory_tree(workspace)
        directory_structure = self._build_directory_structure(
            workspace, code_input.userFilesDir
        )

        summary = {
            "topic": topic,
            "workspace": str(workspace),
            "reports_dir": str(workspace / code_input.userFilesDir / "reports"),
            "logs": {
                "detail": code_input.logDetailPath,
                "summary": code_input.logSummaryPath,
                "run": code_input.logRunPath,
            },
            "environment": {
                "workspace": str(workspace),
                "user_id": code_input.userId,
                "user_files_dir": str(workspace / code_input.userFilesDir),
                "user_logs_dir": str(workspace / code_input.userLogsDir),
                "current_working_directory": str(Path.cwd()),
            },
            "directory_structure": directory_structure,
            "directory_tree": directory_tree,
        }

        if assistant_summary or topic == "":
            summary["assistant_summary"] = assistant_summary

        return summary

    def _generate_directory_tree(self, root_path: Path, max_depth: int = 3) -> dict:
        """
        Generate a hierarchical tree structure of the directory.

        :param root_path: The root directory to scan
        :param max_depth: Maximum depth to traverse (default: 3)
        :return: Dictionary representing the directory tree
        """

        def build_tree(path: Path, current_depth: int = 0) -> dict:
            if current_depth >= max_depth or not path.is_dir():
                return {
                    "name": path.name,
                    "type": "file" if path.is_file() else "directory",
                }

            tree = {"name": path.name, "type": "directory", "children": []}

            try:
                # Sort entries: directories first, then files
                entries = sorted(
                    path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
                )

                for entry in entries:
                    # Skip hidden files/directories (except .claude and .mcp.json)
                    if entry.name.startswith(".") and entry.name not in [
                        ".claude",
                        ".mcp.json",
                    ]:
                        continue

                    if entry.is_dir():
                        tree["children"].append(build_tree(entry, current_depth + 1))
                    else:
                        # Only include files, not their contents
                        tree["children"].append(
                            {
                                "name": entry.name,
                                "type": "file",
                                "size": entry.stat().st_size if entry.exists() else 0,
                            }
                        )
            except PermissionError:
                tree["error"] = "Permission denied"
            except Exception as e:
                tree["error"] = str(e)

            return tree

        return build_tree(root_path)

    def _process_research_notes_with_repomix(
        self,
        session_dir: Path,
        transcript_writer: SandboxTranscriptWriter,
        workspace: Path,
    ):
        research_notes_dir = session_dir / "files" / "research_notes"
        if not research_notes_dir.exists():
            return

        files = (
            list(research_notes_dir.iterdir()) if research_notes_dir.is_dir() else []
        )
        if not files:
            return

        transcript_writer.write_to_file("\n\n=== Research Notes Files ===\n")
        large_files = []
        for file in sorted(files):
            if file.is_file():
                size = file.stat().st_size
                transcript_writer.write_to_file(f"- {file.name} ({size} bytes)\n")
                if size > 1048576:
                    large_files.append(file.name)

        if large_files:
            transcript_writer.write_to_file(
                f"\nNote: The following files exceed 1MB and will be skipped by Repomix:\n"
            )
            for filename in large_files:
                transcript_writer.write_to_file(f"  - {filename}\n")

        try:
            transcript_writer.write_to_file("\n=== Running Repomix ===\n")

            config_path = workspace / ".repomix-tmp.json"
            config_content = {
                "input": {"maxFileSize": 1048576},
                "ignore": {
                    "customPatterns": [
                        "**/*.jpg",
                        "**/*.jpeg",
                        "**/*.png",
                        "**/*.gif",
                        "**/*.bmp",
                        "**/*.svg",
                        "**/*.ico",
                        "**/*.webp",
                    ]
                },
            }
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config_content, f)

            repomix_cmd = [
                "npx",
                "repomix@latest",
                "--config",
                str(config_path),
                "--style",
                "plain",
                str(research_notes_dir),
            ]

            result = subprocess.run(
                repomix_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if config_path.exists():
                config_path.unlink()

            if result.stdout:
                transcript_writer.write_to_file(result.stdout)
            if result.stderr:
                transcript_writer.write_to_file(f"Errors:\n{result.stderr}\n")

        except subprocess.TimeoutExpired:
            transcript_writer.write_to_file("Repomix command timed out.\n")
        except Exception as e:
            transcript_writer.write_to_file(f"Error running repomix: {e}\n")

    def _init_workspace(
        self, code_input: ResearchAgentSandboxProcessorData, task_id: str
    ) -> Path:
        cwd = Path(self.cwd)

        if code_input.workspace:
            workspace = Path(code_input.workspace)
            if not workspace.is_absolute():
                workspace = cwd / workspace / task_id
        else:
            workspace = cwd / "workspace" / task_id

        workspace.mkdir(parents=True, exist_ok=True)

        user_files_dir = workspace / code_input.userFilesDir
        user_files_dir.mkdir(parents=True, exist_ok=True)

        user_logs_dir = workspace / code_input.userLogsDir
        user_logs_dir.mkdir(parents=True, exist_ok=True)

        code_input.logDetailPath = (workspace / code_input.logDetailPath).as_posix()
        code_input.logSummaryPath = (workspace / code_input.logSummaryPath).as_posix()
        code_input.logRunPath = (workspace / code_input.logRunPath).as_posix()

        import sandbox.common.research_agent as research_agent

        project_root = Path(self.cwd)
        claude_src = project_root / ".claude"
        mcp_src = project_root / ".mcp.json"

        claude_dst = workspace / ".claude"
        mcp_dst = workspace / ".mcp.json"

        if claude_src.exists() and not claude_dst.exists():
            shutil.copytree(claude_src, claude_dst)
        if mcp_src.exists() and not mcp_dst.exists():
            shutil.copy(mcp_src, mcp_dst)

        return workspace

    async def _run_research_bak(
        self, code_input: ResearchAgentSandboxProcessorData, task_id: str, topic: str
    ):
        workspace = self._init_workspace(code_input, task_id)

        original_cwd = Path.cwd()
        os.chdir(workspace)

        log_detail_file = Path(code_input.logDetailPath)
        log_summary_file = Path(code_input.logSummaryPath)
        log_run_file = Path(code_input.logRunPath)

        client = None
        try:
            transcript_writer = SandboxTranscriptWriter(log_run_file)

            session_dir = log_detail_file.parent
            session_dir.mkdir(parents=True, exist_ok=True)
            tracker = SubagentTracker(
                transcript_writer=transcript_writer, session_dir=session_dir
            )

            lead_agent_prompt = self._resolve_prompt("lead_agent_qa.txt", "lead_agent")
            researcher_prompt = self._resolve_prompt(
                "researcher_SAAD-SOP.txt", "researcher"
            )
            data_analyst_prompt = self._resolve_prompt(
                "data_analyst.txt", "data_analyst"
            )
            report_writer_prompt = self._resolve_prompt(
                "report_writer.txt", "report_writer"
            )

            agents = {
                "researcher": AgentDefinition(
                    description=(
                        "Use this agent when you need to gather research information on any topic. "
                        "The researcher uses web search to find relevant information, articles, and sources "
                        "from across the internet. Writes research findings to files/research_notes/ "
                        "for later use by report writers. Ideal for complex research tasks "
                        "that require deep searching and cross-referencing."
                    ),
                    tools=[
                        "Write",
                        "mcp__data-analyst-mcp__vanna_chat_once",
                        "mcp__exa-search-mcp__get_code_context_exa",
                        "mcp__exa-search-mcp__web_search_exa",
                    ],
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
                    tools=[
                        "Glob",
                        "Read",
                        "Bash",
                        "Write",
                        "mcp__data-analyst-mcp__vanna_chat_once",
                    ],
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
                    model="sonnet",
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

            options = ClaudeAgentOptions(
                permission_mode="bypassPermissions",
                cwd=workspace.as_posix(),
                setting_sources=["project"],
                system_prompt=lead_agent_prompt,
                allowed_tools=["Task", "mcp__data-analyst-mcp__vanna_chat_once"],
                agents=agents,
                hooks=hooks,
                model="sonnet",
            )

            client = await self._create_client(options)

            transcript_writer.write_to_file(f"\nYou: {topic}\n")

            await client.query(prompt=topic)

            transcript_writer.write("\nAgent: ", end="")

            message_count = 0
            async for msg in client.receive_response():
                if type(msg).__name__ == "AssistantMessage":
                    process_assistant_message(msg, tracker, transcript_writer)

                    # Update directory_tree dynamically every 10 messages
                    message_count += 1
                    if message_count % 10 == 0:
                        intermediate_summary = self._build_summary_structure(
                            workspace=workspace,
                            code_input=code_input,
                            topic=topic,
                            assistant_summary=transcript_writer.buffer,
                        )
                        with log_summary_file.open("w", encoding="utf-8") as handle:
                            json.dump(
                                intermediate_summary,
                                handle,
                                ensure_ascii=False,
                                indent=2,
                            )

            self._process_research_notes_with_repomix(
                session_dir, transcript_writer, workspace
            )

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

            # 使用通用方法构建 summary 结构
            summary = self._build_summary_structure(
                workspace=workspace,
                code_input=code_input,
                topic=topic,
                assistant_summary=transcript_writer.buffer,
            )

            with log_summary_file.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)

            result_path = (log_summary_file.parent / "result.json").as_posix()
            Path(result_path).parent.mkdir(parents=True, exist_ok=True)

            # result_payload uses the same structure as summary (without assistant_summary)
            result_payload = {
                k: v for k, v in summary.items() if k != "assistant_summary"
            }

            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result_payload, handle, ensure_ascii=False, indent=2)

            return (
                result_path,
                code_input.logDetailPath,
                code_input.logSummaryPath,
                code_input.logRunPath,
            )

        finally:
            os.chdir(original_cwd)
            logger.info("Restored original working directory")
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                    logger.info("Claude SDK client closed successfully")
                except Exception as e:
                    logger.error(f"Error closing Claude SDK client: {e}", exc_info=e)

    async def _run_research(
        self, code_input: ResearchAgentSandboxProcessorData, task_id: str, topic: str
    ):
        workspace = self._init_workspace(code_input, task_id)

        original_cwd = Path.cwd()
        os.chdir(workspace)

        log_detail_file = Path(code_input.logDetailPath)
        log_summary_file = Path(code_input.logSummaryPath)
        log_run_file = Path(code_input.logRunPath)

        client = None
        try:
            transcript_writer = SandboxTranscriptWriter(log_run_file)

            session_dir = log_detail_file.parent
            session_dir.mkdir(parents=True, exist_ok=True)
            tracker = SubagentTracker(
                transcript_writer=transcript_writer, session_dir=session_dir
            )

            lead_agent_prompt = self._resolve_prompt("lead_agent_qa.txt", "lead_agent")
            researcher_prompt = self._resolve_prompt(
                "researcher_SAAD-SOP.txt", "researcher"
            )
            data_analyst_prompt = self._resolve_prompt(
                "data_analyst.txt", "data_analyst"
            )
            report_writer_prompt = self._resolve_prompt(
                "report_writer.txt", "report_writer"
            )

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

            options = ClaudeAgentOptions(
                permission_mode="bypassPermissions",
                cwd=workspace.as_posix(),
                setting_sources=["project"],
                system_prompt=researcher_prompt,
                allowed_tools=[
                    "Task",
                    "mcp__data-analyst-mcp__vanna_chat_once",
                    "mcp__exa-search-mcp__get_code_context_exa",
                    "mcp__exa-search-mcp__web_search_exa",
                ],
                tools=[
                    "Write",
                    "mcp__data-analyst-mcp__vanna_chat_once",
                    "mcp__exa-search-mcp__get_code_context_exa",
                    "mcp__exa-search-mcp__web_search_exa",
                ],
                hooks=hooks,
                model="sonnet",
            )

            client = await self._create_client(options)

            transcript_writer.write_to_file(f"\nYou: {topic}\n")

            await client.query(prompt=topic)

            transcript_writer.write("\nAgent: ", end="")

            message_count = 0
            async for msg in client.receive_response():
                if type(msg).__name__ == "AssistantMessage":
                    process_assistant_message(msg, tracker, transcript_writer)

                    # Update directory_tree dynamically every 10 messages
                    message_count += 1
                    if message_count % 10 == 0:
                        intermediate_summary = self._build_summary_structure(
                            workspace=workspace,
                            code_input=code_input,
                            topic=topic,
                            assistant_summary=transcript_writer.buffer,
                        )
                        with log_summary_file.open("w", encoding="utf-8") as handle:
                            json.dump(
                                intermediate_summary,
                                handle,
                                ensure_ascii=False,
                                indent=2,
                            )

            self._process_research_notes_with_repomix(
                session_dir, transcript_writer, workspace
            )

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

            # 使用通用方法构建 summary 结构
            summary = self._build_summary_structure(
                workspace=workspace,
                code_input=code_input,
                topic=topic,
                assistant_summary=transcript_writer.buffer,
            )

            with log_summary_file.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)

            result_path = (log_summary_file.parent / "result.json").as_posix()
            Path(result_path).parent.mkdir(parents=True, exist_ok=True)

            # result_payload uses the same structure as summary (without assistant_summary)
            result_payload = {
                k: v for k, v in summary.items() if k != "assistant_summary"
            }

            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result_payload, handle, ensure_ascii=False, indent=2)

            return (
                result_path,
                code_input.logDetailPath,
                code_input.logSummaryPath,
                code_input.logRunPath,
            )

        finally:
            os.chdir(original_cwd)
            logger.info("Restored original working directory")
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                    logger.info("Claude SDK client closed successfully")
                except Exception as e:
                    logger.error(f"Error closing Claude SDK client: {e}", exc_info=e)
