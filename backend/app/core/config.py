from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "yt-transcript-api"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    temp_dir: str = "./tmp"
    upload_storage_dir: str = "./storage"
    asr_model_size: str = "base"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    database_url: str = "sqlite:///./app.db"
    database_echo: bool = False
    database_auto_create_tables: bool = True
    task_poll_interval_seconds: int = 2
    subtitle_fetch_timeout_seconds: int = 180
    ytdlp_js_runtimes: str = "node"
    ytdlp_cookies_from_browser: str = ""
    ytdlp_cookies_file: str = ""
    ytdlp_extractor_args: str = "youtube:player_client=web"
    ytdlp_remote_components: str = "ejs:github"
    allow_user_supplied_cookies: bool = False
    youtube_cookies_max_chars: int = 200_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def temp_path(self) -> Path:
        return Path(self.temp_dir).resolve()

    @property
    def upload_storage_path(self) -> Path:
        return Path(self.upload_storage_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
