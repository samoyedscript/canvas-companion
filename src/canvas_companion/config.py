"""Application configuration via environment variables."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CC_",
    )

    # Canvas
    canvas_base_url: str
    canvas_api_token: SecretStr

    # Google Drive
    google_credentials_path: Path = Path("credentials/credentials.json")
    google_token_path: Path = Path("credentials/token.json")
    drive_root_folder_name: str = "Canvas Companion"

    # Telegram
    telegram_bot_token: SecretStr
    telegram_chat_id: str

    # Scheduler
    sync_interval_minutes: int = 30

    # Database
    db_path: Path = Path("canvas_companion.db")

    # Logging
    log_level: str = "INFO"
