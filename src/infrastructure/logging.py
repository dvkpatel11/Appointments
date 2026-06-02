from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config import settings


def setup_server_logger() -> logging.Logger:
    logger = logging.getLogger("usvisa")
    if logger.handlers:
        return logger

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "server.log"

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_client_logger(client_id: str) -> logging.Logger:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{client_id}.log"

    logger_name = f"usvisa.client.{client_id}"
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(client_id)s] %(message)s")

        file_handler = RotatingFileHandler(str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class ClientLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        super().__init__(get_client_logger(client_id), {"client_id": client_id})

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        kwargs.setdefault("extra", {})["client_id"] = self.client_id
        return msg, kwargs


def read_client_log(client_id: str, lines: int = 200) -> str:
    log_file = Path(settings.log_dir) / f"{client_id}.log"
    if not log_file.exists():
        return ""
    with open(log_file) as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])
