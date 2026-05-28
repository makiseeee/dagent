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
from personal_agent.plugins.schedule.services.add_item_service import (
    apply_add_today_item,
    prepare_add_today_item,
)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 5, 29, 9, 0, 0)

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


def patch_clock(monkeypatch) -> None:
    import personal_agent.plugins.schedule.obsidian.reader as reader_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)


def write_daily_note(tmp_path: Path, date: str, body: str) -> Path:
    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True, exist_ok=True)
    path = daily_dir / f"{date}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_prepare_and_apply_add_today_item(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)
    note_path = write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 已有任务

## Thino
""",
    )

    proposal = prepare_add_today_item(
        config,
        content="准备组会",
        llm_rewrite=False,
    )

    assert proposal["operation"] == "schedule.add_today_item"
    assert proposal["status"] == "prepared"
    assert proposal["changed"] is True
    assert proposal["new_lines"] == ["- [ ] 准备组会"]
    assert "+- [ ] 准备组会" in proposal["diff"]

    result = apply_add_today_item(config, proposal)

    assert result["status"] == "applied"
    assert "- [ ] 准备组会" in note_path.read_text(encoding="utf-8")


def test_add_today_item_target_note_missing(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)

    proposal = prepare_add_today_item(
        make_config(tmp_path),
        content="准备组会",
    )

    assert proposal["status"] == "target_note_missing"
    assert proposal["changed"] is False


def test_add_today_item_creates_schedule_section_when_missing(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)
    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## Thino
""",
    )

    proposal = prepare_add_today_item(
        config,
        content="问陈老师报销",
    )

    assert proposal["status"] == "prepared"
    assert "+## 日程" in proposal["diff"]
    assert "+- [ ] 问陈老师报销" in proposal["diff"]


def test_add_today_item_duplicate_is_skipped(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)
    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 准备组会
""",
    )

    proposal = prepare_add_today_item(
        config,
        content="准备组会",
    )

    assert proposal["status"] == "duplicate"
    assert proposal["changed"] is False
    assert proposal["skipped_duplicates"] == ["准备组会"]


def test_apply_add_today_item_blocks_unexpected_file(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)
    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程
""",
    )

    proposal = prepare_add_today_item(
        config,
        content="准备组会",
    )
    proposal["files"]["/tmp/other.md"] = "bad"

    result = apply_add_today_item(config, proposal)

    assert result["status"] == "blocked"
    assert result["message"] == "Add-today proposal contains unexpected file changes."
