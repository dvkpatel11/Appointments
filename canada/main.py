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
import resend
import requests


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


MAX_POLLS = 30
MIN_SLEEP_BEFORE_RETRY = 30
MAX_SLEEP_BEFORE_RETRY = 60

logger = setup_logger("canada_app", "canada/app.log")


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
    ):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.screenshots_folder = str(int(time.time()))
        Path(f"./screenshots/{self.screenshots_folder}").mkdir(
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

        self.username = username
        self.password = password
        self.appointment_id = appointment_id
        self.appointment_url = appointment_url
        self.notification_email = notification_email
        self.browsers = browsers
        self.check = check
        self.reschedule = reschedule

        self.login_url = "https://ais.usvisa-info.com/en-ca/niv/users/sign_in"
        self.username_input_id = "Email"
        self.password_input_id = "Password"
        self.terms_checkbox_label = (
            "I have read and understood the Privacy Policy and the Terms of Use"
        )
        self.sign_in_button_label = "Sign In"
        self.appointment_link = (
            appointment_url
            if appointment_url
            else "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"
        )
        self.continue_button_label = "Continue"
        self.not_available_selector = "#consulate_date_time_not_available"
        self.visa_locations = {
            "Toronto": "Consular Address \
                            225 Simcoe Street \
                            Toronto, ON, Ontario, M5G 1S4 \
                            Canada",
            "Vancouver": "Consular Address \
                            1075 West Pender Street \
                            Vancouver, BC, V6E 2M6 \
                            Canada",
            "Calgary": "Consular Address \
                            615 Macleod Trail, SE \
                            Suite 1000 \
                            Calgary, AB, T2G 4T8 \
                            Canada",
            "Ottawa": "Consular Address \
                            490 Sussex Drive \
                            Ottawa, ON, Ontario, K1N 1G8 \
                            Canada",
            "Halifax": "Consular Address \
                            Suite 904, Purdy's Wharf Tower II \
                            1969 Upper Water Street \
                            Halifax, NS, Nova Scotia, B3J 3R7 \
                            Canada",
            "Montreal": "Consular Address \
                            1134 Saint-Catherine St. West \
                            Montréal, QC, Québec, H3B 1H4 \
                            Canada",
        }
        self.location_id = "#appointments_consulate_appointment_facility_id"
        self.calender_dropdown_date_selector = (
            "#appointments_consulate_appointment_date"
        )
        self.calender_id = ".ui-datepicker-title"
        self.next_button_label = "Next"
        self.appointment_date_selector = ".consular-appt"
        self.appointment_date_regex = r".*Appointment:(.*)(?:Vancouver|Toronto|Calgary|Ottawa|Halifax|Montreal) local time.*$"
        self.calender_month_selector = ".ui-datepicker-month"
        self.calender_year_selector = ".ui-datepicker-year"
        self.time_appointment_selector = "#appointments_consulate_appointment_time"
        self.network_request_regex = r"^[0-9]{2}\.json\?appointments\[expedite\]=false$"
        self.match_id = ".ui-datepicker-group-first  td.undefined > a.ui-state-default"
        self.json_response_base_link = appointment_url.format(appointment_id)
        self.poll_count = 0
        self.debug_screenshot_counter = 0
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
        ]

    def _log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"ts": ts, "msg": msg}
        self.action_log.append(entry)
        if len(self.action_log) > 100:
            self.action_log = self.action_log[-100:]
        getattr(logger, level)(msg)

    def capture_debug_screenshot(self, name: str):
        self.debug_screenshot_counter += 1
        screenshot_name = f"{self.debug_screenshot_counter:03d}_{name}"
        self.capture_screenshot(screenshot_name)
        self._log(f"Captured debug screenshot: {screenshot_name}", "debug")

    def month_to_number(self, month):
        return {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }[month.lower()]

    def handle_request(self, route, request):
        route.continue_()
        response = route.response
        status = response.status
        headers = response.headers
        body = response.body()
        self._log(f"Response Status: {status}", "debug")
        self._log(f"Response Headers: {headers}", "debug")
        self._log(f"Response Body: {body}", "debug")

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
        self.page.screenshot(path=f"./screenshots/{self.screenshots_folder}/{name}.png")

    def login(self, username, password, continue_login=True, press_ok=False):
        try:
            self._log("Attempting to log in")
            self.current_action = "LOGIN"
            self.go_to_page(self.login_url)
            self.capture_debug_screenshot("login_page")

            self.page.get_by_label(self.username_input_id).fill(username)
            self.page.get_by_label(self.password_input_id).fill(password)
            self.capture_debug_screenshot("credentials_filled")

            self.page.locator("label").filter(
                has_text=self.terms_checkbox_label
            ).click()
            self.capture_debug_screenshot("terms_checked")

            self.page.get_by_role("button", name=self.sign_in_button_label).click()
            self._log("Clicked sign in button", "debug")

            if press_ok:
                self.capture_debug_screenshot("before_press_ok")
                self.page.get_by_label("OK").click()
                self._log("Pressed OK button", "debug")
            self.capture_debug_screenshot("logged_in")

            if continue_login:
                self.page.get_by_role(
                    "menuitem", name=self.continue_button_label
                ).click()
                self._log("Clicked continue button", "debug")
                self.capture_debug_screenshot("after_continue")

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

    def navigate_to_appointments(self, appointment_id):
        try:
            self.current_action = "NAVIGATE"
            self._log(f"Navigating to appointments page for ID: {appointment_id}")
            self.page.goto(self.appointment_link.format(appointment_id))
            self.page.wait_for_load_state("networkidle")
            self.capture_debug_screenshot("appointments_page")
            self._log("Successfully navigated to appointments page")
            self.current_action = "CHECKING"
        except Exception as e:
            self._log(f"Failed to navigate to appointments: {str(e)}", "error")
            self.capture_debug_screenshot("navigation_error")
            time.sleep(120)
            self.navigate_to_appointments(appointment_id)

    def check_availability(self):
        self._log("Checking availability")
        self.capture_debug_screenshot("before_check_availability")

        calendar_content = self.page.locator(self.calender_id).first.text_content()
        self._log(f"Calendar content: {calendar_content}", "debug")

        match_element = self.page.query_selector(self.match_id)
        calendar_date = None

        if match_element:
            try:
                day = int(match_element.text_content())
                month = self.page.locator(
                    self.calender_month_selector
                ).first.text_content()
                month_number = self.month_to_number(month[:3].lower())
                year = int(
                    self.page.locator(self.calender_year_selector).first.text_content()
                )
                calendar_date = datetime(year, month_number, day)
                self._log(f"Found potential date: {calendar_date}", "debug")
                self.capture_debug_screenshot("date_found")

            except Exception:
                self._log("Exception in check_availability()", "error")
                self.capture_debug_screenshot("check_availability_error")
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
            date_text = self.page.locator(self.appointment_date_selector).text_content()
        except Exception as e:
            e_strings = str(e).split("get_by_text")
            start_index = e_strings[1].index("(")
            end_index = e_strings[1].index(")")
            date_text = e_strings[1][start_index + 1 : end_index]

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
        if location in self.visa_locations:
            try:
                location_selector = self.page.locator(self.location_id)
                location_selector.select_option(location)
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)

            except TimeoutError:
                self._log(
                    f"Timeout occurred while selecting {location} location", "error"
                )

    def is_date_available(self, wait_time: int = 100):
        try:
            self.page.wait_for_selector(self.not_available_selector, timeout=wait_time)
            return False
        except TimeoutError:
            return True

    def run_check(self):
        availability_list = []

        for location in self.visa_locations:
            self.last_checked_location = location
            self.page.route(re.compile(self.network_request_regex), self.handle_request)
            self._log(f"Checking availability at {location}")
            self.select_location(location)
            self.capture_debug_screenshot(f"location_{location}")

            if self.is_date_available():
                availability_list.append(True)
                self._log(f"Date available at {location}", "debug")

                continue_check = True
                self.page.locator(self.calender_dropdown_date_selector).click()
                self.capture_debug_screenshot(f"calendar_dropdown_{location}")

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
                                if self.notification_email:
                                    self.send_email_notification(msg)
                                self.send_telegram_notification(msg)

                        if self.reschedule:
                            if self.new_date and self.current_date:
                                if self.new_date < self.current_date:
                                    self.reschedule_appointment(location)

                        break

                    else:
                        self.page.get_by_text(self.next_button_label).click()
                        self._log("Clicked next button", "debug")
                        self.capture_debug_screenshot(f"next_month_{location}")
                        time.sleep(0.2)

                self.page.keyboard.press("Escape")
                self._log("Closed calendar dropdown", "debug")

            else:
                availability_list.append(False)
                self._log(f"No dates available at {location}")
                self.capture_debug_screenshot(f"no_dates_{location}")

        return any(availability_list)

    def run(self):
        self.is_running = True
        self._log("Starting automation")

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
                        if self.poll_count >= MAX_POLLS:
                            self.handle_soft_ban()

                    if check_number < self.check - 1:
                        self.sleep_before_retry(check_number)

            except Exception as error:
                self.handle_error(error)

            finally:
                self.close_context()

                if session_number == self.browsers - 1:
                    self._log("All browser sessions completed.")
                    self.close_browser()

        self.is_running = False
        self._log("Automation stopped")

    def send_email_notification(self, message):
        if not self.notification_email:
            return

        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            self._log("RESEND_API_KEY not set, skipping email", "warning")
            return

        try:
            resend.api_key = api_key
            resend.Emails.send({
                "from": "Visa Alerts <onboarding@resend.dev>",
                "to": [self.notification_email],
                "subject": f"VISA UPDATE: {message[:50]}...",
                "text": message,
            })
            self._log(f"Email sent to {self.notification_email}")
        except Exception:
            self._log("Email send failed", "error")

    def send_telegram_notification(self, message):
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            self._log("Telegram not configured, skipping", "debug")
            return

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": f"🇨🇦 {message}"}

        try:
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                self._log("Telegram notification sent")
            else:
                self._log(f"Telegram failed: {response.status_code}", "warning")
        except Exception:
            self._log("Telegram error", "error")

    def reschedule_appointment(self, location):
        try:
            self.current_action = "RESCHEDULING"
            self._log(f"Attempting to reschedule appointment at {location}")
            self.capture_debug_screenshot("before_reschedule")

            self.page.query_selector(self.match_id).click()
            self._log("Selected new date")
            self.capture_debug_screenshot("date_selected")
            time.sleep(0.5)

            options = self.page.locator(self.time_appointment_selector).text_content()
            option = options.strip()[:5]
            self.page.locator(self.time_appointment_selector).select_option(option)
            self._log(f"Selected time slot: {option}")
            self.capture_debug_screenshot("time_selected")

            self.page.get_by_text("Reschedule").last.click()
            self._log("Clicked Reschedule button")
            self.capture_debug_screenshot("reschedule_clicked")

            self.page.get_by_text("Confirm").last.click()
            self._log("Clicked Confirm button")
            self.capture_debug_screenshot("confirm_clicked")

            time.sleep(5)

            self.current_date = self.get_appointment_date()
            self._log(f"New appointment date: {self.current_date}")

            location_address = self.visa_locations.get(location, "Unknown Location")
            message = f"Rescheduled to a new earlier appointment date at {location}: \nDate: {self.current_date}\nLocation: {location_address}"
            self._log(message)
            self.send_email_notification(message)
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
        min_sleep = (check_number // 5) * MIN_SLEEP_BEFORE_RETRY
        max_sleep = min_sleep + MAX_SLEEP_BEFORE_RETRY
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
