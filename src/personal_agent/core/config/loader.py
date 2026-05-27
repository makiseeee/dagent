from pathlib import Path
from pydantic import BaseModel
import yaml


class LLMConfig(BaseModel):
    provider: str
    base_url: str
    default_model: str
    cheap_model: str | None = None


class AgentConfig(BaseModel):
    name: str = "personal-agent"
    require_confirmation_for_write: bool = True


class ObsidianConfig(BaseModel):
    vault_path: str = ""
    daily_note_dir: str = ""
    date_format: str = "%Y-%m-%d"

class BackupConfig(BaseModel):
    git_enabled: bool = True
    git_auto_push: bool = False
    default_commit_message: str = "Backup Obsidian vault"


class AppConfig(BaseModel):
    llm: LLMConfig
    agent: AgentConfig
    obsidian: ObsidianConfig
    backup: BackupConfig = BackupConfig()


def load_config(path: str = "configs/agent.yaml") -> AppConfig:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return AppConfig.model_validate(raw)