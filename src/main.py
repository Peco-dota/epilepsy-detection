from face_detection import FaceDetection
from gpt_client import AIClient

client = AIClient()
twilio_client = None

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