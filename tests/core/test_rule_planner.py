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
                "schedule.reschedule_item",
                "schedule.cancel_item",
                "schedule.add_today_item",
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


def test_cancel_item_simple():
    planner = make_planner()

    plan = planner.plan("取消准备组会")

    assert plan is not None
    assert plan.tool_name == "schedule.cancel_item"
    assert plan.tool_args["target_text"] == "准备组会"
    assert plan.tool_args["days"] == 7


def test_cancel_item_ba_cancel():
    planner = make_planner()

    plan = planner.plan("把准备组会取消")

    assert plan is not None
    assert plan.tool_name == "schedule.cancel_item"
    assert plan.tool_args["target_text"] == "准备组会"


def test_cancel_item_today_do_not_do():
    planner = make_planner()

    plan = planner.plan("今天不做准备组会了")

    assert plan is not None
    assert plan.tool_name == "schedule.cancel_item"
    assert plan.tool_args["target_text"] == "准备组会"


def test_cancel_item_do_not_do():
    planner = make_planner()

    plan = planner.plan("不做调研 VLA benchmark 了")

    assert plan is not None
    assert plan.tool_name == "schedule.cancel_item"
    assert plan.tool_args["target_text"] == "调研 VLA benchmark"


def test_mark_done():
    planner = make_planner()

    plan = planner.plan("完成调研轻量级 VLA")

    assert plan is not None
    assert plan.tool_name == "schedule.mark_done"
    assert plan.tool_args["target_text"] == "调研轻量级 VLA"


def test_reschedule_item_change_to_tomorrow():
    planner = make_planner()

    plan = planner.plan("把准备组会改到明天")

    assert plan is not None
    assert plan.tool_name == "schedule.reschedule_item"
    assert plan.tool_args["target_text"] == "准备组会"
    assert plan.tool_args["target_date_text"] == "明天"
    assert plan.tool_args["days"] == 7


def test_reschedule_item_move_to_next_monday():
    planner = make_planner()

    plan = planner.plan("把调研 VLA benchmark 挪到下周一")

    assert plan is not None
    assert plan.tool_name == "schedule.reschedule_item"
    assert plan.tool_args["target_text"] == "调研 VLA benchmark"
    assert plan.tool_args["target_date_text"] == "下周一"


def test_reschedule_item_do_tomorrow():
    planner = make_planner()

    plan = planner.plan("问陈老师报销明天再做")

    assert plan is not None
    assert plan.tool_name == "schedule.reschedule_item"
    assert plan.tool_args["target_text"] == "问陈老师报销"
    assert plan.tool_args["target_date_text"] == "明天"


def test_reschedule_item_this_task_tomorrow():
    planner = make_planner()

    plan = planner.plan("这个任务明天再做")

    assert plan is not None
    assert plan.tool_name == "schedule.reschedule_item"
    assert plan.tool_args["target_text"] == "这个任务"
    assert plan.tool_args["target_date_text"] == "明天"


def test_adopt_inbox_today():
    planner = make_planner()

    plan = planner.plan("把 inbox 里今天该做的事项安排到今天日程")

    assert plan is not None
    assert plan.tool_name == "schedule.adopt_inbox_today"


def test_add_today_item_colon():
    planner = make_planner()

    plan = planner.plan("添加今天任务：准备组会")

    assert plan is not None
    assert plan.tool_name == "schedule.add_today_item"
    assert plan.tool_args["content"] == "准备组会"
    assert plan.tool_args["llm_rewrite"] is True


def test_add_today_item_today_add_task():
    planner = make_planner()

    plan = planner.plan("今天加一个任务，整理实验代码")

    assert plan is not None
    assert plan.tool_name == "schedule.add_today_item"
    assert plan.tool_args["content"] == "整理实验代码"


def test_add_today_item_record_to_today_schedule():
    planner = make_planner()

    plan = planner.plan("记到今天日程：问陈老师报销")

    assert plan is not None
    assert plan.tool_name == "schedule.add_today_item"
    assert plan.tool_args["content"] == "问陈老师报销"


def test_add_today_item_arrange_specific_content():
    planner = make_planner()

    plan = planner.plan("帮我今天安排一下读论文")

    assert plan is not None
    assert plan.tool_name == "schedule.add_today_item"
    assert plan.tool_args["content"] == "读论文"


def test_add_today_item_keeps_time_text():
    planner = make_planner()

    plan = planner.plan("今天下午安排一下写实验报告")

    assert plan is not None
    assert plan.tool_name == "schedule.add_today_item"
    assert plan.tool_args["content"] == "今天下午写实验报告"


def test_arrange_today_schedule_adopts_overdue():
    planner = make_planner()

    plan = planner.plan("安排今天的日程")

    assert plan is not None
    assert plan.tool_name == "schedule.adopt_overdue_today"
    assert plan.tool_args["lookback_days"] == 7
    assert plan.tool_args["llm_rewrite"] is False


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
