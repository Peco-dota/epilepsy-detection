from twilio.rest import Client
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))


def _format_whatsapp_number(number):
    if not number:
        return None
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


class TwilioClient:
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.from_number = _format_whatsapp_number(os.getenv('TWILIO_WHATSAPP_FROM'))
        self.to_number = _format_whatsapp_number(os.getenv('TELEPHONE_NUMBER'))
        self.client = Client(self.account_sid, self.auth_token)

    def send_message(self, message):
        self.client.messages.create(
            from_=self.from_number,
            to=self.to_number,
            body=message
        )