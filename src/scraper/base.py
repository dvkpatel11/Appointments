from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.config import settings
from src.infrastructure.logging import ClientLoggerAdapter
from src.infrastructure.repositories import state_repo as state_db
from src.services.notification_service import NotificationService


@dataclass
class CheckResult:
    available: bool
    date: datetime | None = None
    location: str | None = None


class VisaScraper(ABC):
    USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    ]

    def __init__(
        self,
        client_id: str,
        username: str,
        password: str,
        appointment_id: str | None = None,
        appointment_url: str | None = None,
        reschedule: bool = False,
        preferred_locations: list[str] | None = None,
        preferred_date_from: str | None = None,
        preferred_date_to: str | None = None,
        notification_email: str | None = None,
        telegram_chat_id: str | None = None,
        phone_number: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.username = username
        self.password = password
        self.appointment_id = appointment_id or ""
        self.appointment_url = appointment_url or ""
        self.reschedule = reschedule
        self.preferred_locations = preferred_locations
        self.preferred_date_from = preferred_date_from
        self.preferred_date_to = preferred_date_to
        self.notification_email = notification_email
        self.telegram_chat_id = telegram_chat_id
        self.phone_number = phone_number

        self.log = ClientLoggerAdapter(client_id)
        self.notifier = NotificationService()

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_running = False
        self._shutting_down = False

        self.current_date: datetime | None = None
        self.new_date: datetime | None = None
        self.current_action: str = ""
        self.action_log: list[dict[str, str]] = []
        self.last_checked_location: str | None = None
        self.screenshot_path: str | None = None
        self.poll_count: int = 0
        self.debug_counter: int = 0

    @abstractmethod
    def get_login_url(self) -> str: ...

    @abstractmethod
    def get_selectors(self) -> dict[str, str]: ...

    @abstractmethod
    def get_visa_locations(self) -> dict[str, str]: ...

    @abstractmethod
    def login(self) -> bool: ...

    @abstractmethod
    def get_current_appointment(self) -> datetime | None: ...

    @abstractmethod
    def check_availability(self, location: str) -> CheckResult: ...

    @abstractmethod
    def reschedule_to(self, location: str) -> bool: ...

    def _log(self, msg: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.action_log.append({"ts": ts, "msg": msg})
        if len(self.action_log) > settings.max_action_log_entries:
            self.action_log = self.action_log[-settings.max_action_log_entries :]
        if not self._shutting_down:
            self._persist_state()
        getattr(self.log, level)(msg)

    def _persist_state(self) -> None:
        state_db.save(
            self.client_id,
            {
                "is_running": self._is_running,
                "current_action": self.current_action,
                "action_log": self.action_log,
                "current_appointment": str(self.current_date) if self.current_date else None,
                "new_appointment": str(self.new_date) if self.new_date else None,
                "last_checked_location": self.last_checked_location,
                "screenshot_path": self.screenshot_path,
            },
        )

    def _log_url(self, label: str) -> None:
        try:
            self._log(f"[{label}] URL: {self._page.url}")
        except Exception:
            self._log(f"[{label}] URL: <unreachable>", "warn")

    def _screenshot(self, name: str, persist: bool = False) -> None:
        self.debug_counter += 1
        screenshot_dir = Path(settings.screenshot_base) / self.client_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / f"{self.debug_counter:03d}_{name}.png"
        try:
            self._page.screenshot(path=str(path))
            if persist:
                self.screenshot_path = str(path)
                self._persist_state()
        except Exception:
            pass

    def _notify(self, message: str) -> None:
        self.notifier.send(
            message=message,
            email_addr=self.notification_email,
            telegram_chat_id=self.telegram_chat_id,
            phone_number=self.phone_number,
            logger=lambda msg, lvl="info": self._log(msg, lvl),
        )

    def _init_browser(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def _close_browser(self) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def _new_context(self) -> None:
        if self._context:
            self._context.close()
        user_agent = random.choice(self.USER_AGENTS)
        self._context = self._browser.new_context(user_agent=user_agent)
        self._page = self._context.new_page()

    def _navigate(self, url: str) -> None:
        self._page.goto(url)
        self._page.wait_for_load_state("networkidle")

    def run(self) -> None:
        self._is_running = True
        self._log("Automation started")
        self._notify("Visa Automation started — monitoring for earlier dates...")
        try:
            self._init_browser()
            while self._is_running:
                for _ in range(1):
                    if not self._is_running:
                        break
                    try:
                        self._new_context()
                        self.login()
                        self.current_date = self.get_current_appointment()
                        for check_num in range(12):
                            if not self._is_running:
                                return
                            self._log(f"Check {check_num + 1}/12")
                            self._run_check_cycle()
                            if check_num < 11:
                                self._sleep_before_retry(check_num)
                    except Exception as e:
                        self._handle_error(e)
                    finally:
                        if self._context:
                            self._context.close()
                if self._is_running:
                    wait = random.randint(30, 60)
                    self._log(f"Waiting {wait}s before next cycle")
                    time.sleep(wait)
        finally:
            self._is_running = False
            self._shutting_down = True
            self._close_browser()
            self._persist_state()
            self._log("Automation stopped")

    def _run_check_cycle(self) -> bool:
        locations = self.get_visa_locations()
        if self.preferred_locations:
            locations = {k: v for k, v in locations.items() if k in self.preferred_locations}
        found = False
        for location in locations:
            self.last_checked_location = location
            self._log(f"Checking {location}")
            result = self.check_availability(location)
            if result.available and result.date:
                self.new_date = result.date
                if not self._in_preferred_window(result.date):
                    self._log(f"Date {result.date.date()} outside preferred window — skipping")
                    continue
                msg = f"Date available at {location} on {result.date.strftime('%Y-%m-%d')}"
                self._log(msg)
                self._screenshot(f"date_found_{location}", persist=True)
                if self.current_date and result.date < self.current_date:
                    self._notify(f"Earlier date found at {location}: {result.date.strftime('%Y-%m-%d')}")
                if self.reschedule and self.current_date and result.date < self.current_date:
                    self.reschedule_to(location)
                found = True
        return found

    def _in_preferred_window(self, date: datetime) -> bool:
        if not self.preferred_date_from and not self.preferred_date_to:
            return True
        if self.preferred_date_from and date < datetime.strptime(self.preferred_date_from, "%Y-%m-%d"):
            return False
        if self.preferred_date_to and date > datetime.strptime(self.preferred_date_to, "%Y-%m-%d"):
            return False
        return True

    def _sleep_before_retry(self, check_num: int) -> None:
        base = (check_num // 5) * 30
        sleep_time = random.randint(base, base + 30)
        self._log(f"Sleeping {sleep_time}s before next check")
        time.sleep(sleep_time)

    def _handle_error(self, error: Exception) -> None:
        self._log(f"Error: {error}", "error")
        self._screenshot("error")
        time.sleep(300)

    def stop(self) -> None:
        self._is_running = False
        self._log("Stop requested")
