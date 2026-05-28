from pathlib import Path

from personal_agent.core.config.loader import AppConfig, ObsidianConfig, LLMConfig, BackupConfig
from personal_agent.plugins.schedule.services.recurring_service import (
    prepare_add_recurring_rule,
    prepare_cancel_recurring_rule,
    apply_recurring_proposal,
)
from personal_agent.core.config.loader import (
    AppConfig,
    AgentConfig,
    ObsidianConfig,
    LLMConfig,
    BackupConfig,
)


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


def test_prepare_and_apply_add_recurring_rule(tmp_path: Path):
    config = make_config(tmp_path)

    proposal = prepare_add_recurring_rule(
        config,
        title="跑步",
        weekdays=["WE"],
        time="20:00",
        reminder_minutes=30,
        duration_minutes=60,
        start_date="2026-05-27",
    )

    assert proposal["operation"] == "schedule.recurring_add"
    assert proposal["status"] == "prepared"
    assert proposal["changed"] is True
    assert proposal["rule"]["title"] == "跑步"
    assert proposal["rule"]["weekdays"] == ["WE"]
    assert proposal["rule"]["time"] == "20:00"
    assert ".wenbo-agent/recurring.yaml" in proposal["note_path"]
    assert "+- id:" in proposal["diff"] or "+recurring:" in proposal["diff"]

    result = apply_recurring_proposal(config, proposal)

    assert result["status"] == "applied"

    store_path = tmp_path / ".wenbo-agent" / "recurring.yaml"
    assert store_path.exists()

    text = store_path.read_text(encoding="utf-8")
    assert "跑步" in text
    assert "WE" in text
    assert "20:00" in text


def test_prepare_cancel_recurring_rule_by_query(tmp_path: Path):
    config = make_config(tmp_path)

    add_proposal = prepare_add_recurring_rule(
        config,
        title="跑步",
        weekdays=["WE"],
        time="20:00",
        start_date="2026-05-27",
    )
    apply_recurring_proposal(config, add_proposal)

    cancel_proposal = prepare_cancel_recurring_rule(
        config,
        query="跑步",
    )

    assert cancel_proposal["operation"] == "schedule.recurring_cancel"
    assert cancel_proposal["status"] == "prepared"
    assert cancel_proposal["changed"] is True
    assert cancel_proposal["rule"]["title"] == "跑步"
    assert cancel_proposal["rule"]["status"] == "cancelled"
    assert "-  status: active" in cancel_proposal["diff"]
    assert "+  status: cancelled" in cancel_proposal["diff"]

    result = apply_recurring_proposal(config, cancel_proposal)

    assert result["status"] == "applied"

    store_path = tmp_path / ".wenbo-agent" / "recurring.yaml"
    text = store_path.read_text(encoding="utf-8")

    assert "status: cancelled" in text


def test_cancel_recurring_rule_not_found(tmp_path: Path):
    config = make_config(tmp_path)

    proposal = prepare_cancel_recurring_rule(
        config,
        query="不存在的循环事项",
    )

    assert proposal["operation"] == "schedule.recurring_cancel"
    assert proposal["status"] == "not_found"
    assert proposal["changed"] is False