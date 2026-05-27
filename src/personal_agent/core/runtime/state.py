from pydantic import BaseModel, Field
from typing import Any


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None


class AgentState(BaseModel):
    user_input: str
    messages: list[dict[str, str]] = Field(default_factory=list)

    # debug / trace
    planner_output: dict[str, Any] | None = None
    plan: list[str] = Field(default_factory=list)

    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirmation: dict[str, Any] | None = None
    final_answer: str | None = None