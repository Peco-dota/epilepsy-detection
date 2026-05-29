from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

class TwilioClient:
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.client = Client(self.account_sid, self.auth_token)

    def send_message(self, message):
        self.client.messages.create(
            from_='+13606671377',
            to=os.getenv("TELEPHONE_NUMBER"),
            body=message
        )