import os
from face_detection import FaceDetection
from gpt_client import AIClient
from pathlib import Path
from dotenv import load_dotenv
from twilio_client import TwilioClient

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

client = AIClient()

twilio_client = None
if os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and os.getenv("TWILIO_WHATSAPP_FROM") and os.getenv("TELEPHONE_NUMBER"):
    twilio_client = TwilioClient()

debug=True
solo_video=False  # False = multi-window mosaic (all detectors visible), True = single window

config = None
if not debug:
    from menu import show_menu_modern
    config = show_menu_modern(client=client)

    if config is None:
        print("Application cancelled by user")
        exit(0)

    print(f"Config: {config}")

face_detection = FaceDetection(debug=debug, solo_video=solo_video, ai_client=client, sms_client=twilio_client)

face_detection.face_freeze_module_init()
face_detection.eye_tracking_module_init()
face_detection.blinking_module_init()
face_detection.twitch_detector_module_init()
face_detection.shake_detection_module_init()
face_detection.face_drooping_model_init()
face_detection.health_monitor_module_init()

if config and config.get('context_multipliers'):
    face_detection.apply_context_multipliers(config['context_multipliers'])
    if config.get('context_summary'):
        print(f"📋 Session context: {config['context_summary']}")

face_detection.start()