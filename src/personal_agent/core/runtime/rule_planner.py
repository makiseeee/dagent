import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from personal_agent.core.runtime.plan import AgentPlan
from personal_agent.core.tools.registry import ToolRegistry


ZH_WEEKDAY_TO_CODE = {
    "一": "MO",
    "二": "TU",
    "三": "WE",
    "四": "TH",
    "五": "FR",
    "六": "SA",
    "日": "SU",
    "天": "SU",
}


class RulePlanner:
    """
    High-confidence deterministic routing.

    Keep rules here small and explicit.
    Anything fuzzy or semantic should fall back to LLM planner.
    """

    def __init__(self, tools: ToolRegistry):
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

    def plan(self, user_input: str) -> AgentPlan | None:
        text = user_input.strip()

        for rule in [
            self._plan_mark_done,
            self._plan_recurring_cancel,
            self._plan_recurring_add,
            self._plan_adopt_inbox_today,
            self._plan_organize_today,
            self._plan_inbox_review,
            self._plan_week,
            self._plan_adopt_overdue_today,
            self._plan_today,
            self._plan_tomorrow,
            self._plan_day_after_tomorrow,
        ]:
            plan = rule(text)
            if plan is not None:
                return plan

        return None

    def _plan_mark_done(self, text: str) -> AgentPlan | None:
        if not re.search(r"(完成|做完|搞定|标记完成)", text):
            return None

        target = text
        target = re.sub(r"^(完成|做完|搞定)\s*", "", target).strip()
        target = re.sub(r"^把\s*", "", target).strip()
        target = re.sub(r"\s*标记为?完成$", "", target).strip()
        target = re.sub(r"\s*(完成|做完)$", "", target).strip()

        if not target or not self._tool_exists("schedule.mark_done"):
            return None

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

    def _extract_weekly_recurring(self, text: str) -> dict | None:
        """
        Parse simple weekly recurring schedule requests.

        Example:
        以后每周三晚上提醒我去跑步
        -> title=跑步, weekdays=["WE"], time=20:00, reminder=30
        """
        weekday_match = re.search(
            r"(?:每周|每星期|每礼拜|周|星期|礼拜)\s*([一二三四五六日天])",
            text,
        )
        if not weekday_match:
            return None

        weekday_zh = weekday_match.group(1)
        weekday = ZH_WEEKDAY_TO_CODE[weekday_zh]

        rest = text[weekday_match.end():].strip()

        time_value = None
        if re.search(r"(晚上|晚)", rest):
            time_value = "20:00"
        elif re.search(r"(早上|上午)", rest):
            time_value = "08:00"
        elif "下午" in rest:
            time_value = "14:00"

        title = rest
        title = re.sub(r"^(早上|上午|中午|下午|晚上|晚间|晚)\s*", "", title)
        title = re.sub(r"^(提醒我|提醒|记得)\s*", "", title)
        title = re.sub(r"^(去|做)\s*", "", title)
        title = title.strip(" ，,。.!！?？")

        if not title:
            title = "未命名循环日程"

        return {
            "title": title,
            "weekdays": [weekday],
            "time": time_value,
            "reminder_minutes": 30 if re.search(r"(提醒|记得)", text) else None,
            "duration_minutes": 60,
        }

    def _plan_recurring_add(self, text: str) -> AgentPlan | None:
        if re.search(r"(取消|不用|不再|停止)", text):
            return None

        if not re.search(r"(以后|之后|每周|每星期|每礼拜|每个)", text):
            return None
        recurring_args = self._extract_weekly_recurring(text)

        if not recurring_args or not self._tool_exists("schedule.recurring_add"):
            return None

        return AgentPlan(
            kind="tool_call",
            tool_name="schedule.recurring_add",
            tool_args=recurring_args,
            source="rule",
            reason="Matched recurring weekly schedule creation.",
        )

    def _plan_recurring_cancel(self, text: str) -> AgentPlan | None:
        if not re.search(r"(取消|不用|不再|停止)", text):
            return None

        if not re.search(r"(每周|每星期|每礼拜|循环|固定|提醒)", text):
            return None

        if not self._tool_exists("schedule.recurring_cancel"):
            return None

        query = text
        query = re.sub(r"^(取消|不用|不再|停止)\s*", "", query).strip()
        query = re.sub(r"(每周|每星期|每礼拜)\s*[一二三四五六日天]?", "", query).strip()
        query = re.sub(r"(提醒我|提醒|去|做)", "", query).strip()
        query = query.strip(" ，,。.!！?？")

        if not query:
            query = None

        return AgentPlan(
            kind="tool_call",
            tool_name="schedule.recurring_cancel",
            tool_args={
                "rule_id": None,
                "query": query,
            },
            source="rule",
            reason="Matched recurring schedule cancellation.",
        )

    def _plan_adopt_inbox_today(self, text: str) -> AgentPlan | None:
        if not re.search(r"(inbox|待整理|今天该做|今天可安排|该处理)", text, re.IGNORECASE):
            return None

        if not re.search(r"(安排|整理|写入|加入|放到|放进|并入)", text):
            return None

        if not re.search(r"(今天|今日|日程|计划)", text):
            return None

        if not self._tool_exists("schedule.adopt_inbox_today"):
            return None

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

    def _plan_organize_today(self, text: str) -> AgentPlan | None:
        if not re.search(r"(整理|收拢|归类|写入|加入|放到|放进)", text):
            return None

        if not re.search(r"(日程|计划)", text):
            return None

        if not re.search(r"(今天|今日|Thino|thino|待整理|零散)", text):
            return None

        if not self._tool_exists("schedule.organize_today"):
            return None

        return AgentPlan(
            kind="tool_call",
            tool_name="schedule.organize_today",
            tool_args={"llm_rewrite": True},
            source="rule",
            reason="Matched organize today's Thino inbox into schedule.",
        )

    def _plan_inbox_review(self, text: str) -> AgentPlan | None:
        if not re.search(r"(整理|归类|review|inbox|零散|收拢|梳理)", text, re.IGNORECASE):
            return None

        if not re.search(r"(Thino|thino|任务|待办|事项|日程|记录)", text, re.IGNORECASE):
            return None

        if not self._tool_exists("schedule.get_inbox_items"):
            return None

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

    def _plan_week(self, text: str) -> AgentPlan | None:
        if not re.search(r"(这周|本周|这一周|这星期|本星期|这个星期|本礼拜|这礼拜)", text):
            return None

        if not self._tool_exists("schedule.get_range_items"):
            return None

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

    def _plan_adopt_overdue_today(self, text: str) -> AgentPlan | None:
        if not re.search(r"(遗留|没完成|未完成|昨天|之前)", text):
            return None

        if not re.search(r"(放到今天|放进今天|整理到今天|整理进今天|并入今天|接收到今天|今天.*日程)", text):
            return None

        if not self._tool_exists("schedule.adopt_overdue_today"):
            return None

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

    def _plan_today(self, text: str) -> AgentPlan | None:
        if not re.search(r"(今天|今日)", text):
            return None

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

        return None

    def _plan_tomorrow(self, text: str) -> AgentPlan | None:
        if "明天" not in text:
            return None

        if not self._tool_exists("schedule.get_daily_items"):
            return None

        tomorrow = (self._today().date() + timedelta(days=1)).isoformat()

        return AgentPlan(
            kind="tool_call",
            tool_name="schedule.get_daily_items",
            tool_args={"date": tomorrow},
            source="rule",
            reason="Matched tomorrow's schedule query.",
        )

    def _plan_day_after_tomorrow(self, text: str) -> AgentPlan | None:
        if "后天" not in text:
            return None

        if not self._tool_exists("schedule.get_daily_items"):
            return None

        day_after_tomorrow = (self._today().date() + timedelta(days=2)).isoformat()

        return AgentPlan(
            kind="tool_call",
            tool_name="schedule.get_daily_items",
            tool_args={"date": day_after_tomorrow},
            source="rule",
            reason="Matched day-after-tomorrow schedule query.",
        )