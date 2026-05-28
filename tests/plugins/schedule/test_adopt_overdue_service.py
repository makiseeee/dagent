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
from personal_agent.plugins.schedule.services.adopt_overdue_service import (
    prepare_adopt_overdue_today,
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


def test_prepare_adopt_overdue_today_uses_overdue_schedule_items(
    tmp_path: Path,
    monkeypatch,
):
    import personal_agent.plugins.schedule.obsidian.reader as reader_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)

    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-28.md").write_text(
        """# 2026-05-28

## 日程

- [ ] 进行 WF 仿真
- [ ] 复现 VLA Adapter 与 Libero
""",
        encoding="utf-8",
    )

    (daily_dir / "2026-05-29.md").write_text(
        """# 2026-05-29

## 日程

- [ ] 询问陈老师后续安排
""",
        encoding="utf-8",
    )

    proposal = prepare_adopt_overdue_today(
        make_config(tmp_path),
        llm=None,
        lookback_days=7,
        llm_rewrite=False,
    )

    assert proposal["changed"] is True
    assert [item["content"] for item in proposal["source_items"]] == [
        "进行 WF 仿真",
        "复现 VLA Adapter 与 Libero",
    ]
    assert proposal["new_lines"] == [
        "- [ ] 进行 WF 仿真",
        "- [ ] 复现 VLA Adapter 与 Libero",
    ]
