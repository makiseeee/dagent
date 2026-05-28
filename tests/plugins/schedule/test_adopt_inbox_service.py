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
from personal_agent.plugins.schedule.services.adopt_inbox_service import (
    prepare_adopt_inbox_today,
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


def test_adopt_inbox_today_includes_old_note_default_capture(tmp_path: Path, monkeypatch):
    import personal_agent.plugins.schedule.obsidian.reader as reader_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)

    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-26.md").write_text(
        """# 2026-05-26

## Thino

- 17:30 处理旧备忘
""",
        encoding="utf-8",
    )

    (daily_dir / "2026-05-27.md").write_text(
        """# 2026-05-27

## 日程

## Thino
""",
        encoding="utf-8",
    )

    proposal = prepare_adopt_inbox_today(
        make_config(tmp_path),
        llm=None,
        lookback_days=2,
        llm_rewrite=False,
    )

    source_items = proposal["source_items"]
    assert [item["content"] for item in source_items] == ["处理旧备忘"]
    assert source_items[0]["bucket"] == "overdue"
    assert proposal["changed"] is True
    assert "- [ ] 处理旧备忘" in proposal["diff"]
    assert "#agent/organized" in proposal["diff"]
