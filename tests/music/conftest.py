"""Keep music unit tests independent of the unrelated research-agent runtime."""

import importlib.util
import sys
import types

if importlib.util.find_spec("claude_agent_sdk") is None:
    module = types.ModuleType("claude_agent_sdk")

    class _UnusedResearchSDK:
        pass

    for name in (
        "ClaudeSDKClient",
        "ClaudeAgentOptions",
        "AgentDefinition",
        "HookMatcher",
    ):
        setattr(module, name, _UnusedResearchSDK)
    sys.modules["claude_agent_sdk"] = module
