from __future__ import annotations

import os
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    admin_password: str = ""
    secret_key: str = ""
    debug: bool = False

    db_path: str = os.environ.get("DB_PATH", "data/visactrl.db")
    log_dir: str = "logs"
    screenshot_base: str = "screenshots"

    max_action_log_entries: int = 100
    hang_timeout_seconds: int = 900
    pending_link_ttl_seconds: int = 1800
    navigate_max_retries: int = 5
    max_polls: int = 30
    min_sleep_before_retry: int = 30
    max_sleep_before_retry: int = 60
    min_wait_between_checks: int = 30
    max_wait_between_checks: int = 60
    crash_backoff_base: int = 30
    crash_backoff_max: int = 600

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    telegram_bot_token: str | None = None
    telegram_bot_username: str = "us_x_visa_x_bot"

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    sentry_dsn: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = AppSettings()
