import json
from pathlib import Path
from datetime import datetime

PROFILE_FILE = Path(__file__).parent.parent / 'profile.json'

DEFAULT = {
    'setup_complete': False,
    'patient_name': '',
    'patient_age': '',
    'emergency_contact': '',
    'created_at': '',
    'last_calibration': '',
}


def load_profile() -> dict:
    if PROFILE_FILE.exists():
        try:
            data = json.loads(PROFILE_FILE.read_text())
            p = DEFAULT.copy()
            p.update(data)
            return p
        except Exception:
            pass
    return DEFAULT.copy()


def save_profile(profile: dict):
    try:
        PROFILE_FILE.write_text(json.dumps(profile, indent=2))
    except Exception as e:
        print(f"Could not save profile: {e}")


def is_setup_complete() -> bool:
    return load_profile().get('setup_complete', False)


def mark_calibrated():
    p = load_profile()
    p['last_calibration'] = datetime.now().isoformat()
    save_profile(p)
