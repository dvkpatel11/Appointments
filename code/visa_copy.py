import re
import random
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dateutil import parser
from playwright.sync_api import TimeoutError, sync_playwright, expect

from creds import *

MAX_POLLS = 30
MIN_SLEEP_BEFORE_RETRY = 30  # seconds
MAX_SLEEP_BEFORE_RETRY = 60  # seconds


class VisaAutomation:
    def __init__(self):
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
            # "Calgary": "Consular Address \
            #                 615 Macleod Trail, SE \
            #                 Suite 1000 \
            #                 Calgary, AB, T2G 4T8 \
            #                 Canada",
            # "Halifax": "Consular Address \
            #                 Suite 904, Purdy's Wharf Tower II \
            #                 1969 Upper Water Street \
            #                 Halifax, NS, Nova Scotia, B3J 3R7 \
            #                 Canada",
            # "Montreal": "Consular Address \
            #                 1134 Saint-Catherine St. West \
            #                 Montréal, QC, Québec, H3B 1H4 \
            #                 Canada",
            # "Ottawa": "Consular Address \
            #                 490 Sussex Drive \
            #                 Ottawa, ON, Ontario, K1N 1G8 \
            #                 Canada",
            # "Quebec City": "Consular Address \
            #                 2, rue de la Terrasse Dufferin \
            #                 Québec, QC, G1R 4N5 \
            #                 Canada",
            # "Vancouver": "Consular Address \
            #                 1075 West Pender Street \
            #                 Vancouver, BC, V6E 2M6 \
            #                 Canada",
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

        logging.info("Response Status: %s", status)
        logging.info("Response Headers: %s", headers)
        logging.info("Response Body: %s", body)

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

    def login(self, username, password, continue_login=False, press_ok=True):
        try:
            self.go_to_page(self.login_url)
            logging.info(f"Loaded url {self.login_url}...")

            self.page.get_by_label(self.username_input_id).fill(username)
            self.page.get_by_label(self.password_input_id).fill(password)
            logging.info("Found login fields...")
            self.page.locator("label").filter(has_text=self.terms_checkbox_label).click()
            self.page.get_by_role("button", name=self.sign_in_button_label).click()
            logging.info("Found login fields...")

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
                username=user, password=password, continue_login=False, press_ok=True
            )

    def navigate_to_appointments(self, appointment_id):
        try:
            logging.error("Navigate_to_appointments...")
            self.page.goto(self.appointment_link.format(appointment_id))
            logging.error("Navigated...")
            self.page.wait_for_load_state("networkidle")
            logging.error("Loaded...")
            if is_multiple_users:
                self.handle_confirm_page_befor_navigate_to_appointment()
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
                logging.error(
                    "Exception occurred in check_availability()", exc_info=True
                )
                logging.error("No match found, continuing checks...")
                return False, True

            if calendar_date:
                logging.info(
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
            logging.info(f"Current appointment details: {appointment_datetime}")
            return appointment_datetime
        else:
            logging.warning("No appointment date information found.")
            return None

    def click_reschedule_and_navigate(self):
        logging.info("Attempting to click 'Reschedule Appointment' and navigate")
        try:
            # Look for the reschedule button
            reschedule_selector = "a.button:has-text('Reschedule Appointment')"
            reschedule_button = self.page.locator(reschedule_selector)

            if reschedule_button.is_visible(timeout=5000):
                logging.info("'Reschedule Appointment' button found. Clicking...")

                # Click the button and wait for navigation
                with self.page.expect_navigation(timeout=10000):
                    reschedule_button.click()

                logging.info(
                    "Clicked 'Reschedule Appointment' and navigated to new page"
                )
                logging.info(f"New page URL: {self.page.url}")
                return True
            else:
                logging.warning(
                    "'Reschedule Appointment' button not found or not visible"
                )
                return False

        except Exception as e:
            logging.error(
                f"Error while clicking 'Reschedule Appointment': {str(e)}",
                exc_info=True,
            )
            return False

    def select_location(self, location):
        if location in self.visa_locations:
            logging.info(f"Attempting to select location: {location}")
            try:
                if self.click_reschedule_and_navigate():
                    logging.info("Successfully navigated to the rescheduling page")
                else:
                    logging.warning(
                        "Could not navigate to rescheduling page. Attempting to proceed anyway."
                    )

                # info: Log page title and URL
                logging.info(f"Current page title: ")
                logging.info(f"{self.page.title()}")
                logging.info(f"Current page URL: {self.page.url}")

                # info: Check if the page is still valid
                if self.page.is_closed():
                    logging.error("Page is closed. Cannot proceed.")
                    return False

                # info: Log the HTML content of the page
                # logging.info(f"Page content html: {self.page.content()[:]}...")  # First 500 characters

                # info: Attempt to find the selector
                logging.info(
                    f"Attempting to locate element with selector: {self.location_id}"
                )
                try:
                    # Set a short timeout for infoging purposes
                    with self.page.expect_request("**/*", timeout=5000) as request_info:
                        location_selector = self.page.locator(self.location_id)
                        # Force evaluation to trigger any potential errors
                        is_visible = location_selector.is_visible(timeout=100)
                    logging.info(f"Selector found. Visible: {is_visible}")
                    logging.info(f"Last request URL: {request_info.value.url}")
                # except PlaywrightTimeoutError:
                #     logging.error(f"Timeout while trying to locate the element: {self.location_id}")
                #     return False
                except Exception as e:
                    logging.error(f"Error locating element: {str(e)}", exc_info=True)
                    return False

                # info: Check if the selector matches any elements
                count = location_selector.count()
                logging.info(f"Number of elements matching the selector: {count}")

                if count == 0:
                    logging.error(
                        f"No elements found matching the selector: {self.location_id}"
                    )
                    return False

                options = location_selector.locator("option")
                option_count = options.count()
                logging.info(f"Found {option_count} options in the dropdown")

                # Find the option with matching text
                for i in range(option_count):
                    option_text = options.nth(i).inner_text()
                    logging.info(f"Checking option {i}: {option_text}")
                    if option_text == location:
                        logging.info(f"Found matching option at index {i}")
                        # Select by index
                        location_selector.select_option(index=i)
                        logging.info(f"Selected option at index {i}")
                        break
                else:
                    logging.error(f"Location '{location}' not found in dropdown")
                    raise ValueError(f"Location '{location}' not found in dropdown")

                # Wait for network to be idle
                logging.info("Waiting for network to be idle")
                self.page.wait_for_load_state("networkidle")
                logging.info("Network is idle")

                # Verify selection
                logging.info("Verifying selection")
                expect(location_selector).to_have_value(location_selector.input_value())
                logging.info("Selection verified")

                # Optional: Click to ensure the change is registered
                logging.info("Clicking selector to ensure change is registered")
                location_selector.click()

                # Wait for any potential AJAX updates
                logging.info("Waiting for 2 seconds for potential AJAX updates")
                time.sleep(2)

                return True

            except TimeoutError:
                logging.error(f"Timeout occurred while selecting {location} location")

                return False

        return False

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
            logging.info(f"Checking availability at {location}")
            location_selected = self.select_location(location)

            if location_selected and self.is_date_available():
                availability_list.append(True)
                continue_check = True
                print(
                    f"Found date picker on page: f{self.page.locator(self.calender_dropdown_date_selector).text_content()}"
                )
                self.page.locator(self.calender_dropdown_date_selector).click()

                while continue_check:
                    result, continue_check = self.check_availability()

                    if result:
                        formatted_found_date = self.new_date.strftime("%Y-%m-%d")
                        message = (
                            f"Date available at {location} on {formatted_found_date}"
                        )
                        logging.info(message)
                        if send_telegram_notification:
                            self.send_telegram_notification(message)

                        if reschedule:
                            if self.new_date < self.current_date:
                                self.reschedule_appointment(location)

                        break

                    else:
                        self.page.get_by_text(self.next_button_label).click()
                        time.sleep(0.2)

                self.page.keyboard.press("Escape")

            else:
                availability_list.append(False)
                logging.info(f"No dates available at {location}")

        return any(availability_list)

    def run(self):
        for session_number in range(browsers):
            try:
                logging.info(f"Before context")
                self.create_new_context()
                logging.info(f"After context")
                self.login(username=user, password=password, continue_login=False)
                self.current_date = self.get_appointment_date()

                for check_number in range(check):
                    logging.info(f"Session {check_number}")
                    self.navigate_to_appointments(appointment_id)
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

                if session_number == browsers - 1:
                    logging.info("All browser sessions completed.")
                    self.close_browser()

    def send_telegram_notification(self, message):
        logging.info("Trying to send telegram noti...")
        # url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": chat_id, "text": message}
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
            logging.info(message)
            self.send_telegram_notification(message)

        except Exception:
            message = f"Error while booking new date for {location} ({user[:3]})"
            logging.error(message, exc_info=True)

    def handle_soft_ban(self):
        logging.info("Sleeping for 10 mins due to soft ban")
        time.sleep(600)
        self.poll_count = 0

    def sleep_before_retry(self, check_number):
        min_sleep = (check_number // 5) * MIN_SLEEP_BEFORE_RETRY
        max_sleep = min_sleep + MAX_SLEEP_BEFORE_RETRY
        sleep_time = random.randint(min_sleep, max_sleep)
        logging.info(f"Sleeping for {sleep_time} seconds before next check")
        time.sleep(sleep_time)

    def handle_error(self, error):
        logging.error("Error occurred while checking:", exc_info=True)
        logging.info("Sleeping for 5 mins due to error")
        time.sleep(300)

    def handle_confirm_page_befor_navigate_to_appointment(self):
        try:
            # Click the "Continue" button
            self.page.locator(
                'input[type="submit"][name="commit"][value="Continue"]'
            ).click()
            # logging.info("Successfully clicked the Continue button.")

        except Exception as e:
            # logging.error("Failed to click on the Continue button", exc_info=True)
            self.navigate_to_appointments()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    logging.info("Script started")

    current_time = datetime.now()
    target_time = current_time.replace(
        hour=1, minute=15, second=0, microsecond=0
    ) + timedelta(days=1)
    time_until_target = (target_time - current_time).total_seconds()
    logging.info(f"Sleeping until {target_time}...")
    # time.sleep(time_until_target)  ### Wait in seconds for after how long you want the script to kick off

    visa_automation = VisaAutomation()
    visa_automation.run()
