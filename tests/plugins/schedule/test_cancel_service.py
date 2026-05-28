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
from personal_agent.plugins.schedule.services.cancel_service import (
    apply_cancel_item,
    prepare_cancel_item,
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


def write_daily_note(tmp_path: Path, date: str, body: str) -> Path:
    daily_dir = tmp_path / "2. Areas" / "日记"
    daily_dir.mkdir(parents=True, exist_ok=True)
    path = daily_dir / f"{date}.md"
    path.write_text(body, encoding="utf-8")
    return path


def patch_clock(monkeypatch) -> None:
    import personal_agent.plugins.schedule.obsidian.reader as reader_module

    monkeypatch.setattr(reader_module, "datetime", FixedDateTime)


def test_prepare_and_apply_cancel_item(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    source_path = write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 准备组会
- [ ] 调研 VLA benchmark
""",
    )

    proposal = prepare_cancel_item(
        config,
        target_text="准备组会",
    )

    assert proposal["operation"] == "schedule.cancel_item"
    assert proposal["status"] == "prepared"
    assert proposal["changed"] is True
    assert proposal["matched_item"]["content"] == "准备组会"
    assert "- [ ] 准备组会 #agent/cancelled" in proposal["diff"]

    result = apply_cancel_item(config, proposal)

    assert result["status"] == "applied"
    text = source_path.read_text(encoding="utf-8")
    assert "- [ ] 准备组会 #agent/cancelled" in text
    assert "- [ ] 调研 VLA benchmark" in text


def test_already_cancelled_is_not_reprocessed(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 准备组会 #agent/cancelled
""",
    )

    proposal = prepare_cancel_item(
        config,
        target_text="准备组会",
    )

    assert proposal["status"] == "not_found"
    assert proposal["changed"] is False


def test_ambiguous_match_returns_candidates(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 问陈老师报销
- [ ] 问李老师报销
""",
    )

    proposal = prepare_cancel_item(
        config,
        target_text="问老师报销",
    )

    assert proposal["status"] == "ambiguous_match"
    assert proposal["changed"] is False
    assert len(proposal["candidates"]) == 2


def test_low_confidence_returns_candidates(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 准备组会
- [ ] 调研 VLA benchmark
""",
    )

    proposal = prepare_cancel_item(
        config,
        target_text="这个任务",
    )

    assert proposal["status"] == "low_confidence"
    assert proposal["changed"] is False
    assert [item["content"] for item in proposal["candidates"]] == [
        "准备组会",
        "调研 VLA benchmark",
    ]


def test_apply_blocks_unrelated_changes(tmp_path: Path, monkeypatch):
    patch_clock(monkeypatch)
    config = make_config(tmp_path)

    write_daily_note(
        tmp_path,
        "2026-05-29",
        """# 2026-05-29

## 日程

- [ ] 准备组会
- [ ] 调研 VLA benchmark
""",
    )

    proposal = prepare_cancel_item(
        config,
        target_text="准备组会",
    )
    note_path = proposal["note_path"]
    proposal["files"][note_path] = proposal["files"][note_path].replace(
        "调研 VLA benchmark",
        "篡改其他任务",
    )

    result = apply_cancel_item(config, proposal)

    assert result["status"] == "blocked"
    assert result["message"] == "Cancel proposal contains changes outside the matched line."
