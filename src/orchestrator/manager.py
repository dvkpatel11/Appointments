from __future__ import annotations

import multiprocessing
import os
import time

from src.config import settings
from src.domain.client import Client
from src.infrastructure import logging as client_logging
from src.infrastructure.repositories import client_repo, state_repo

logger = client_logging.setup_server_logger()
_alive_processes: dict[str, multiprocessing.Process] = {}
_error_counts: dict[str, int] = {}
_last_crash: dict[str, float] = {}


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _scraper_entry(
    client_id: str,
    username: str,
    password: str,
    appointment_id: str | None,
    appointment_url: str | None,
    visa_type: str,
    reschedule: bool,
    preferred_locations: list[str] | None,
    preferred_date_from: str | None,
    preferred_date_to: str | None,
    notification_email: str | None,
    telegram_chat_id: str | None,
    phone_number: str | None,
) -> None:
    if visa_type == "canada":
        from src.scraper.canada.scraper import CanadaVisaScraper

        scraper = CanadaVisaScraper(
            client_id=client_id,
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            reschedule=reschedule,
            preferred_locations=preferred_locations,
            preferred_date_from=preferred_date_from,
            preferred_date_to=preferred_date_to,
            notification_email=notification_email,
            telegram_chat_id=telegram_chat_id,
            phone_number=phone_number,
        )
    elif visa_type == "uk":
        from src.scraper.uk.scraper import UKVisaScraper

        scraper = UKVisaScraper(
            client_id=client_id,
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            reschedule=reschedule,
            preferred_locations=preferred_locations,
            preferred_date_from=preferred_date_from,
            preferred_date_to=preferred_date_to,
            notification_email=notification_email,
            telegram_chat_id=telegram_chat_id,
            phone_number=phone_number,
        )
    else:
        raise ValueError(f"Unknown visa type: {visa_type}")

    scraper.run()


def start(client: Client) -> bool:
    client_id = client.id
    if client_id in _alive_processes and _alive_processes[client_id].is_alive():
        logger.warning(f"Client {client_id[:12]}... already running")
        return False
    if not client.username or not client.password:
        logger.error(f"Client {client_id[:12]}... missing credentials")
        return False
    try:
        proc = multiprocessing.Process(
            target=_scraper_entry,
            args=(
                client_id,
                client.username,
                client.password,
                client.appointment_id,
                client.appointment_url,
                client.visa_type.value,
                client.reschedule,
                client.preferred_locations,
                client.preferred_date_from,
                client.preferred_date_to,
                client.notification_email,
                client.telegram_chat_id,
                client.phone_number,
            ),
        )
        proc.start()
        _alive_processes[client_id] = proc
        client_repo.update_field(client_id, agent_pid=proc.pid)
        logger.info(f"Started scraper for {client_id[:12]}... (pid={proc.pid})")
        return True
    except Exception as e:
        logger.error(f"Failed to start scraper for {client_id[:12]}...: {e}")
        _alive_processes.pop(client_id, None)
        return False


def stop(client_id: str) -> bool:
    proc = _alive_processes.get(client_id)
    if not proc or not proc.is_alive():
        _alive_processes.pop(client_id, None)
        return False
    try:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=3)
    except Exception as e:
        logger.warning("Error stopping process for %s: %s", client_id[:12], e)
    _alive_processes.pop(client_id, None)
    client_repo.update_field(client_id, agent_pid=None, state="stopped")
    state_repo.delete(client_id)
    return True


def stop_all() -> None:
    for client_id in list(_alive_processes.keys()):
        stop(client_id)


def is_alive(client_id: str) -> bool:
    proc = _alive_processes.get(client_id)
    return proc is not None and proc.is_alive()


def get_backoff_seconds(client_id: str) -> int:
    err_count = _error_counts.get(client_id, 0)
    if err_count <= 0:
        return 0
    return min(settings.crash_backoff_base * (2 ** (err_count - 1)), settings.crash_backoff_max)


def check_and_recover() -> None:
    approved = client_repo.get_by_state("approved")
    now = time.time()
    for client_id, client in approved.items():
        proc = _alive_processes.get(client_id)
        if proc and proc.is_alive():
            continue
        if _pid_alive(client.agent_pid):
            _alive_processes.pop(client_id, None)
            continue
        _alive_processes.pop(client_id, None)
        last = _last_crash.get(client_id, 0)
        backoff = get_backoff_seconds(client_id)
        if backoff > 0 and (now - last) < backoff:
            logger.info(f"Client {client_id[:12]}... in backoff ({int(backoff - (now - last))}s remaining)")
            continue
        state_repo.delete(client_id)
        _error_counts[client_id] = _error_counts.get(client_id, 0) + 1
        _last_crash[client_id] = now
        logger.info(f"Recovering client {client_id[:12]}... (crash #{_error_counts[client_id]})")
        start(client)


def reset_error_count(client_id: str) -> None:
    _error_counts.pop(client_id, None)
    _last_crash.pop(client_id, None)


def resume_approved_agents() -> None:
    """Start scraper processes for all approved clients (called on app startup)."""
    approved = client_repo.get_by_state("approved")
    _error_counts.clear()
    _last_crash.clear()
    for client_id, client in approved.items():
        if client_id not in _alive_processes or not _alive_processes[client_id].is_alive():
            logger.info(f"Resuming agent {client_id[:12]}...")
            start(client)
