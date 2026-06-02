SELECTORS: dict[str, str] = {
    "username": "Email",
    "password": "Password",
    "terms_label": "I have read and understood the Privacy Policy and the Terms of Use",
    "sign_in_button": "Sign In",
    "continue_button": "Continue",
    "not_available": "#consulate_date_time_not_available",
    "location": "#appointments_consulate_appointment_facility_id",
    "date_dropdown": "#appointments_consulate_appointment_date",
    "calendar_title": ".ui-datepicker-title",
    "calendar_month": ".ui-datepicker-month",
    "calendar_year": ".ui-datepicker-year",
    "match_date": ".ui-datepicker-group-first  td.undefined > a.ui-state-default",
    "appointment_date": ".consular-appt",
    "time_slot": "#appointments_consulate_appointment_time",
    "next_button": "Next",
    "applicants_checkbox": "input[type='checkbox'][name^='applicants']",
}

APPOINTMENT_DATE_REGEX = r".*Appointment:(.*)(?:Vancouver|Toronto|Calgary|Ottawa|Halifax|Montreal) local time.*$"
LOGIN_URL = "https://ais.usvisa-info.com/en-ca/niv/users/sign_in"
APPOINTMENT_URL_TEMPLATE = "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"

VISA_LOCATIONS: dict[str, str] = {
    "Toronto": "225 Simcoe Street, Toronto, ON, M5G 1S4, Canada",
    "Vancouver": "1075 West Pender Street, Vancouver, BC, V6E 2M6, Canada",
    "Calgary": "615 Macleod Trail, SE, Suite 1000, Calgary, AB, T2G 4T8, Canada",
    "Ottawa": "490 Sussex Drive, Ottawa, ON, K1N 1G8, Canada",
    "Halifax": "Suite 904, Purdy's Wharf Tower II, 1969 Upper Water Street, Halifax, NS, B3J 3R7, Canada",
    "Montreal": "1134 Saint-Catherine St. West, Montréal, QC, H3B 1H4, Canada",
}

MONTH_MAP: dict[str, int] = {
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
}
