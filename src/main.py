from face_detection import FaceDetection
from menu import show_menu_modern
from twilio_client import TwilioClient
from gpt_client import AIClient

client = AIClient()
twilio_client = TwilioClient()

debug=True
solo_video=False

if not debug:
    config = show_menu_modern(client=client)

    if config is None:
        print("Aplikácia zrušená používateľom")
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

face_detection.start()