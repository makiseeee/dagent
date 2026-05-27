from typing import Callable, Literal, Any
from pydantic import BaseModel


SideEffect = Literal["none", "read", "write", "external", "dangerous"]


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: type[BaseModel]
    side_effect: SideEffect = "none"
    require_confirmation: bool = False

    model_config = {
        "arbitrary_types_allowed": True
    }


class Tool:
    def __init__(self, spec: ToolSpec, func: Callable[[BaseModel], Any]):
        self.spec = spec
        self.func = func

    def run(self, raw_args: dict[str, Any]) -> Any:
        args = self.spec.input_schema.model_validate(raw_args)
        return self.func(args)

    def schema_for_llm(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "side_effect": self.spec.side_effect,
            "require_confirmation": self.spec.require_confirmation,
            "input_schema": self.spec.input_schema.model_json_schema(),
        }