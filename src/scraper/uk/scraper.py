from __future__ import annotations

from datetime import datetime

from src.scraper.base import CheckResult, VisaScraper
from src.scraper.uk import selectors


class UKVisaScraper(VisaScraper):
    def get_login_url(self) -> str:
        return selectors.LOGIN_URL

    def get_selectors(self) -> dict[str, str]:
        return selectors.SELECTORS

    def get_visa_locations(self) -> dict[str, str]:
        return selectors.VISA_LOCATIONS

    def login(self) -> bool:
        s = selectors.SELECTORS
        try:
            self._log("Attempting UK login")
            self.current_action = "LOGIN"
            self._navigate(selectors.LOGIN_URL)
            self._screenshot("login_page")

            self._page.get_by_label(s["username"]).fill(self.username)
            self._page.get_by_label(s["password"]).fill(self.password)
            self._page.locator("label").filter(has_text=s["terms_label"]).click()
            self._page.get_by_role("button", name=s["sign_in_button"]).click()

            self._log("UK login successful")
            self._screenshot("login_success")
            self.current_action = "IDLE"
            return True
        except Exception as e:
            self._log(f"UK login failed: {e}", "error")
            self._screenshot("login_error")
            return False

    def get_current_appointment(self) -> datetime | None:
        try:
            date_text = self._page.locator(selectors.SELECTORS["appointment_date"]).text_content()
            return datetime.strptime(date_text.strip(), "%B %d, %Y")
        except Exception:
            self._log("Could not parse current UK appointment", "warning")
            return None

    def check_availability(self, location: str) -> CheckResult:
        self._log(f"UK check_availability stub for {location}")
        return CheckResult(available=False)

    def reschedule_to(self, location: str) -> bool:
        self._log(f"UK reschedule stub for {location}")
        return False
