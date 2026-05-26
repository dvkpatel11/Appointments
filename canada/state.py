import json

from canada import config
from canada import db


def save_state(user_id, instance):
    data = {
        "is_running": instance.is_running,
        "current_action": instance.current_action,
        "action_log": instance.action_log,
        "current_appointment": str(instance.current_date) if instance.current_date else None,
        "new_appointment": str(instance.new_date) if instance.new_date else None,
        "last_checked_location": instance.last_checked_location,
        "appointments_page_screenshot": instance.appointments_page_screenshot,
    }
    db.save_automation_state(user_id, data)


def load_state(user_id):
    return db.load_automation_state(user_id)


def delete_state(user_id):
    db.delete_automation_state(user_id)


def load_client_tokens():
    return db.get_all_client_tokens()


def save_client_tokens(tokens):
    for token, data in tokens.items():
        db.save_client_token(token, data)


def load_settings():
    return dict(db.SETTINGS_CACHE)


def save_settings(settings):
    for key, value in settings.items():
        db.set_setting(key, value)


def serialize_automation(inst):
    return {
        "is_running": inst.is_running,
        "current_action": inst.current_action,
        "action_log": inst.action_log,
        "current_appointment": str(inst.current_date) if inst.current_date else None,
        "new_appointment": str(inst.new_date) if inst.new_date else None,
        "last_checked_location": inst.last_checked_location,
    }
