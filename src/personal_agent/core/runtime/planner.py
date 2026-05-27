import json
import re
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from personal_agent.core.llm.client import LLMClient
from personal_agent.core.tools.registry import ToolRegistry


class AgentPlan(BaseModel):
    kind: Literal["final", "tool_call"]
    final_answer: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)

    # debug fields
    source: str = "llm"
    reason: str | None = None


class Planner:
    def __init__(self, llm: LLMClient, tools: ToolRegistry):
        self.llm = llm
        self.tools = tools

    def _today(self) -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _tool_exists(self, name: str) -> bool:
        try:
            self.tools.get(name)
            return True
        except KeyError:
            return False

    def _current_week_range(self) -> tuple[str, str]:
        today = self._today().date()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()

    def _maybe_rule_plan(self, user_input: str) -> AgentPlan | None:
        """
        High-confidence deterministic routing.

        These should not rely on LLM planning, because date-range tool choice
        needs to be stable.
        """
        text = user_input.strip()

        # 完成 xxx / 做完 xxx / 标记完成 xxx
        if re.search(r"(完成|做完|搞定|标记完成)", text):
            target = text

            target = re.sub(r"^(完成|做完|搞定)\s*", "", target).strip()
            target = re.sub(r"^把\s*", "", target).strip()
            target = re.sub(r"\s*标记为?完成$", "", target).strip()
            target = re.sub(r"\s*(完成|做完)$", "", target).strip()

            if target and self._tool_exists("schedule.mark_done"):
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.mark_done",
                    tool_args={
                        "target_text": target,
                        "days": 7,
                    },
                    source="rule",
                    reason="Matched mark-done query.",
                )

        schedule_words = re.search(
            r"(安排|日程|任务|待办|todo|事项|计划|提醒)",
            text,
            re.IGNORECASE,
        )

        if not schedule_words:
            return None
                # 把 inbox 中到今天该处理的事项安排进今天日程
        if re.search(r"(inbox|待整理|今天该做|今天可安排|该处理)", text, re.IGNORECASE):
            if re.search(r"(安排|整理|写入|加入|放到|放进|并入)", text):
                if re.search(r"(今天|今日|日程|计划)", text):
                    if self._tool_exists("schedule.adopt_inbox_today"):
                        return AgentPlan(
                            kind="tool_call",
                            tool_name="schedule.adopt_inbox_today",
                            tool_args={
                                "lookback_days": 7,
                                "llm_rewrite": True,
                            },
                            source="rule",
                            reason="Matched adopt due inbox items into today's schedule.",
                        )    
        # 整理进日程 / 写入日程
        if re.search(r"(整理|收拢|归类|写入|加入|放到|放进)", text):
            if re.search(r"(日程|计划)", text):
                if re.search(r"(今天|今日|Thino|thino|待整理|零散)", text):
                    if self._tool_exists("schedule.organize_today"):
                        return AgentPlan(
                            kind="tool_call",
                            tool_name="schedule.organize_today",
                            tool_args={"llm_rewrite": True},
                            source="rule",
                            reason="Matched organize today's Thino inbox into schedule.",
                        )
                    
         # 整理 Thino / 零散任务 / inbox / review
        if re.search(r"(整理|归类|review|inbox|零散|收拢|梳理)", text, re.IGNORECASE):
            if re.search(r"(Thino|thino|任务|待办|事项|日程|记录)", text, re.IGNORECASE):
                if self._tool_exists("schedule.get_inbox_items"):
                    days = 1 if re.search(r"(今天|今日)", text) else 7

                    return AgentPlan(
                        kind="tool_call",
                        tool_name="schedule.get_inbox_items",
                        tool_args={"days": days},
                        source="rule",
                        reason=(
                            "Matched today's Thino inbox query."
                            if days == 1
                            else "Matched schedule inbox/review query."
                        ),
                    )
                        
        # 本周 / 这周 / 这一周 / 本星期 / 这个星期
        if re.search(r"(这周|本周|这一周|这星期|本星期|这个星期|本礼拜|这礼拜)", text):
            if self._tool_exists("schedule.get_range_items"):
                start_date, end_date = self._current_week_range()
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.get_range_items",
                    tool_args={
                        "start_date": start_date,
                        "end_date": end_date,
                        "lookback_days": 30,
                    },
                    source="rule",
                    reason="Matched weekly schedule query.",
                )
        # 把遗留事项 / 昨天没完成的事项接收到今天
        if re.search(r"(遗留|没完成|未完成|昨天|之前)", text):
            if re.search(r"(放到今天|放进今天|整理到今天|整理进今天|并入今天|接收到今天|今天.*日程)", text):
                if self._tool_exists("schedule.adopt_overdue_today"):
                    return AgentPlan(
                        kind="tool_call",
                        tool_name="schedule.adopt_overdue_today",
                        tool_args={
                            "lookback_days": 7,
                            "llm_rewrite": False,
                        },
                        source="rule",
                        reason="Matched adopt overdue items into today's schedule.",
                    )
        # 今天
        if re.search(r"(今天|今日)", text):
            if self._tool_exists("schedule.get_today_overview"):
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.get_today_overview",
                    tool_args={"lookback_days": 7},
                    source="rule",
                    reason="Matched today's overview query.",
                )

            if self._tool_exists("schedule.get_daily_items"):
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.get_daily_items",
                    tool_args={"date": "today"},
                    source="rule",
                    reason="Matched today's schedule query.",
                )

        # 明天
        if "明天" in text:
            if self._tool_exists("schedule.get_daily_items"):
                tomorrow = (self._today().date() + timedelta(days=1)).isoformat()
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.get_daily_items",
                    tool_args={"date": tomorrow},
                    source="rule",
                    reason="Matched tomorrow's schedule query.",
                )

        # 后天
        if "后天" in text:
            if self._tool_exists("schedule.get_daily_items"):
                day_after_tomorrow = (
                    self._today().date() + timedelta(days=2)
                ).isoformat()
                return AgentPlan(
                    kind="tool_call",
                    tool_name="schedule.get_daily_items",
                    tool_args={"date": day_after_tomorrow},
                    source="rule",
                    reason="Matched day-after-tomorrow schedule query.",
                )
        return None

    def plan(self, user_input: str) -> AgentPlan:
        rule_plan = self._maybe_rule_plan(user_input)
        if rule_plan is not None:
            return rule_plan

        tool_schemas = self.tools.schemas_for_llm()

        today = self._today().date()
        week_start, week_end = self._current_week_range()

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
- 如果用户问今天的安排、今天的任务、今天的日程，调用 schedule.get_daily_items，date 使用 "today"。
- 如果用户问本周、这周、这一周、这个星期的任务或安排，调用 schedule.get_range_items。
- 本周查询的 start_date 使用 {week_start}，end_date 使用 {week_end}，lookback_days 使用 30。
- 如果没有合适工具，就 kind=final，并说明目前还没有对应工具。
- 不要编造工具名。
- 如果用户要求整理 Thino、整理零散任务、查看 inbox、review 最近任务，调用 schedule.get_inbox_items，days 使用 7。
- 如果用户要求把今天 Thino、待整理事项、零散记录整理进日程，调用 schedule.organize_today，llm_rewrite 使用 true。
"""

        messages = [
            {"role": "system", "content": system_prompt.strip()},
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