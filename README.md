# usvisa-appointment

# Env setup

## Pre-requisite

- Make sure python3 is installed

## setup

- create virtaul env: `python -m venv myenv`
- activate it: `source myenv/bin/activate`
- install requirements: `pip install -r requirements.txt`
- install playwright : `playwright install`
- install playwright browsers : `playwright install-deps`

## config

- create `creds.py` inside code folder and fill values as below

```
user = "abc@gmail.com"
password = "Password"
# get this id from reschedeule page url mentioned below
appointment_id = "12345678"
appointment_url = "https://ais.usvisa-info.com/en-ca/niv/schedule/{}/appointment"
visa_locations = ["Toronto", "Ottawa", "Vancouver", "Calgary"]
check = 12
time_gap = 300
reschedule = False
send_telegram_notification =True
TOKEN = "telegram bot token id"
chat_id = "telegram chat id"
browsers = 10
is_multiple_users = False
```

- Update the time to sleep to number of seconds you want the script to sleep before kicking off. Seconds from now() to 10 PM is ideal

## run

`python ./code/visa.py`
