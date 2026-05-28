from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentPlan(BaseModel):
    kind: Literal["final", "tool_call"]
    final_answer: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)

    source: str = "llm"
    reason: str | None = None