import json
from collections.abc import Iterator

from personal_agent.core.llm.client import LLMClient
from personal_agent.core.runtime.state import AgentState, ToolCallRecord
from personal_agent.core.runtime.planner import Planner
from personal_agent.core.runtime.executor import Executor
from personal_agent.core.tools.registry import ToolRegistry


FINAL_SYSTEM_PROMPT = """
你是一个个人 Agent。
你刚刚调用了一个工具。
请根据用户请求和工具返回结果，给出自然、简洁、准确的最终回答。

重要规则：
- created_time 表示 Thino 记录创建时间，只能作为内部参考，不要展示给用户。
- 只有字段 time 才表示明确日程时间。
- effective_date 表示事项实际归属日期。
- date 表示事项所在 daily note 的日期，不等于任务归属日期。
- 没有明确日期的事项默认属于所在 note 的日期。
- 如果内容里有“明天、27号、周三、下周一”等显式日期，必须按 effective_date 归类。

today_overview 规则：
- today_schedule_items 是今天 ## 日程 中已有的正式日程。
- overdue_schedule_items 是过去 ## 日程 中未完成、且尚未并入今天日程的遗留事项。
- inbox_due_items 是 Thino inbox 中 effective_date <= 今天、尚未整理进日程的待安排事项。
- inbox_future_items 是 Thino inbox 中属于未来日期的待安排事项。
- inbox_unplanned_items 是 Thino inbox 中没有明确日期但可行动的事项。
- 回答今天总览时，必须分清“正式日程”“遗留未完成”“Inbox 中今天可安排”。
- 过期正式日程不属于 inbox，不要说它们来自 Thino。
- inbox 事项还不是正式日程，不要说已经安排，除非用户确认写入。

inbox 规则：
- 如果工具结果 mode 是 inbox，说明这是从最近 Thino 中提取的零散待整理事项。
- Thino 是 capture 区，里面的 memo 不等于正式任务。
- 对 inbox 结果，不要把所有事项都称为“任务”，优先称为“待整理事项”或“候选事项”。
- item_type 表示原始形态；suggested_type 表示整理进日程时建议写成什么。
- 只有写入 ## 日程 后，才称为正式日程任务。
- 对 inbox 结果，必须严格按照工具返回的 groups / bucket 分组回答。
- groups.today 只能说成“今日待整理事项”。
- groups.future 必须说成“未来待整理事项”，不能放进“今日任务”。

其他规则：
- 当用户问“这周/本周还有什么任务”时，按 effective_date 分组总结本周未完成任务。
- 不要说 inbox 事项已经写入 ## 日程；它们只是待整理候选项。
- 不要主动展开 filtered_out 的未来事项。
""".strip()


DIRECT_SYSTEM_PROMPT = """
你是一个运行在用户本地 WSL 环境中的个人 Agent。
请清楚、直接、简洁地回答用户的问题。
如果用户请求需要外部动作，但当前没有对应工具，请说明目前还不能执行。
""".strip()


class AgentRuntime:
    def __init__(self, llm: LLMClient, tools: ToolRegistry | None = None):
        self.llm = llm
        self.tools = tools or ToolRegistry()
        self.planner = Planner(llm=self.llm, tools=self.tools)
        self.executor = Executor(tools=self.tools)

    def _build_tool_final_messages(
        self,
        user_input: str,
        observation: dict,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": FINAL_SYSTEM_PROMPT,
            },
            {"role": "user", "content": user_input},
            {
                "role": "assistant",
                "content": f"工具返回结果：{json.dumps(observation, ensure_ascii=False)}",
            },
        ]

    def _build_direct_messages(self, user_input: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": DIRECT_SYSTEM_PROMPT,
            },
            {"role": "user", "content": user_input},
        ]

    def prepare(self, user_input: str) -> AgentState:
        """
        Prepare one agent run.

        This method does planning and tool execution only.
        It does not force a final LLM answer if a confirmation is needed.
        CLI / GUI can inspect AgentState.pending_confirmation and decide what to do.
        """
        state = AgentState(user_input=user_input)

        plan = self.planner.plan(user_input)

        state.planner_output = plan.model_dump()
        state.plan.append(
            f"{plan.kind}: {plan.tool_name or plan.final_answer or ''}"
        )

        if plan.kind == "final":
            if plan.final_answer:
                state.final_answer = plan.final_answer
                return state

            state.messages = self._build_direct_messages(user_input)
            return state

        if plan.kind == "tool_call":
            if not plan.tool_name:
                state.final_answer = "Planner 没有返回工具名。"
                return state

            observation = self.executor.execute(
                tool_name=plan.tool_name,
                tool_args=plan.tool_args,
            )

            state.tool_calls.append(
                ToolCallRecord(
                    tool_name=plan.tool_name,
                    arguments=plan.tool_args,
                    result=observation,
                )
            )
            state.observations.append(observation)

            if observation.get("status") == "needs_confirmation":
                state.pending_confirmation = observation
                state.final_answer = "这个操作需要确认。"
                return state

            if observation.get("status") == "error":
                state.final_answer = (
                    f"工具调用失败：{observation.get('error_type')}: "
                    f"{observation.get('error')}"
                )
                return state

            state.messages = self._build_tool_final_messages(
                user_input=user_input,
                observation=observation,
            )
            return state

        state.final_answer = "未知计划类型。"
        return state

    def run(self, user_input: str) -> AgentState:
        """
        Non-streaming execution.
        """
        state = self.prepare(user_input)

        if state.pending_confirmation:
            return state

        if state.final_answer:
            return state

        if state.messages:
            state.final_answer = self.llm.chat(state.messages, temperature=0.2)
            return state

        state.final_answer = "没有可用回复。"
        return state

    def stream(self, user_input: str) -> Iterator[str]:
        """
        Streaming execution.
        """
        state = self.prepare(user_input)

        if state.pending_confirmation:
            yield state.final_answer or "这个操作需要确认。"
            return

        if state.final_answer:
            yield state.final_answer
            return

        if state.messages:
            for chunk in self.llm.chat_stream(state.messages, temperature=0.2):
                yield chunk
            return

        yield "没有可用回复。"