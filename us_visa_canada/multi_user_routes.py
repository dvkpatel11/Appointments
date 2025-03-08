from flask import Flask, render_template, request, jsonify
from main import VisaAutomation
import threading
import json

app = Flask(__name__)

automation_instances = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/multi_user")
def multi_user():
    return render_template("multi_user.html")


@app.route("/start_automation", methods=["POST"])
def start_automation():
    user_id = request.form.get("user_id", "default")
    if (
        user_id not in automation_instances
        or not automation_instances[user_id].is_running
    ):
        # Get credentials and settings from the form
        username = request.form.get("username")
        password = request.form.get("password")
        appointment_id = request.form.get("appointment_id")
        appointment_url = request.form.get("appointment_url")
        token = request.form.get("token")
        chat_id = request.form.get("chat_id")
        browsers = int(request.form.get("browsers", 1))
        check = int(request.form.get("check", 1))
        reschedule = request.form.get("reschedule") == "true"
        send_telegram_notification = (
            request.form.get("send_telegram_notification") == "true"
        )

        automation_instances[user_id] = VisaAutomation(
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            token=token,
            chat_id=chat_id,
            browsers=browsers,
            check=check,
            reschedule=reschedule,
            telegram_noti_enabled=send_telegram_notification,
        )
        thread = threading.Thread(target=automation_instances[user_id].run)
        thread.start()
        return jsonify({"status": f"Automation started for user {user_id}"})
    else:
        return jsonify({"status": f"Automation already running for user {user_id}"})


@app.route("/stop_automation", methods=["POST"])
def stop_automation():
    user_id = request.form.get("user_id", "default")
    if user_id in automation_instances and automation_instances[user_id].is_running:
        automation_instances[user_id].stop()
        return jsonify({"status": f"Automation stopped for user {user_id}"})
    else:
        return jsonify({"status": f"No automation running for user {user_id}"})


@app.route("/get_status", methods=["GET"])
def get_status():
    user_id = request.args.get("user_id", "default")
    if user_id in automation_instances:
        return jsonify(
            {
                "is_running": automation_instances[user_id].is_running,
                "current_appointment": str(automation_instances[user_id].current_date),
                "new_appointment": (
                    str(automation_instances[user_id].new_date)
                    if automation_instances[user_id].new_date
                    else None
                ),
                "last_checked_location": automation_instances[
                    user_id
                ].last_checked_location,
            }
        )
    else:
        return jsonify({"status": f"No automation instance created for user {user_id}"})


@app.route("/start_multi_automation", methods=["POST"])
def start_multi_automation():
    users_data = json.loads(request.form.get("users_data"))
    for user_id, user_data in users_data.items():
        if (
            user_id not in automation_instances
            or not automation_instances[user_id].is_running
        ):
            automation_instances[user_id] = VisaAutomation(**user_data)
            thread = threading.Thread(target=automation_instances[user_id].run)
            thread.start()
    return jsonify({"status": "Multi-user automation started"})


@app.route("/stop_all_automation", methods=["POST"])
def stop_all_automation():
    for user_id, instance in automation_instances.items():
        if instance.is_running:
            instance.stop()
    return jsonify({"status": "All automations stopped"})


@app.route("/get_all_status", methods=["GET"])
def get_all_status():
    all_status = {}
    for user_id, instance in automation_instances.items():
        all_status[user_id] = {
            "is_running": instance.is_running,
            "current_appointment": str(instance.current_date),
            "new_appointment": str(instance.new_date) if instance.new_date else None,
            "last_checked_location": instance.last_checked_location,
        }
    return jsonify(all_status)


if __name__ == "__main__":
    app.run(debug=True)
