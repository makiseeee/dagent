from typing import Any

from personal_agent.core.tools.registry import ToolRegistry


class Executor:
    def __init__(self, tools: ToolRegistry):
        self.tools = tools

    def execute(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        try:
            tool = self.tools.get(tool_name)

            result = tool.run(tool_args)

            if tool.spec.side_effect in {"write", "external", "dangerous"}:
                if tool.spec.require_confirmation:
                    return {
                        "status": "needs_confirmation",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "result": result,
                        "reason": (
                            "This tool prepared a proposal with side effects. "
                            "User confirmation is required before applying it."
                        ),
                    }

            return {
                "status": "success",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result,
            }

        except Exception as exc:
            return {
                "status": "error",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }