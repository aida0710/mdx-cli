from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    base_url: str = "https://oprpl.mdx.jp"
    default_project_id: str | None = None
    request_timeout: int = 120
    task_poll_interval: int = 3
    task_poll_timeout: int = 600
    config_dir: Path = Path.home() / ".config" / "mdx-cli"

    model_config = SettingsConfigDict(
        env_prefix="MDX_",
    )
