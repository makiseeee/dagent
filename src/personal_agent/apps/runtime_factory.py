from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.runtime.runtime import AgentRuntime
from personal_agent.core.tools.registry import ToolRegistry
from personal_agent.plugins.system.tools import get_tools as get_system_tools
from personal_agent.plugins.schedule.tools import get_tools as get_schedule_tools


def build_runtime(config: AppConfig) -> tuple[AgentRuntime, LLMClient]:
    llm = LLMClient(config.llm)

    tools = ToolRegistry()

    for tool in get_system_tools():
        tools.register(tool)

    for tool in get_schedule_tools(config):
        tools.register(tool)

    runtime = AgentRuntime(llm=llm, tools=tools)

    return runtime, llm