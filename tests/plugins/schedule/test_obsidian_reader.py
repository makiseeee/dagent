from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from personal_agent.core.config.loader import ObsidianConfig
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 5, 27, 9, 0, 0)

        if tz is not None:
            return fixed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))

        return fixed


@pytest.fixture()
def fake_vault(tmp_path: Path) -> Path:
    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-26.md").write_text(
        """# 2026-05-26

## 日程

- [x] 修改 Figure 2
- [ ] 调研轻量级 VLA 使用的 Benchmark
- [ ] 尝试部署上述 VLA

## Thino

- 18:57 27 号问一下陈老师 大创报销
- 18:58 周三后问一下 autodl 报销的事情 #agent/organized
- 21:27 明天晚上记得准备组会
- 21:29 下周一开始复习人工智能基础的时候记得做并且提交一下第五章作业
""",
        encoding="utf-8",
    )

    (daily_dir / "2026-05-27.md").write_text(
        """# 2026-05-27

## 日程

- [ ] 调研轻量级 VLA 使用的 Benchmark

## Thino

- 今天临时处理一个新事项
""",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture()
def reader(fake_vault: Path, monkeypatch) -> ObsidianScheduleReader:
    import personal_agent.plugins.schedule.obsidian.reader as reader_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)

    config = ObsidianConfig(
        vault_path=str(fake_vault),
        daily_note_dir="2. Areas/日记",
        date_format="%Y-%m-%d",
    )

    return ObsidianScheduleReader(config)


def test_inbox_hides_organized_capture_by_default(reader: ObsidianScheduleReader):
    result = reader.read_inbox_items(days=2, include_organized=False)

    contents = [item["content"] for item in result["items"]]

    assert "周三后问一下 autodl 报销的事情" not in contents
    assert "27 号问一下陈老师 大创报销" in contents
    assert "明天晚上记得准备组会" in contents


def test_inbox_can_show_organized_capture(reader: ObsidianScheduleReader):
    result = reader.read_inbox_items(days=2, include_organized=True)

    organized_items = [
        item
        for item in result["items"]
        if item["content"] == "周三后问一下 autodl 报销的事情"
    ]

    assert len(organized_items) == 1
    assert organized_items[0]["organized"] is True
    assert organized_items[0]["review_status"] == "already_organized"


def test_inbox_groups_due_and_future_items(reader: ObsidianScheduleReader):
    result = reader.read_inbox_items(days=2, include_organized=False)

    today_contents = [item["content"] for item in result["groups"]["today"]]
    future_contents = [item["content"] for item in result["groups"]["future"]]

    assert "27 号问一下陈老师 大创报销" in today_contents
    assert "明天晚上记得准备组会" in today_contents
    assert "今天临时处理一个新事项" in today_contents

    assert "下周一开始复习人工智能基础的时候记得做并且提交一下第五章作业" in future_contents


def test_today_overview_separates_schedule_overdue_and_inbox(reader: ObsidianScheduleReader):
    result = reader.read_today_overview(lookback_days=2)

    today_schedule_contents = [
        item["content"]
        for item in result["today_schedule_items"]
    ]

    overdue_schedule_contents = [
        item["content"]
        for item in result["overdue_schedule_items"]
    ]

    inbox_due_contents = [
        item["content"]
        for item in result["inbox_due_items"]
    ]

    inbox_future_contents = [
        item["content"]
        for item in result["inbox_future_items"]
    ]

    # 今天正式日程
    assert today_schedule_contents == [
        "调研轻量级 VLA 使用的 Benchmark",
    ]

    # 昨天的“调研轻量级 VLA...”已经接收到今天日程，所以不再作为遗留显示。
    assert "调研轻量级 VLA 使用的 Benchmark" not in overdue_schedule_contents

    # 昨天未完成且未接收到今天的正式日程仍然是遗留。
    assert "尝试部署上述 VLA" in overdue_schedule_contents

    # 未 organized 的 Thino due items 会进入 inbox_due。
    assert "27 号问一下陈老师 大创报销" in inbox_due_contents
    assert "明天晚上记得准备组会" in inbox_due_contents

    # 已 organized 的 Thino 不进入 inbox_due。
    assert "周三后问一下 autodl 报销的事情" not in inbox_due_contents

    # 未来事项单独进入 future。
    assert "下周一开始复习人工智能基础的时候记得做并且提交一下第五章作业" in inbox_future_contents