from flask import Flask, render_template, request, jsonify
from main import VisaAutomation
import threading

app = Flask(__name__)

visa_automation = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start_automation", methods=["POST"])
def start_automation():
    global visa_automation
    if visa_automation is None or not visa_automation.is_running:
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

        visa_automation = VisaAutomation(
            username=username,
            password=password,
            appointment_id=appointment_id,
            appointment_url=appointment_url,
            token=token,
            chat_id=chat_id,
            browsers=browsers,
            check=check,
            reschedule=reschedule,
            send_telegram_notification=send_telegram_notification,
        )
        thread = threading.Thread(target=visa_automation.run)
        thread.start()
        return jsonify({"status": "Automation started"})
    else:
        return jsonify({"status": "Automation already running"})


@app.route("/stop_automation", methods=["POST"])
def stop_automation():
    global visa_automation
    if visa_automation and visa_automation.is_running:
        visa_automation.stop()
        return jsonify({"status": "Automation stopped"})
    else:
        return jsonify({"status": "No automation running"})


@app.route("/get_status", methods=["GET"])
def get_status():
    global visa_automation
    if visa_automation:
        return jsonify(
            {
                "is_running": visa_automation.is_running,
                "current_appointment": str(visa_automation.current_date),
                "new_appointment": (
                    str(visa_automation.new_date) if visa_automation.new_date else None
                ),
                "last_checked_location": visa_automation.last_checked_location,
            }
        )
    else:
        return jsonify({"status": "No automation instance created"})


if __name__ == "__main__":
    app.run(debug=True)
