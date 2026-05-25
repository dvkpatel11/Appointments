import os
import json

from canada import config


# ── State save/load (cross-process via JSON files) ───────────────────────────

def save_state(user_id, instance):
    os.makedirs(config.STATE_DIR, exist_ok=True)
    state = {
        "is_running": instance.is_running,
        "current_action": instance.current_action,
        "action_log": instance.action_log,
        "current_appointment": str(instance.current_date) if instance.current_date else None,
        "new_appointment": str(instance.new_date) if instance.new_date else None,
        "last_checked_location": instance.last_checked_location,
        "appointments_page_screenshot": instance.appointments_page_screenshot,
    }
    with open(f"{config.STATE_DIR}/{user_id}.json", "w") as f:
        json.dump(state, f)


def load_state(user_id):
    state_file = f"{config.STATE_DIR}/{user_id}.json"
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def delete_state(user_id):
    state_file = f"{config.STATE_DIR}/{user_id}.json"
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
        except Exception:
            pass


# ── Client tokens ─────────────────────────────────────────────────────────────

def load_client_tokens():
    os.makedirs(os.path.dirname(config.CLIENT_TOKENS_FILE), exist_ok=True)
    if os.path.exists(config.CLIENT_TOKENS_FILE):
        try:
            with open(config.CLIENT_TOKENS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_client_tokens(tokens):
    try:
        with open(config.CLIENT_TOKENS_FILE, "w") as f:
            json.dump(tokens, f)
    except Exception:
        pass


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings():
    settings = dict(config.DEFAULT_SETTINGS)
    if os.path.exists(config.SETTINGS_FILE):
        try:
            with open(config.SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))
        except Exception:
            pass
    return settings


def save_settings(settings):
    os.makedirs(os.path.dirname(config.SETTINGS_FILE), exist_ok=True)
    with open(config.SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


# ── Serialization ─────────────────────────────────────────────────────────────

def serialize_automation(inst):
    return {
        "is_running": inst.is_running,
        "current_action": inst.current_action,
        "action_log": inst.action_log,
        "current_appointment": str(inst.current_date) if inst.current_date else None,
        "new_appointment": str(inst.new_date) if inst.new_date else None,
        "last_checked_location": inst.last_checked_location,
    }
