import re
import os
import random
import smtplib
import time

from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from dateutil import parser
from playwright.sync_api import TimeoutError, sync_playwright

import logging
from logging.handlers import RotatingFileHandler


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
MIN_SLEEP_BEFORE_RETRY = 30  # seconds
MAX_SLEEP_BEFORE_RETRY = 60  # seconds

logger = setup_logger("my_app", "app.log")


class VisaAutomation:
    def __init__(
        self,
        username,
        password,
        appointment_id,
        appointment_url,
        notification_email=None,
        token=None,       # kept for backward compat, unused
        chat_id=None,     # kept for backward compat, unused
        browsers=1,
        check=1,
        reschedule=False,
        telegram_noti_enabled=False,  # kept for backward compat, unused
    ):
        # Playwright is intentionally NOT started here.
        # sync_playwright must be started inside the same thread that uses it
        # (the daemon thread spawned by app.py). Initialising it in __init__
        # (Flask's main thread) causes greenlet "cannot switch to a different
        # thread" errors at runtime.
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.current_date = None
        self.new_date = None
        self.is_running = False
        self.last_checked_location = None
        self.screenshots_folder = str(int(time.time()))
        Path(f"./screenshots/{self.screenshots_folder}").mkdir(
            parents=True, exist_ok=True
        )

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
            "Calgary": "615 Macleod Trail SE, Suite 1000, Calgary AB T2G 4T8",
            "Halifax": "Suite 904, Purdy's Wharf Tower II, 1969 Upper Water St, Halifax NS B3J 3R7",
            "Montreal": "1134 Saint-Catherine St. West, Montréal QC H3B 1H4",
            "Ottawa": "490 Sussex Drive, Ottawa ON K1N 1G8",
            "Quebec City": "2 rue de la Terrasse Dufferin, Québec QC G1R 4N5",
            "Toronto": "225 Simcoe Street, Toronto ON M5G 1S4",
            "Vancouver": "1075 West Pender Street, Vancouver BC V6E 2M6",
        }
        self.location_id = "#appointments_consulate_appointment_facility_id"
        self.calender_dropdown_date_selector = (
            "#appointments_consulate_appointment_date"
        )
        self.calender_id = ".ui-datepicker-title"
        self.next_button_label = "Next"
        self.appointment_date_selector = ".consular-appt"
        self.appointment_date_regex = r".*Appointment:(.*)(?:Vancouver|Toronto|Calgary|Ottawa|Halifax|Montreal|Quebec City) local time.*$"
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

    def stop(self):
        self.is_running = False

    def capture_debug_screenshot(self, name: str):
        self.debug_screenshot_counter += 1
        screenshot_name = f"{self.debug_screenshot_counter:03d}_{name}"
        self.capture_screenshot(screenshot_name)
        logger.debug(f"Captured debug screenshot: {screenshot_name}")

    def month_to_number(self, month):
        return {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }[month]

    def handle_request(self, route, request):
        route.continue_()
        response = route.response
        status = response.status
        headers = response.headers
        body = response.body()
        logger.info("Response Status: %s", status)
        logger.info("Response Headers: %s", headers)
        logger.info("Response Body: %s", body)

    def create_new_context(self):
        user_agent = random.choice(self.user_agents)
        logger.debug(f"Using User-Agent: {user_agent}")
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
            logger.debug("Attempting to log in")
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
            logger.debug("Clicked sign in button")

            if press_ok:
                self.capture_debug_screenshot("before_press_ok")
                self.page.get_by_label("OK").click()
                logger.debug("Pressed OK button")
            self.capture_debug_screenshot("logged_in")

            if continue_login:
                self.page.get_by_role(
                    "menuitem", name=self.continue_button_label
                ).click()
                logger.debug("Clicked continue button")
                self.capture_debug_screenshot("after_continue")

            logger.info("Login successful")
        except Exception as e:
            logger.error(f"Login failed: {str(e)}", exc_info=True)
            self.capture_debug_screenshot("login_error")
            time.sleep(60)
            self.login(
                username=username,
                password=password,
                continue_login=False,
                press_ok=True,
            )

    def handle_scheduling_limit_warning(self):
        """
        The site shows a 'Scheduling Limit Warning' page before the appointment
        form whenever you navigate there. It must be dismissed (tick 'I understand'
        + click Continue) or no automation is possible.

        Also extracts the remaining reschedule attempt count and:
          - Sends an email alert if attempts are running low (≤ 1).
          - Stops auto-reschedule entirely (but keeps monitoring) if 0 remain,
            so the appointment cannot be accidentally locked.

        Returns True if the warning was found and handled, False if not present.
        """
        try:
            # Short timeout — normal appointment page won't have this heading
            self.page.wait_for_selector(
                "text=Scheduling Limit Warning", timeout=3000
            )
        except TimeoutError:
            return False  # no warning page — nothing to do

        self.capture_debug_screenshot("scheduling_limit_warning")
        logger.warning("Scheduling Limit Warning detected — reading remaining attempts")

        # Extract remaining attempt count from the warning body
        remaining = None
        try:
            body_text = self.page.locator("body").text_content() or ""
            match = re.search(
                r"You have (\d+) remaining attempt", body_text, re.IGNORECASE
            )
            if match:
                remaining = int(match.group(1))
                logger.warning(f"Remaining reschedule attempts: {remaining}")
        except Exception:
            logger.warning("Could not parse remaining attempt count from warning page")

        # If auto-reschedule is enabled and 0 attempts left, disable it to
        # prevent the appointment being permanently locked.
        if remaining == 0 and self.reschedule:
            msg = (
                "CRITICAL: 0 reschedule attempts remaining.\n"
                "Auto-reschedule has been DISABLED to protect your appointment "
                "from being permanently locked. Monitoring will continue."
            )
            logger.error(msg)
            self.send_email_notification(msg)
            self.reschedule = False  # demote to monitor-only for this session

        # Low-attempt warning (still has attempts, but getting close)
        elif remaining is not None and remaining <= 1 and self.reschedule:
            msg = (
                f"WARNING: Only {remaining} reschedule attempt(s) remaining.\n"
                "Your appointment will be permanently locked if the limit is reached."
            )
            logger.warning(msg)
            self.send_email_notification(msg)

        # Dismiss: tick 'I understand', then click Continue
        try:
            self.page.locator("label", has_text="I understand").click()
            self.capture_debug_screenshot("scheduling_limit_acknowledged")
            self.page.get_by_role("button", name="Continue").click()
            self.page.wait_for_load_state("networkidle")
            self.capture_debug_screenshot("scheduling_limit_dismissed")
            logger.info("Scheduling Limit Warning dismissed — proceeding to appointment page")
        except Exception as e:
            logger.error(f"Failed to dismiss scheduling limit warning: {e}", exc_info=True)

        return True

    def navigate_to_appointments(self, appointment_id):
        try:
            logger.debug(f"Navigating to appointments page for ID: {appointment_id}")
            self.page.goto(self.appointment_link.format(appointment_id))
            self.page.wait_for_load_state("networkidle")
            self.capture_debug_screenshot("appointments_page")

            # The site intercepts navigation with a Scheduling Limit Warning page
            # when reschedule attempts are running low. Detect and dismiss it so
            # the automation can continue to the actual appointment form.
            self.handle_scheduling_limit_warning()

            logger.info("Successfully navigated to appointments page")
        except Exception as e:
            logger.error(f"Failed to navigate to appointments: {str(e)}", exc_info=True)
            self.capture_debug_screenshot("navigation_error")
            time.sleep(120)
            self.navigate_to_appointments(appointment_id)

    def check_availability(self):
        logger.debug("Checking availability")
        self.capture_debug_screenshot("before_check_availability")

        calendar_content = self.page.locator(self.calender_id).first.text_content()
        logger.debug(f"Calendar content: {calendar_content}")

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
                logger.debug(f"Found potential date: {calendar_date}")
                self.capture_debug_screenshot("date_found")

            except Exception:
                logger.error("Exception in check_availability()", exc_info=True)
                self.capture_debug_screenshot("check_availability_error")
                logger.debug("No match found, continuing checks...")
                return False, True

            if calendar_date:
                logger.info(
                    f"Date found: {calendar_date.strftime('%Y-%m-%d')}. Exiting..."
                )
                self.new_date = calendar_date
                return True, False

        logger.debug("No suitable date found")
        return False, True

    def get_appointment_date(self):
        try:
            logger.info("Getting current appointment details...")
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
            logger.info(f"Current appointment details: {appointment_datetime}")
            return appointment_datetime
        else:
            logger.warning("No appointment date information found.")
            return None

    def select_location(self, location):
        if location in self.visa_locations:
            try:
                location_selector = self.page.locator(self.location_id)
                location_selector.select_option(location)
                self.page.wait_for_load_state("networkidle")
                self.last_checked_location = location
                time.sleep(2)
            except TimeoutError:
                logger.error(f"Timeout occurred while selecting {location} location")

    def is_date_available(self, wait_time: int = 100):
        try:
            self.page.wait_for_selector(self.not_available_selector, timeout=wait_time)
            return False
        except TimeoutError:
            return True

    def run_check(self):
        availability_list = []

        for location in self.visa_locations:
            self.page.route(re.compile(self.network_request_regex), self.handle_request)
            logger.info(f"Checking availability at {location}")
            self.select_location(location)
            self.capture_debug_screenshot(f"location_{location}")

            if self.is_date_available():
                availability_list.append(True)
                logger.debug(f"Date available at {location}")

                continue_check = True
                self.page.locator(self.calender_dropdown_date_selector).click()
                # self.capture_debug_screenshot(f"calendar_dropdown_{location}")

                while continue_check:
                    result, continue_check = self.check_availability()

                    if result:
                        formatted_found_date = self.new_date.strftime("%Y-%m-%d")
                        message = (
                            f"Date available at {location} on {formatted_found_date}"
                        )
                        logger.info(message)
                        self.capture_debug_screenshot(f"date_found_{location}")

                        if self.notification_email and self.new_date and self.current_date and self.new_date < self.current_date:
                            self.send_email_notification(message)

                        if self.reschedule:
                            if self.new_date < self.current_date:
                                self.reschedule_appointment(location)

                        break

                    else:
                        self.page.get_by_text(self.next_button_label).click()
                        logger.debug("Clicked next button")
                        # self.capture_debug_screenshot(f"next_month_{location}")
                        time.sleep(0.2)

                self.page.keyboard.press("Escape")
                logger.debug("Closed calendar dropdown")

            else:
                availability_list.append(False)
                logger.info(f"No dates available at {location}")
                # self.capture_debug_screenshot(f"no_dates_{location}")

        return any(availability_list)

    def run(self):
        """
        Entry point for the daemon thread.
        All Playwright objects are created here so they share the same
        greenlet/thread context — calling sync_playwright() anywhere else
        (e.g. __init__, which runs on Flask's main thread) causes the
        'cannot switch to a different thread' greenlet error.
        """
        self.is_running = True
        # Start playwright inside this thread
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.launch(headless=True)

            for session_number in range(self.browsers):
                try:
                    self.create_new_context()
                    self.login(
                        username=self.username, password=self.password, continue_login=False
                    )
                    self.current_date = self.get_appointment_date()

                    for check_number in range(self.check):
                        if not self.is_running:
                            return
                        logger.info(f"Session {check_number}")
                        self.navigate_to_appointments(self.appointment_id)
                        availability_flag = self.run_check()

                        if availability_flag:
                            self.poll_count = 0
                        else:
                            self.poll_count += 1
                            if self.poll_count >= MAX_POLLS:
                                self.handle_soft_ban()

                        self.sleep_before_retry(check_number)

                except Exception as error:
                    self.handle_error(error)

                finally:
                    self.close_context()

            logger.info("All browser sessions completed.")

        finally:
            # Always clean up browser + playwright regardless of errors
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.is_running = False

    def send_email_notification(self, message):
        if not self.notification_email:
            logger.warning("No notification_email set — skipping notification")
            return

        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")

        if not smtp_user or not smtp_password:
            logger.warning("SMTP_USER / SMTP_PASSWORD not set — skipping email")
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = f"Visa Monitor <{smtp_user}>"
            msg["To"] = self.notification_email
            msg["Subject"] = "[VISA MONITOR] Appointment Update"
            msg.attach(MIMEText(message, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info(f"Email notification sent to {self.notification_email}")
        except Exception as e:
            logger.error(f"Email notification failed: {e}", exc_info=True)

    def reschedule_appointment(self, location):
        try:
            logger.debug(f"Attempting to reschedule appointment at {location}")
            self.capture_debug_screenshot("before_reschedule")

            self.page.query_selector(self.match_id).click()
            logger.debug("Selected new date")
            self.capture_debug_screenshot("date_selected")
            time.sleep(0.5)

            options = self.page.locator(self.time_appointment_selector).text_content()
            option = options.strip()[:5]
            self.page.locator(self.time_appointment_selector).select_option(option)
            logger.debug(f"Selected time slot: {option}")
            self.capture_debug_screenshot("time_selected")

            self.page.get_by_text("Reschedule").last.click()
            logger.debug("Clicked Reschedule button")
            self.capture_debug_screenshot("reschedule_clicked")

            self.page.get_by_text("Confirm").last.click()
            logger.debug("Clicked Confirm button")
            self.capture_debug_screenshot("confirm_clicked")

            time.sleep(5)

            self.current_date = self.get_appointment_date()
            logger.info(f"New appointment date: {self.current_date}")

            location_address = self.visa_locations.get(location, "Unknown Location")
            message = (
                f"Rescheduled to an earlier appointment!\n\n"
                f"Location: {location}\n"
                f"Address: {location_address}\n"
                f"New Date: {self.current_date}"
            )
            logger.info(message)
            self.send_email_notification(message)
            self.capture_debug_screenshot("reschedule_complete")

        except Exception as e:
            message = f"Error while booking new date for {location}"
            logger.error(message, exc_info=True)
            self.capture_debug_screenshot("reschedule_error")

    def handle_soft_ban(self):
        logger.info("Sleeping for 10 mins due to soft ban")
        time.sleep(600)
        self.poll_count = 0

    def sleep_before_retry(self, check_number):
        min_sleep = (check_number // 5) * MIN_SLEEP_BEFORE_RETRY
        max_sleep = min_sleep + MAX_SLEEP_BEFORE_RETRY
        sleep_time = random.randint(min_sleep, max_sleep)
        logger.info(f"Sleeping for {sleep_time} seconds before next check")
        time.sleep(sleep_time)

    def handle_error(self, error):
        logger.error("Error occurred while checking:", exc_info=True)
        logger.info("Sleeping for 5 mins due to error")
        time.sleep(300)

    def handle_confirm_page_befor_navigate_to_appointment(self):
        try:
            self.page.locator(
                'input[type="submit"][name="commit"][value="Continue"]'
            ).click()
        except Exception:
            self.navigate_to_appointments(self.appointment_id)


if __name__ == "__main__":
    try:
        from creds import (
            user, password, appointment_id, appointment_url,
            TOKEN, chat_id, browsers, check, reschedule,
            telegram_noti_enabled,
        )
    except ImportError:
        raise SystemExit("creds.py not found. Copy creds.py.example and fill in your values.")

    logger.info("Script started")

    visa_automation = VisaAutomation(
        username=user,
        password=password,
        appointment_id=appointment_id,
        appointment_url=appointment_url,
        browsers=browsers,
        check=check,
        reschedule=reschedule,
    )
    visa_automation.run()
