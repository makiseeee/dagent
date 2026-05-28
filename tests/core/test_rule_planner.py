from personal_agent.core.runtime.rule_planner import RulePlanner


class DummyToolRegistry:
    def __init__(self, names: set[str]):
        self.names = names

    def get(self, name: str):
        if name not in self.names:
            raise KeyError(name)
        return object()


def make_planner() -> RulePlanner:
    return RulePlanner(
        tools=DummyToolRegistry(
            {
                "schedule.mark_done",
                "schedule.recurring_add",
                "schedule.recurring_cancel",
                "schedule.adopt_inbox_today",
                "schedule.organize_today",
                "schedule.get_inbox_items",
                "schedule.get_range_items",
                "schedule.adopt_overdue_today",
                "schedule.get_today_overview",
                "schedule.get_daily_items",
            }
        )
    )


def test_recurring_add_extracts_full_title():
    planner = make_planner()

    plan = planner.plan("以后每周三晚上提醒我去跑步")

    assert plan is not None
    assert plan.tool_name == "schedule.recurring_add"
    assert plan.tool_args["title"] == "跑步"
    assert plan.tool_args["weekdays"] == ["WE"]
    assert plan.tool_args["time"] == "20:00"
    assert plan.tool_args["reminder_minutes"] == 30


def test_recurring_cancel():
    planner = make_planner()

    plan = planner.plan("取消每周三跑步")

    assert plan is not None
    assert plan.tool_name == "schedule.recurring_cancel"
    assert plan.tool_args["query"] == "跑步"


def test_mark_done():
    planner = make_planner()

    plan = planner.plan("完成调研轻量级 VLA")

    assert plan is not None
    assert plan.tool_name == "schedule.mark_done"
    assert plan.tool_args["target_text"] == "调研轻量级 VLA"


def test_adopt_inbox_today():
    planner = make_planner()

    plan = planner.plan("把 inbox 里今天该做的事项安排到今天日程")

    assert plan is not None
    assert plan.tool_name == "schedule.adopt_inbox_today"


def test_today_overview():
    planner = make_planner()

    plan = planner.plan("今天有什么事项？")

    assert plan is not None
    assert plan.tool_name == "schedule.get_today_overview"


def test_week_range():
    planner = make_planner()

    plan = planner.plan("这周有什么安排？")

    assert plan is not None
    assert plan.tool_name == "schedule.get_range_items"
    assert "start_date" in plan.tool_args
    assert "end_date" in plan.tool_args