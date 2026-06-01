import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

# ── Dev flags ──────────────────────────────────────────────────────────────────
debug = '--debug' in sys.argv
solo_video = True

# ── Clients ────────────────────────────────────────────────────────────────────
from services.gpt_client import AIClient
from services.twilio_client import TwilioClient

try:
    USE_AI = True
    client = AIClient() if USE_AI else None
except ValueError:
    client = None
    print("⚠️  AI features disabled — set GEMINI_API_KEY in src/.env")

twilio_client = None
if all(os.getenv(k) for k in ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM', 'TELEPHONE_NUMBER']):
    twilio_client = TwilioClient()

# ── Debug shortcut ─────────────────────────────────────────────────────────────
if debug:
    from detectors.face_detection import FaceDetection
    fd = FaceDetection(debug=True, solo_video=solo_video, ai_client=client, sms_client=twilio_client)
    fd.face_freeze_module_init()
    fd.eye_tracking_module_init()
    fd.blinking_module_init()
    fd.twitch_detector_module_init()
    fd.shake_detection_module_init()
    fd.face_drooping_model_init()
    fd.health_monitor_module_init()
    fd.start()
    sys.exit(0)

# ── Login / register ───────────────────────────────────────────────────────────
from ui.auth_screen import show_auth
email = show_auth()
if not email:
    sys.exit(0)

# ── Patient selector + daily check-in ─────────────────────────────────────────
from ui.patients_screen import show_patients
from ui.theme import DEBUG_OVERLAY

while True:
    result = show_patients(client=client, twilio_client=twilio_client)
    if result is None:
        sys.exit(0)

    patient = result['patient']
    config  = result.get('config', {}) or {}

    # ── Start monitoring ───────────────────────────────────────────────────────
    from detectors.face_detection import FaceDetection
    face_detection = FaceDetection(
        debug=False,
        solo_video=solo_video,
        ai_client=client,
        sms_client=twilio_client,
        patient_id=patient['id'],
        debug_overlay=DEBUG_OVERLAY,
        screen_protection=config.get('screen_protection_enabled', True),
    )

    face_detection.face_freeze_module_init()
    face_detection.eye_tracking_module_init()
    face_detection.blinking_module_init()
    face_detection.twitch_detector_module_init()
    face_detection.shake_detection_module_init()
    face_detection.face_drooping_model_init()
    face_detection.health_monitor_module_init()

    if config.get('audio_enabled'):
        face_detection.audio_module_init()

    if config.get('context_multipliers'):
        face_detection.apply_context_multipliers(config['context_multipliers'])
        if config.get('context_summary'):
            print(f"📋 Context: {config['context_summary']}")

    face_detection.patient_name = patient.get('name', '')
    face_detection.start()
