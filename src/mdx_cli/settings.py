from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    base_url: str = "https://oprpl.mdx.jp"
    default_project_id: str | None = None
    request_timeout: int = 120
    task_poll_interval: int = 3
    task_poll_timeout: int = 600
    # クラス定義時に Path.home() を評価するとimport時点のHOMEで固定されるため
    # default_factory でインスタンス生成時に解決する。
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "mdx-cli"
    )

    model_config = SettingsConfigDict(
        env_prefix="MDX_",
    )


@lru_cache
def get_settings() -> Settings:
    """共有のSettingsインスタンスを返す。

    環境変数の再パースを避けるためキャッシュする。
    テストで環境変数を変える場合は cache_clear() を呼ぶこと。
    """
    return Settings()
