"""
Local account + multi-patient data store.
No network calls — everything lives in ../data/.
"""
import json
import hashlib
import uuid
from pathlib import Path
from datetime import datetime

DATA_DIR      = Path(__file__).parent.parent.parent / 'data'
PATIENTS_DIR  = DATA_DIR / 'patients'
AVATARS_DIR   = DATA_DIR / 'avatars'
ACCOUNTS_FILE = DATA_DIR / 'accounts.json'

DEFAULT_WEIGHTS = {
    'w_bpm': 0.10, 'w_color': 0.10, 'w_shake': 0.30, 'w_twitch': 0.35,
    'w_blink': 0.30, 'w_freeze': 0.40, 'w_asym': 0.55,
    'w_blink_nc': 0.30, 'w_bpm_nc': 0.10,
}


def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    PATIENTS_DIR.mkdir(exist_ok=True)
    AVATARS_DIR.mkdir(exist_ok=True)


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _load_data() -> dict:
    _ensure_dirs()
    if ACCOUNTS_FILE.exists():
        try:
            return json.loads(ACCOUNTS_FILE.read_text())
        except Exception:
            pass
    return {'accounts': [], 'current_email': ''}


def _save_data(data: dict):
    _ensure_dirs()
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2))


def _find_account(data: dict, email: str) -> dict | None:
    return next((a for a in data['accounts'] if a['email'] == email), None)


# ── Auth ──────────────────────────────────────────────────────────────────────

def register(email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not email or '@' not in email:
        return False, 'Enter a valid email address'
    if len(password) < 6:
        return False, 'Password must be at least 6 characters'
    data = _load_data()
    if _find_account(data, email):
        return False, 'An account with this email already exists'
    data['accounts'].append({
        'email': email,
        'password_hash': _hash(password),
        'patient_ids': [],
    })
    data['current_email'] = email
    _save_data(data)
    return True, ''


def login(email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    data = _load_data()
    account = _find_account(data, email)
    if not account:
        return False, 'No account found with this email'
    if account['password_hash'] != _hash(password):
        return False, 'Incorrect password'
    data['current_email'] = email
    _save_data(data)
    return True, ''


def logout():
    data = _load_data()
    data['current_email'] = ''
    _save_data(data)


def current_email() -> str:
    return _load_data().get('current_email', '')


# ── Patients ──────────────────────────────────────────────────────────────────

def get_patients() -> list:
    data = _load_data()
    account = _find_account(data, data.get('current_email', ''))
    if not account:
        return []
    result = []
    for pid in account['patient_ids']:
        p = get_patient(pid)
        if p:
            result.append(p)
    return result


def add_patient(name: str, age: str = '') -> dict:
    _ensure_dirs()
    patient = {
        'id': str(uuid.uuid4()),
        'name': name,
        'age': age,
        'emergency_contact': '',
        'setup_complete': False,
        'created_at': datetime.now().isoformat(),
        'last_calibration': '',
        'avatar': None,
        'weights': DEFAULT_WEIGHTS.copy(),
    }
    (PATIENTS_DIR / f"{patient['id']}.json").write_text(json.dumps(patient, indent=2))
    data = _load_data()
    account = _find_account(data, data.get('current_email', ''))
    if account:
        account['patient_ids'].append(patient['id'])
        _save_data(data)
    return patient


def get_patient(patient_id: str) -> dict | None:
    pfile = PATIENTS_DIR / f'{patient_id}.json'
    if pfile.exists():
        try:
            return json.loads(pfile.read_text())
        except Exception:
            pass
    return None


def save_patient(patient: dict):
    _ensure_dirs()
    (PATIENTS_DIR / f"{patient['id']}.json").write_text(json.dumps(patient, indent=2))


def delete_patient(patient_id: str):
    data = _load_data()
    account = _find_account(data, data.get('current_email', ''))
    if account and patient_id in account['patient_ids']:
        account['patient_ids'].remove(patient_id)
        _save_data(data)
    pfile = PATIENTS_DIR / f'{patient_id}.json'
    if pfile.exists():
        pfile.unlink()


# ── Per-patient weights ───────────────────────────────────────────────────────

def get_weights(patient_id: str) -> dict:
    patient = get_patient(patient_id)
    if patient and 'weights' in patient:
        w = DEFAULT_WEIGHTS.copy()
        w.update({k: v for k, v in patient['weights'].items() if k in w})
        return w
    return DEFAULT_WEIGHTS.copy()


def save_weights(patient_id: str, weights: dict):
    patient = get_patient(patient_id)
    if patient:
        patient['weights'] = weights
        save_patient(patient)


# ── Account management ───────────────────────────────────────────────────────

def change_email(current_email: str, new_email: str, password: str) -> tuple[bool, str]:
    new_email = new_email.strip().lower()
    if not new_email or '@' not in new_email:
        return False, 'Enter a valid email address'
    data = _load_data()
    account = _find_account(data, current_email)
    if not account:
        return False, 'Account not found'
    if account['password_hash'] != _hash(password):
        return False, 'Incorrect password'
    if _find_account(data, new_email):
        return False, 'That email is already in use'
    account['email'] = new_email
    if data.get('current_email') == current_email:
        data['current_email'] = new_email
    _save_data(data)
    return True, ''


def change_password(email: str, current_password: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 6:
        return False, 'Password must be at least 6 characters'
    data = _load_data()
    account = _find_account(data, email)
    if not account:
        return False, 'Account not found'
    if account['password_hash'] != _hash(current_password):
        return False, 'Current password is incorrect'
    account['password_hash'] = _hash(new_password)
    _save_data(data)
    return True, ''


# ── Notification phones ───────────────────────────────────────────────────────

def get_notification_phones(email: str = '') -> list:
    data = _load_data()
    email = email or data.get('current_email', '')
    account = _find_account(data, email)
    if not account:
        return []
    return account.get('notification_phones', [])


def save_notification_phones(phones: list, email: str = ''):
    data = _load_data()
    email = email or data.get('current_email', '')
    account = _find_account(data, email)
    if account:
        account['notification_phones'] = [p for p in phones if p.strip()]
        _save_data(data)


def save_avatar_photo(patient_id: str, source_path: str) -> str:
    """Copy source_path into data/avatars/ and return the destination path."""
    import shutil
    _ensure_dirs()
    ext = Path(source_path).suffix.lower() or '.jpg'
    dest = AVATARS_DIR / f'{patient_id}{ext}'
    shutil.copy2(source_path, dest)
    return str(dest)
