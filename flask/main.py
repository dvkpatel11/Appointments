import re
import random
import time
import requests

from datetime import datetime, timedelta
from pathlib import Path
from dateutil import parser
from playwright.sync_api import TimeoutError, sync_playwright

# from creds import *
import logging
from logging.handlers import RotatingFileHandler


# Configure the logger
def setup_logger(name, log_file, level=logging.INFO):
    """Function to set up a logger with file rotation"""

    # Create a formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create a handler that writes log messages to a file, with a maximum file size of 5MB,
    # keeping 3 backup copies of the log files
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)

    # Create a handler that writes log messages to the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Create a logger object
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Add both handlers to the logger
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
        token,
        chat_id,
        browsers=1,
        check=1,
        reschedule=False,
        send_telegram_notification=False,
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

        self.username = username
        self.password = password
        self.appointment_id = appointment_id
        self.appointment_url = appointment_url
        self.token = token
        self.chat_id = chat_id
        self.browsers = browsers
        self.check = check
        self.reschedule = reschedule
        self.send_telegram_notification = send_telegram_notification

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
            "Calgary": "Consular Address \
                            615 Macleod Trail, SE \
                            Suite 1000 \
                            Calgary, AB, T2G 4T8 \
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
            "Ottawa": "Consular Address \
                            490 Sussex Drive \
                            Ottawa, ON, Ontario, K1N 1G8 \
                            Canada",
            "Quebec City": "Consular Address \
                            2, rue de la Terrasse Dufferin \
                            Québec, QC, G1R 4N5 \
                            Canada",
            "Toronto": "Consular Address \
                            225 Simcoe Street \
                            Toronto, ON, Ontario, M5G 1S4 \
                            Canada",
            "Vancouver": "Consular Address \
                            1075 West Pender Street \
                            Vancouver, BC, V6E 2M6 \
                            Canada",
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
        # self.datepicker_calendar_id = "#ui-datepicker-calendar"
        self.time_appointment_selector = "#appointments_consulate_appointment_time"
        self.network_request_regex = r"^[0-9]{2}\.json\?appointments\[expedite\]=false$"
        self.match_id = ".ui-datepicker-group-first  td.undefined > a.ui-state-default"
        self.json_response_base_link = appointment_url.format(appointment_id)
        self.poll_count = 0

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
        self.context = self.browser.new_context()
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
            self.go_to_page(self.login_url)
            self.page.get_by_label(self.username_input_id).fill(username)
            self.page.get_by_label(self.password_input_id).fill(password)
            self.page.locator("label").filter(
                has_text=self.terms_checkbox_label
            ).click()
            self.page.get_by_role("button", name=self.sign_in_button_label).click()

            if press_ok:
                self.capture_screenshot("press-ok")
                self.page.get_by_label("OK").click()
            self.capture_screenshot("logged-in")

            if continue_login:
                self.page.get_by_role(
                    "menuitem", name=self.continue_button_label
                ).click()
        except Exception as e:
            time.sleep(60)
            self.login(
                username=username,
                password=password,
                continue_login=False,
                press_ok=True,
            )

    def navigate_to_appointments(self, appointment_id):
        try:
            self.page.goto(self.appointment_link.format(appointment_id))
            self.page.wait_for_load_state("networkidle")
            # if is_multiple_users:
            #     self.handle_confirm_page_befor_navigate_to_appointment()
        except Exception as e:
            time.sleep(120)
            self.navigate_to_appointments(appointment_id)

    def check_availability(self):
        self.page.locator(self.calender_id).first.text_content()
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

            except Exception:
                logger.error(
                    "Exception occurred in check_availability()", exc_info=True
                )
                logger.error("No match found, continuing checks...")
                return False, True

            if calendar_date:
                logger.info(
                    f"Date found: {calendar_date.strftime('%Y-%m-%d')}. Exiting..."
                )
                self.new_date = calendar_date
                return True, False

        return False, True

    def get_appointment_date(self):
        try:
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
                # location_selector.click()
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

            if self.is_date_available():
                availability_list.append(True)

                continue_check = True
                self.page.locator(self.calender_dropdown_date_selector).click()

                while continue_check:
                    result, continue_check = self.check_availability()

                    if result:
                        formatted_found_date = self.new_date.strftime("%Y-%m-%d")
                        message = (
                            f"Date available at {location} on {formatted_found_date}"
                        )
                        logger.info(message)
                        if (
                            self.send_telegram_notification
                            and self.new_date < self.current_date
                        ):
                            self.send_telegram_notification(message)

                        if self.reschedule:
                            if self.new_date < self.current_date:
                                self.reschedule_appointment(location)

                        break

                    else:
                        self.page.get_by_text(self.next_button_label).click()
                        time.sleep(0.2)

                self.page.keyboard.press("Escape")

            else:
                availability_list.append(False)
                logger.info(f"No dates available at {location}")

        return any(availability_list)

    def run(self):
        self.is_running = True
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

                if session_number == self.browsers - 1:
                    logger.info("All browser sessions completed.")
                    self.close_browser()
        self.is_running = False

    def send_telegram_notification(self, message):
        logger.info("Trying to send telegram noti...")
        # url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": self.chat_id, "text": message}
        try:
            # Send the message using an HTTP POST request
            response = requests.post(url, data=params)
            if response.status_code == 200:
                print("Message sent successfully!")
            else:
                print(f"{response.status_code}: Failed to send message.")
        except Exception as e:
            print(f"Error sending message: {e}")

    def reschedule_appointment(self, location):
        try:
            self.page.query_selector(self.match_id).click()
            time.sleep(0.5)
            options = self.page.locator(self.time_appointment_selector).text_content()
            option = options.strip()[:5]
            self.page.locator(self.time_appointment_selector).select_option(option)
            self.page.get_by_text("Reschedule").last.click()
            self.page.get_by_text("Confirm").last.click()
            time.sleep(5)

            self.current_date = self.get_appointment_date()

            # Get the physical address of the location
            location_address = self.visa_locations.get(location, "Unknown Location")

            # Log and send updated message
            message = f"Rescheduled to a new earlier appointment date at {location}: \nDate: {self.current_date}\nLocation: {location_address}"
            logger.info(message)
            self.send_telegram_notification(message)

        except Exception:
            message = f"Error while booking new date for {location} ({user[:3]})"
            logger.error(message, exc_info=True)

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
            # Click the "Continue" button
            self.page.locator(
                'input[type="submit"][name="commit"][value="Continue"]'
            ).click()
            # logger.info("Successfully clicked the Continue button.")

        except Exception as e:
            # logger.error("Failed to click on the Continue button", exc_info=True)
            self.navigate_to_appointments()


if __name__ == "__main__":

    logger.info("Script started")

    current_time = datetime.now()
    target_time = current_time.replace(
        hour=1, minute=15, second=0, microsecond=0
    ) + timedelta(days=1)
    time_until_target = (target_time - current_time).total_seconds()
    logger.info(f"Sleeping until {target_time}...")
    # time.sleep(time_until_target
    # )  ### Wait in seconds for after how long you want the script to kick off

    visa_automation = VisaAutomation()
    visa_automation.run()
