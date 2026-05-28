from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent.core.config.loader import (
    AgentConfig,
    AppConfig,
    BackupConfig,
    LLMConfig,
    ObsidianConfig,
)
from personal_agent.plugins.schedule.services.reschedule_service import (
    apply_reschedule_item,
    prepare_reschedule_item,
)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 5, 27, 9, 0, 0)

        if tz is not None:
            return fixed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))

        return fixed


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        llm=LLMConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            default_model="deepseek-chat",
            cheap_model=None,
        ),
        agent=AgentConfig(
            name="test-agent",
            require_confirmation_for_write=True,
        ),
        obsidian=ObsidianConfig(
            vault_path=str(tmp_path),
            daily_note_dir="2. Areas/日记",
            date_format="%Y-%m-%d",
        ),
        backup=BackupConfig(
            git_enabled=False,
            git_auto_push=False,
            default_commit_message="test",
        ),
    )


def write_daily_note(tmp_path: Path, date: str, body: str) -> Path:
    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True, exist_ok=True)
    path = daily_dir / f"{date}.md"
    path.write_text(body, encoding="utf-8")
    return path


def patch_clock(monkeypatch) -> None:
    import personal_agent.plugins.schedule.obsidian.reader as reader_module
    import personal_agent.plugins.schedule.services.reschedule_service as service_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)
    monkeypatch.setattr(service_module, "datetime", FixedDateTime)


def test_prepare_and_apply_reschedule_item(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    source_path = write_daily_note(
        tmp_path,
        "2026-05-27",
        """# 2026-05-27

## 日程

- [ ] 准备组会
- [ ] 调研 VLA benchmark
""",
    )
    target_path = write_daily_note(
        tmp_path,
        "2026-05-28",
        """# 2026-05-28

## 日程

- [ ] 已有任务
""",
    )

    proposal = prepare_reschedule_item(
        config,
        target_text="准备组会",
        target_date_text="明天",
    )

    assert proposal["operation"] == "schedule.reschedule_item"
    assert proposal["status"] == "prepared"
    assert proposal["changed"] is True
    assert proposal["target_date"] == "2026-05-28"
    assert proposal["matched_item"]["content"] == "准备组会"
    assert "- [ ] 准备组会 #agent/rescheduled" in proposal["diff"]
    assert "+- [ ] 准备组会" in proposal["diff"]

    result = apply_reschedule_item(config, proposal)

    assert result["status"] == "applied"
    assert "- [ ] 准备组会 #agent/rescheduled" in source_path.read_text(
        encoding="utf-8"
    )
    assert "- [ ] 准备组会" in target_path.read_text(encoding="utf-8")


def test_target_note_missing_blocks(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-27",
        """# 2026-05-27

## 日程

- [ ] 准备组会
""",
    )

    proposal = prepare_reschedule_item(
        config,
        target_text="准备组会",
        target_date_text="明天",
    )

    assert proposal["status"] == "target_note_missing"
    assert proposal["changed"] is False


def test_duplicate_target_only_marks_original(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    source_path = write_daily_note(
        tmp_path,
        "2026-05-27",
        """# 2026-05-27

## 日程

- [ ] 调研 VLA benchmark
""",
    )
    target_path = write_daily_note(
        tmp_path,
        "2026-05-28",
        """# 2026-05-28

## 日程

- [ ] 调研 VLA benchmark
""",
    )

    proposal = prepare_reschedule_item(
        config,
        target_text="调研 VLA benchmark",
        target_date_text="明天",
    )

    assert proposal["status"] == "prepared"
    assert proposal["changed"] is True
    assert proposal["new_lines"] == []
    assert proposal["skipped_duplicates"] == ["调研 VLA benchmark"]

    apply_reschedule_item(config, proposal)

    assert "#agent/rescheduled" in source_path.read_text(encoding="utf-8")
    target_text = target_path.read_text(encoding="utf-8")
    assert target_text.count("- [ ] 调研 VLA benchmark") == 1


def test_ambiguous_match_returns_candidates(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-27",
        """# 2026-05-27

## 日程

- [ ] 问陈老师报销
- [ ] 问李老师报销
""",
    )
    write_daily_note(
        tmp_path,
        "2026-05-28",
        """# 2026-05-28

## 日程
""",
    )

    proposal = prepare_reschedule_item(
        config,
        target_text="问老师报销",
        target_date_text="明天",
    )

    assert proposal["status"] == "ambiguous_match"
    assert proposal["changed"] is False
    assert len(proposal["candidates"]) == 2


def test_low_confidence_returns_recent_candidates(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-27",
        """# 2026-05-27

## 日程

- [ ] 准备组会
- [ ] 调研 VLA benchmark
""",
    )
    write_daily_note(
        tmp_path,
        "2026-05-28",
        """# 2026-05-28

## 日程
""",
    )

    proposal = prepare_reschedule_item(
        config,
        target_text="这个任务",
        target_date_text="明天",
    )

    assert proposal["status"] == "low_confidence"
    assert proposal["changed"] is False
    assert [item["content"] for item in proposal["candidates"]] == [
        "准备组会",
        "调研 VLA benchmark",
    ]
