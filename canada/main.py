import re
import random
import time
import os

from datetime import datetime
from pathlib import Path
from dateutil import parser
from playwright.sync_api import TimeoutError, sync_playwright
import logging
from logging.handlers import RotatingFileHandler

from canada import config
from canada import notifications
from canada import state

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_BASE = os.path.join(MODULE_DIR, "screenshots")

def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def run_in_subprocess(user_id, username, password, appointment_id, appointment_url,
                      notification_email=None, browsers=1, check=12, reschedule=False,
                      telegram_chat_id=None, send_telegram=False,
                      phone_number=None, send_sms=False,
                      preferred_locations=None):
    """Entry point for multiprocessing — runs Playwright in separate process."""
    logger = setup_logger("canada_app", "app.log")
    instance = VisaAutomation(
        username=username,
        password=password,
        appointment_id=appointment_id,
        appointment_url=appointment_url,
        notification_email=notification_email,
        browsers=browsers,
        check=check,
        reschedule=reschedule,
        telegram_chat_id=telegram_chat_id,
        send_telegram=send_telegram,
        phone_number=phone_number,
        send_sms=send_sms,
        logger=logger,
        user_id=user_id,
        preferred_locations=preferred_locations,
    )
    instance.run()

class VisaAutomation:
    def __init__(
        self,
        username,
        password,
        appointment_id,
        appointment_url,
        notification_email=None,
        browsers=1,
        check=12,
        reschedule=False,
        telegram_chat_id=None,
        send_telegram=False,
        phone_number=None,
        send_sms=False,
        logger=None,
        user_id=None,
        preferred_locations=None,
    ):
        self._logger = logger
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        folder_suffix = str(int(time.time()))
        if user_id:
            folder_suffix = f"{user_id}_{folder_suffix}"
        self.screenshots_folder = folder_suffix
        Path(SCREENSHOTS_BASE, self.screenshots_folder).mkdir(
            parents=True, exist_ok=True
        )
        self.context = None
        self.page = None
        self.current_date = None
        self.new_date = None
        self.is_running = False
        self.last_checked_location = None
        self.action_log = []
        self.current_action = ""
        self.appointments_page_screenshot = None
        self.user_id = user_id
        self.username = username
        self.password = password
        self.appointment_id = appointment_id
        self.appointment_url = appointment_url
        self.notification_email = notification_email
        self.browsers = browsers
        self.check = check
        self.reschedule = reschedule
        self.telegram_chat_id = telegram_chat_id
        self.send_telegram = send_telegram
        self.phone_number = phone_number
        self.send_sms = send_sms

        self.login_url = config.LOGIN_URL
        self.s = config.SELECTORS
        self.visa_locations = config.VISA_LOCATIONS
        self.appointment_date_regex = config.APPOINTMENT_DATE_REGEX
        self.network_request_regex = config.NETWORK_REQUEST_REGEX
        self.json_response_base_link = appointment_url.format(appointment_id)
        self.poll_count = 0
        self.debug_screenshot_counter = 0
        self.user_agents = config.USER_AGENTS
        self.preferred_locations = preferred_locations

    def _log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"ts": ts, "msg": msg}
        self.action_log.append(entry)
        if len(self.action_log) > config.MAX_ACTION_LOG_ENTRIES:
            self.action_log = self.action_log[-config.MAX_ACTION_LOG_ENTRIES:]
        if self.user_id:
            state.save_state(self.user_id, self)
        if self._logger:
            getattr(self._logger, level)(msg)
        else:
            print(f"[{level.upper()}] {msg}")

    def capture_debug_screenshot(self, name: str):
        self.debug_screenshot_counter += 1
        screenshot_name = f"{self.debug_screenshot_counter:03d}_{name}"
        self.capture_screenshot(screenshot_name)
        if name == "appointments_page":
            self.appointments_page_screenshot = str(
                Path(SCREENSHOTS_BASE, self.screenshots_folder, f"{screenshot_name}.png")
            )
        if self.user_id:
            state.save_state(self.user_id, self)

    def month_to_number(self, month):
        return config.MONTH_MAP[month.lower()]

    def handle_request(self, route, request):
        route.continue_()
        response = route.response
        self._log(f"Response Status: {response.status}", "debug")
        self._log(f"Response Headers: {response.headers}", "debug")
        self._log(f"Response Body: {response.body()}", "debug")

    def create_new_context(self):
        user_agent = random.choice(self.user_agents)
        self._log(f"Using User-Agent: {user_agent}", "debug")
        self.context = self.browser.new_context(user_agent=user_agent)
        self.page = self.context.new_page()

    def close_context(self):
        if self.context:
            self.context.close()

    def close_browser(self):
        self.browser.close()

    def go_to_page(self, page):
        self.page.goto(page)

    def capture_screenshot(self, name: str = "image"):
        self.page.screenshot(path=str(Path(SCREENSHOTS_BASE, self.screenshots_folder, f"{name}.png")))

    def login(self, username, password, continue_login=True, press_ok=False):
        try:
            self._log("Attempting to log in")
            self.current_action = "LOGIN"
            self.go_to_page(self.login_url)
            self._log_url("login_page_loaded")
            self.capture_debug_screenshot("login_page")

            self.page.get_by_label(self.s["username"]).fill(username)
            self.page.get_by_label(self.s["password"]).fill(password)

            self.page.locator("label").filter(
                has_text=self.s["terms_label"]
            ).click()

            self.page.get_by_role("button", name=self.s["sign_in_button"]).click()
            self._log("Clicked sign in button", "debug")

            if press_ok:
                self.page.get_by_label("OK").click()
                self._log("Pressed OK button", "debug")

            if continue_login:
                self.page.get_by_role(
                    "menuitem", name=self.s["continue_button"]
                ).click()
                self._log("Clicked continue button", "debug")

            self._log_url("after_login")
            self._log("Login successful")
            self.current_action = "IDLE"

        except Exception as e:
            self._log(f"Login failed: {str(e)}", "error")
            self.capture_debug_screenshot("login_error")
            time.sleep(60)
            self.login(
                username=username,
                password=password,
                continue_login=False,
                press_ok=True,
            )

    def navigate_to_appointments(self, appointment_id, _retries=0):
        try:
            self.current_action = "NAVIGATE"
            self._log(f"Navigating to appointments page for ID: {appointment_id}")
            self.page.goto(self.appointment_url.format(appointment_id))
            self.page.wait_for_load_state("networkidle")
            self._log_url("after_goto_appointments")

            consent = self.page.locator('label:has-text("I confirm that I have read")')
            if consent.count() > 0:
                self._log("Found consent checkbox, clicking to confirm...")
                consent.click()
                time.sleep(0.5)
                self.page.get_by_role("button", name="Continue").click()
                self.page.wait_for_load_state("networkidle")
                self._log("Confirmed consent and continued")
                self._log_url("after_consent")

            understand = self.page.locator('label:has-text("I understand")')
            if understand.count() > 0:
                self._log("Found 'I understand' checkbox, clicking...")
                understand.click()
                time.sleep(0.5)
                continue_btn = self.page.get_by_text("Continue").first
                if continue_btn.count() > 0:
                    continue_btn.click()
                    self.page.wait_for_load_state("networkidle")
                    self._log("Clicked Continue after 'I understand'")
                    self._log_url("after_understand")
                self.capture_debug_screenshot("understand_checked")

            limit = self.page.locator("#confirmed_limit_message")
            if limit.count() > 0:
                self._log("Found limit confirmation checkbox, clicking...")
                limit.check()
                time.sleep(0.5)
                self.capture_debug_screenshot("limit_checked")
                continue_btn = self.page.get_by_text("Continue").first
                if continue_btn.count() > 0:
                    continue_btn.click()
                    self.page.wait_for_load_state("networkidle")
                    self._log("Clicked Continue after limit confirmation")
                    self._log_url("after_limit_confirmation")

            # Handle multi-applicant selection page
            applicant_checkboxes = self.page.locator(self.s["applicants_checkbox"])
            if applicant_checkboxes.count() > 0:
                count = applicant_checkboxes.count()
                self._log(f"Applicant selection page detected ({count} applicant(s)) — checking all")
                for i in range(count):
                    cb = applicant_checkboxes.nth(i)
                    if not cb.is_checked():
                        cb.check()
                        self._log(f"Checked applicant #{i+1}")
                time.sleep(0.5)
                continue_btn = self.page.get_by_text("Continue").first
                if continue_btn.count() > 0:
                    continue_btn.click()
                    self.page.wait_for_load_state("networkidle")
                    self._log("Clicked Continue after applicant selection")
                    self._log_url("after_applicant_selection")
                self.capture_debug_screenshot("after_applicant_selection")

            self.capture_debug_screenshot("appointments_page")
            self._log_url("appointments_page_final")
            self._log("Successfully navigated to appointments page")
            self.current_action = "CHECKING"
        except Exception as e:
            self._log(f"Failed to navigate to appointments: {str(e)}", "error")
            self.capture_debug_screenshot("navigation_error")
            if _retries >= config.NAVIGATE_MAX_RETRIES:
                self._log(f"Navigation failed after {_retries} retries — giving up", "error")
                self.current_action = "IDLE"
                raise
            next_retry = _retries + 1
            self._log(f"Retrying navigation ({next_retry}/{config.NAVIGATE_MAX_RETRIES}) in 120s")
            time.sleep(120)
            self.navigate_to_appointments(appointment_id, _retries=next_retry)

    def check_availability(self):
        self._log("Checking availability")

        calendar_content = self.page.locator(self.s["calendar_title"]).first.text_content()
        self._log(f"Calendar content: {calendar_content}", "debug")

        match_element = self.page.query_selector(self.s["match_date"])
        calendar_date = None

        if match_element:
            try:
                day = int(match_element.text_content())
                month = self.page.locator(
                    self.s["calendar_month"]
                ).first.text_content()
                month_number = self.month_to_number(month[:3].lower())
                year = int(
                    self.page.locator(self.s["calendar_year"]).first.text_content()
                )
                calendar_date = datetime(year, month_number, day)
                self._log(f"Found potential date: {calendar_date}", "debug")
            except Exception:
                self._log("Exception in check_availability()", "error")
                self._log("No match found, continuing checks...", "debug")
                return False, True

            if calendar_date:
                self._log(
                    f"Date found: {calendar_date.strftime('%Y-%m-%d')}. Exiting..."
                )
                self.new_date = calendar_date
                return True, False

        self._log("No suitable date found", "debug")
        return False, True

    def get_appointment_date(self):
        try:
            self._log("Getting current appointment details...")
            date_text = self.page.locator(self.s["appointment_date"]).text_content()
        except Exception as e:
            e_strings = str(e).split("get_by_text")
            start_index = e_strings[1].index("(")
            end_index = e_strings[1].index(")")
            date_text = e_strings[1][start_index + 1: end_index]

        date_text = date_text.replace("\n", "")
        matches = re.search(self.appointment_date_regex, date_text)

        if matches:
            date_text = matches.group(1).strip()
            appointment_details = parser.parse(date_text)
            formatted_appointment_date = appointment_details.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            appointment_datetime = datetime.strptime(
                formatted_appointment_date, "%Y-%m-%d %H:%M:%S"
            )
            self._log(f"Current appointment details: {appointment_datetime}")
            return appointment_datetime
        else:
            self._log("No appointment date information found.", "warning")
            return None

    def select_location(self, location):
        if location not in self.visa_locations:
            return
        try:
            self._log(f"Selecting location: {location}")

            loc = self.page.locator(self.s["location"])
            found = loc.count() > 0

            if not found:
                self._log(f"Primary selector '{self.s['location']}' not found — searching for alternatives", "warn")
                self.capture_debug_screenshot(f"location_selector_missing_{location}")
                selects = self.page.eval_on_selector_all("select",
                    "els => els.map(e => e.id + '|' + e.name + '|' + e.className)")
                self._log(f"Available <select> elements: {selects}", "debug")
                if selects:
                    first_id = selects[0].split("|")[0]
                    if first_id:
                        loc = self.page.locator(f"#{first_id}")
                        found = loc.count() > 0
                        if found:
                            self._log(f"Fell back to selector: #{first_id}")

            if not found:
                self._log(f"No location <select> found on page — cannot select {location}", "error")
                return

            current = loc.evaluate("el => el.value")
            self._log(f"Current location: {current}", "debug")

            loc.select_option(location)
            self.page.wait_for_load_state("networkidle")
            time.sleep(0.5)

            self._log(f"Selected {location}")
        except Exception as e:
            self._log(f"Error selecting {location}: {str(e)}", "error")
            self.capture_debug_screenshot(f"location_error_{location}")

    def is_date_available(self, wait_time: int = 100):
        try:
            self.page.wait_for_selector(self.s["not_available"], timeout=wait_time)
            return False
        except TimeoutError:
            return True

    def run_check(self):
        availability_list = []

        locations_to_check = self.visa_locations
        if self.preferred_locations:
            locations_to_check = {k: v for k, v in self.visa_locations.items()
                                  if k in self.preferred_locations}
            self._log(f"Filtered to {len(locations_to_check)} preferred locations: {list(locations_to_check.keys())}")

        for location in locations_to_check:
            self.last_checked_location = location
            self.page.route(re.compile(self.network_request_regex), self.handle_request)
            self._log(f"Checking availability at {location}")
            self.capture_debug_screenshot(f"before_location_{location}")
            self.select_location(location)
            self._log_url(f"after_select_location_{location}")

            if self.is_date_available():
                availability_list.append(True)
                self._log(f"Date available at {location}", "debug")

                self._log(f"Attempting to select date at {location}")
                self.capture_debug_screenshot(f"before_date_select_{location}")

                try:
                    self.page.wait_for_selector(self.s["date_dropdown"], timeout=5000)
                    self.page.locator(self.s["date_dropdown"]).click(timeout=10000)
                except Exception as e:
                    self._log(f"Error clicking date dropdown: {str(e)}", "error")
                    self.capture_debug_screenshot(f"error_date_select_{location}")
                    self.page.keyboard.press("Escape")
                    continue

                continue_check = True
                while continue_check:
                    result, continue_check = self.check_availability()

                    if result:
                        formatted_found_date = self.new_date.strftime("%Y-%m-%d")
                        message = (
                            f"Date available at {location} on {formatted_found_date}"
                        )
                        self._log(message)
                        self.capture_debug_screenshot(f"date_found_{location}")

                        if (
                            self.notification_email
                            and self.new_date
                            and self.current_date
                        ):
                            if self.new_date < self.current_date:
                                self._log(f"Earlier date found at {location}!")
                                msg = f"Earlier date found at {location}: {self.new_date.strftime('%Y-%m-%d')}"
                                self._send_notifications(msg)

                        if self.reschedule:
                            if self.new_date and self.current_date:
                                if self.new_date < self.current_date:
                                    self.reschedule_appointment(location)

                        break

                    else:
                        self.page.get_by_text(self.s["next_button"]).click()
                        self._log("Clicked next button", "debug")
                        self._log_url("after_calendar_next")
                        time.sleep(0.2)

                self.page.keyboard.press("Escape")
                self._log("Closed calendar dropdown", "debug")

            else:
                availability_list.append(False)
                self._log(f"No dates available at {location}")

        return any(availability_list)

    def run(self):
        self.is_running = True
        if self.user_id:
            state.save_state(self.user_id, self)
        self._log("Starting automation")

        start_msg = "Visa Automation started — monitoring for earlier dates..."
        self._send_notifications(start_msg)

        try:
            while self.is_running:
                for session_number in range(self.browsers):
                    if not self.is_running:
                        break

                    try:
                        self.create_new_context()
                        self.login(
                            username=self.username, password=self.password, continue_login=False
                        )
                        self.current_date = self.get_appointment_date()

                        for check_number in range(self.check):
                            if not self.is_running:
                                return
                            self._log(f"Session {check_number + 1}/{self.check}")
                            self.navigate_to_appointments(self.appointment_id)
                            availability_flag = self.run_check()

                            if availability_flag:
                                self.poll_count = 0
                            else:
                                self.poll_count += 1
                                if self.poll_count >= config.MAX_POLLS:
                                    self.handle_soft_ban()

                            if check_number < self.check - 1:
                                self.sleep_before_retry(check_number)

                    except Exception as error:
                        self.handle_error(error)

                    finally:
                        self.close_context()

                        if session_number == self.browsers - 1:
                            self._log("All browser sessions completed.")

                if self.is_running:
                    wait_time = random.randint(
                        config.MIN_WAIT_BETWEEN_CHECKS, config.MAX_WAIT_BETWEEN_CHECKS
                    )
                    self._log(f"Waiting {wait_time}s before next check cycle")
                    time.sleep(wait_time)

        finally:
            self.is_running = False
            self.close_browser()
            self._log("Automation stopped")

    def _send_notifications(self, message):
        if self.notification_email:
            notifications.send_email(
                subject=f"VISA UPDATE: {message[:50]}...",
                message=message,
                to_email=self.notification_email,
                logger=lambda msg, lvl="info": self._log(msg, lvl),
            )
        if self.send_telegram:
            notifications.send_telegram(
                message=message,
                chat_id=self.telegram_chat_id,
                logger=lambda msg, lvl="info": self._log(msg, lvl),
            )
        if self.send_sms and self.phone_number:
            notifications.send_sms(
                message=message,
                to_phone=self.phone_number,
                logger=lambda msg, lvl="info": self._log(msg, lvl),
            )

    def reschedule_appointment(self, location):
        try:
            self.current_action = "RESCHEDULING"
            self._log(f"Attempting to reschedule appointment at {location}")
            self._log_url("before_reschedule")
            self.capture_debug_screenshot("before_reschedule")

            # Handle multiple applicants: uncheck all by default
            applicant_checkboxes = self.page.locator(self.s["applicants_checkbox"])
            applicant_count = applicant_checkboxes.count()
            if applicant_count > 1:
                self._log(f"Multiple applicants detected ({applicant_count}) — unchecking all by default")
                for i in range(applicant_count):
                    checkbox = applicant_checkboxes.nth(i)
                    if checkbox.is_checked():
                        checkbox.uncheck()
                        self._log(f"Unchecked applicant #{i+1}")
                self.page.get_by_text(self.s["continue_button"]).click()
                self._log("Clicked Continue after applicant selection")

            self.page.query_selector(self.s["match_date"]).click()
            self._log("Selected new date")
            time.sleep(0.5)

            options = self.page.locator(self.s["time_slot"]).text_content()
            option = options.strip()[:5]
            self.page.locator(self.s["time_slot"]).select_option(option)
            self._log(f"Selected time slot: {option}")

            self.page.get_by_text("Reschedule").last.click()
            self._log("Clicked Reschedule button")
            self._log_url("after_reschedule_click")

            self.page.get_by_text("Confirm").last.click()
            self._log("Clicked Confirm button")
            self._log_url("after_confirm_reschedule")

            time.sleep(5)

            self.current_date = self.get_appointment_date()
            self._log(f"New appointment date: {self.current_date}")

            location_address = self.visa_locations.get(location, "Unknown Location")
            message = f"Rescheduled to a new earlier appointment date at {location}: \nDate: {self.current_date}\nLocation: {location_address}"
            self._log(message)
            self._send_notifications(message)
            self.capture_debug_screenshot("reschedule_complete")
            self.current_action = "IDLE"

        except Exception:
            message = f"Error while booking new date for {location}"
            self._log(message, "error")
            self.capture_debug_screenshot("reschedule_error")
            self.current_action = "IDLE"

    def handle_soft_ban(self):
        self._log("Sleeping for 10 mins due to soft ban")
        time.sleep(600)
        self.poll_count = 0

    def sleep_before_retry(self, check_number):
        min_sleep = (check_number // 5) * config.MIN_SLEEP_BEFORE_RETRY
        max_sleep = min_sleep + config.MAX_SLEEP_BEFORE_RETRY
        sleep_time = random.randint(min_sleep, max_sleep)
        self._log(f"Sleeping for {sleep_time} seconds before next check")
        time.sleep(sleep_time)

    def handle_error(self, error):
        self._log(f"Error occurred while checking: {error}", "error")
        self._log("Sleeping for 5 mins due to error")
        time.sleep(300)

    def stop(self):
        self.is_running = False
        self._log("Stop requested")

if __name__ == "__main__":
    from creds import user, password, appointment_id, appointment_url, check, reschedule

    logger = setup_logger("canada_app", "app.log")
    logger.info("Canada automation script started")
    visa_automation = VisaAutomation(
        username=user,
        password=password,
        appointment_id=appointment_id,
        appointment_url=appointment_url,
        browsers=1,
        check=check,
        reschedule=reschedule,
    )
    visa_automation.run()
