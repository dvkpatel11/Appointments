from __future__ import annotations

import re
import time
from datetime import datetime

from dateutil import parser
from playwright.sync_api import TimeoutError

from src.scraper.base import CheckResult, VisaScraper
from src.scraper.canada import selectors


class CanadaVisaScraper(VisaScraper):
    def get_login_url(self) -> str:
        return selectors.LOGIN_URL

    def get_selectors(self) -> dict[str, str]:
        return selectors.SELECTORS

    def get_visa_locations(self) -> dict[str, str]:
        return selectors.VISA_LOCATIONS

    def get_appointment_url(self) -> str:
        return selectors.APPOINTMENT_URL_TEMPLATE.format(self.appointment_id)

    def login(self) -> bool:
        s = selectors.SELECTORS
        try:
            self._log("Attempting login")
            self.current_action = "LOGIN"
            self._navigate(selectors.LOGIN_URL)
            self._screenshot("login_page")

            self._page.get_by_label(s["username"]).fill(self.username)
            self._page.get_by_label(s["password"]).fill(self.password)
            self._page.locator("label").filter(has_text=s["terms_label"]).click()
            self._page.get_by_role("button", name=s["sign_in_button"]).click()

            self._log("Login successful")
            self._screenshot("login_success")
            self.current_action = "IDLE"
            return True

        except Exception as e:
            self._log(f"Login failed: {e}", "error")
            self._screenshot("login_error")
            time.sleep(60)
            try:
                self._page.get_by_role("menuitem", name=s["continue_button"]).click()
            except Exception:
                pass
            return False

    def get_current_appointment(self) -> datetime | None:
        try:
            date_text = self._page.locator(selectors.SELECTORS["appointment_date"]).text_content()
        except Exception as e:
            e_strings = str(e).split("get_by_text")
            if len(e_strings) > 1:
                start = e_strings[1].index("(")
                end = e_strings[1].index(")")
                date_text = e_strings[1][start + 1 : end]
            else:
                self._log("Could not parse current appointment", "warning")
                return None

        date_text = date_text.replace("\n", "")
        matches = re.search(selectors.APPOINTMENT_DATE_REGEX, date_text)
        if matches:
            date_text = matches.group(1).strip()
            return parser.parse(date_text)
        self._log("No current appointment found", "warning")
        return None

    def check_availability(self, location: str) -> CheckResult:
        if location not in selectors.VISA_LOCATIONS:
            return CheckResult(available=False)

        s = selectors.SELECTORS
        self._log(f"Selecting location: {location}")

        try:
            loc = self._page.locator(s["location"])
            if loc.count() == 0:
                self._log(f"Location selector not found for {location}", "error")
                return CheckResult(available=False)

            loc.select_option(location)
            self._page.wait_for_load_state("networkidle")
            self._screenshot(f"location_{location}")

            try:
                self._page.wait_for_selector(s["not_available"], timeout=100)
                return CheckResult(available=False)
            except TimeoutError:
                pass

            try:
                self._page.wait_for_selector(s["date_dropdown"], timeout=5000)
                self._page.locator(s["date_dropdown"]).click(timeout=10000)
            except Exception as e:
                self._log(f"Error opening date picker: {e}", "error")
                return CheckResult(available=False)

            while True:
                cal_date = self._parse_calendar_date()
                if cal_date:
                    self._screenshot(f"date_found_{location}")
                    self._page.keyboard.press("Escape")
                    return CheckResult(available=True, date=cal_date, location=location)

                next_btn = self._page.get_by_text(s["next_button"])
                if next_btn.count() == 0:
                    break
                next_btn.click()
                time.sleep(0.2)

            self._page.keyboard.press("Escape")
            return CheckResult(available=False)

        except Exception as e:
            self._log(f"Error checking {location}: {e}", "error")
            return CheckResult(available=False)

    def _parse_calendar_date(self) -> datetime | None:
        s = selectors.SELECTORS
        try:
            match_el = self._page.query_selector(s["match_date"])
            if not match_el:
                return None
            day = int(match_el.text_content())
            month = self._page.locator(s["calendar_month"]).first.text_content()
            year = int(self._page.locator(s["calendar_year"]).first.text_content())
            month_num = selectors.MONTH_MAP.get(month[:3].lower())
            if month_num:
                return datetime(year, month_num, day)
        except Exception:
            pass
        return None

    def reschedule_to(self, location: str) -> bool:
        s = selectors.SELECTORS
        try:
            self.current_action = "RESCHEDULING"
            self._log(f"Rescheduling at {location}")
            self._screenshot("before_reschedule")

            checkbox = self._page.locator(s["applicants_checkbox"])
            count = checkbox.count()
            if count > 1:
                for i in range(count):
                    cb = checkbox.nth(i)
                    if cb.is_checked():
                        cb.uncheck()
                self._page.get_by_text(s["continue_button"]).click()

            self._page.query_selector(s["match_date"]).click()
            time.sleep(0.5)

            options = self._page.locator(s["time_slot"]).text_content()
            option = options.strip()[:5]
            self._page.locator(s["time_slot"]).select_option(option)

            self._page.get_by_text("Reschedule").last.click()
            self._page.get_by_text("Confirm").last.click()
            time.sleep(5)

            self.current_date = self.get_current_appointment()
            addr = selectors.VISA_LOCATIONS.get(location, location)
            msg = f"Rescheduled to earlier date at {location}: {self.current_date}\nLocation: {addr}"
            self._log(msg)
            self._notify(msg)
            self._screenshot("reschedule_complete")
            self.current_action = "IDLE"
            return True

        except Exception as e:
            self._log(f"Reschedule failed: {e}", "error")
            self._screenshot("reschedule_error")
            self.current_action = "IDLE"
            return False
