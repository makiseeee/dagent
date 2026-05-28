import json

from personal_agent.core.llm.client import LLMClient
from personal_agent.core.runtime.plan import AgentPlan
from personal_agent.core.runtime.rule_planner import RulePlanner
from personal_agent.core.tools.registry import ToolRegistry


class Planner:
    def __init__(self, llm: LLMClient, tools: ToolRegistry):
        self.llm = llm
        self.tools = tools
        self.rule_planner = RulePlanner(tools=tools)

    def plan(self, user_input: str) -> AgentPlan:
        rule_plan = self.rule_planner.plan(user_input)
        if rule_plan is not None:
            return rule_plan

        return self._plan_with_llm(user_input)

    def _plan_with_llm(self, user_input: str) -> AgentPlan:
        tool_schemas = self.tools.schemas_for_llm()

        today = self.rule_planner._today().date()
        week_start, week_end = self.rule_planner._current_week_range()

        system_prompt = f"""
你是一个个人 Agent 的 Planner。

当前日期：{today.isoformat()}
本周范围：{week_start} 到 {week_end}

你的任务是判断用户请求是否需要调用工具。

可用工具如下：
{json.dumps(tool_schemas, ensure_ascii=False, indent=2)}

你必须只输出 JSON，不要输出 markdown，不要解释。

输出格式只能是两种之一：

1. 不需要工具，直接回答：
{{
  "kind": "final",
  "final_answer": "你的回答"
}}

2. 需要调用工具：
{{
  "kind": "tool_call",
  "tool_name": "工具名",
  "tool_args": {{
    "参数名": "参数值"
  }}
}}

规则：
- 如果用户问当前时间、今天日期、系统状态，优先调用 system.get_current_time。
- 如果用户问今天的安排、今天的任务、今天的日程，调用 schedule.get_today_overview，lookback_days 使用 7。
- 如果用户说安排今天的日程、规划今天事项，表示要把最近未完成的正式日程遗留接收到今天，调用 schedule.adopt_overdue_today，lookback_days 使用 7，llm_rewrite 使用 false。
- 如果用户问本周、这周、这一周、这个星期的任务或安排，调用 schedule.get_range_items。
- 本周查询的 start_date 使用 {week_start}，end_date 使用 {week_end}，lookback_days 使用 30。
- 如果用户要求整理 Thino、整理零散任务、查看 inbox、review 最近任务，调用 schedule.get_inbox_items，days 使用 7。
- 如果用户要求把今天 Thino、待整理事项、零散记录整理进日程，调用 schedule.organize_today，llm_rewrite 使用 true。
- 如果用户要求把 inbox 中今天该处理的事项安排进今天日程，调用 schedule.adopt_inbox_today，lookback_days 使用 7，llm_rewrite 使用 true。
- 如果用户要求新增一条今天任务，例如“添加今天任务：xxx”“今天加一个任务xxx”“记到今天日程：xxx”“帮我今天安排一下xxx”，调用 schedule.add_today_item，content 使用用户给出的任务文本，llm_rewrite 使用 true。
- 如果用户要求创建每周循环日程，调用 schedule.recurring_add。
- 如果用户要求取消循环日程，调用 schedule.recurring_cancel。
- 如果没有合适工具，就 kind=final，并说明目前还没有对应工具。
- 不要编造工具名。
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        raw = self.llm.chat(messages, temperature=0.0).strip()

        if raw.startswith("```"):
            raw = (
                raw.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Planner returned invalid JSON: {raw}") from exc

        plan = AgentPlan.model_validate(data)
        plan.source = "llm"
        plan.reason = "Planned by LLM."
        return plan
