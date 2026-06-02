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
}

LOGIN_URL = "https://ais.usvisa-info.com/en-uk/niv/users/sign_in"
APPOINTMENT_URL_TEMPLATE = "https://ais.usvisa-info.com/en-uk/niv/schedule/{}/appointment"

VISA_LOCATIONS: dict[str, str] = {
    "London": "33 Nine Elms Lane, London, SW11 7US, United Kingdom",
    "Belfast": "Belfast, United Kingdom",
}
