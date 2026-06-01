"""
Centralised colour theme.  Read once at app start from data/settings.json.
All screen modules import their colour constants from here so that the right
palette is baked in at import time.  Changing the theme in Settings and
restarting the app applies the new palette everywhere.
"""
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent.parent.parent / 'data' / 'settings.json'

_LIGHT = dict(
    BG='#f4f3ee', SURFACE='#e8e5dc', CARD='#ffffff',
    BORDER='rgba(177,173,161,0.4)',
    TEXT='#1c1917', MUTED='#8a847a',
    ACCENT='#c15f3c', ACCENT2='#d4724e',
    SUCCESS='#2e7d32', DANGER='#b91c1c', WARN='#b45309',
    INPUT_BG='#ffffff', IS_DARK=False,
)

_DARK = dict(
    BG='#1c1917', SURFACE='#252220', CARD='#2e2b28',
    BORDER='rgba(80,75,65,0.55)',
    TEXT='#ede9e4', MUTED='#9e9890',
    ACCENT='#d4724e', ACCENT2='#e08060',
    SUCCESS='#4ade80', DANGER='#f87171', WARN='#fbbf24',
    INPUT_BG='#3a3530', IS_DARK=True,
)


def _load_name() -> str:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f).get('theme', 'light')
    except Exception:
        return 'light'


def save_name(name: str):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data['theme'] = name
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_name() -> str:
    return NAME


def set_active(name: str):
    """Update all module-level colour constants in-process (no restart needed)."""
    global BG, SURFACE, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2
    global SUCCESS, DANGER, WARN, INPUT_BG, IS_DARK, NAME
    p = _DARK if name == 'dark' else _LIGHT
    BG = p['BG']; SURFACE = p['SURFACE']; CARD = p['CARD']
    BORDER = p['BORDER']; TEXT = p['TEXT']; MUTED = p['MUTED']
    ACCENT = p['ACCENT']; ACCENT2 = p['ACCENT2']
    SUCCESS = p['SUCCESS']; DANGER = p['DANGER']; WARN = p['WARN']
    INPUT_BG = p['INPUT_BG']; IS_DARK = p['IS_DARK']
    NAME = name
    save_name(name)


NAME = _load_name()
_p = _DARK if NAME == 'dark' else _LIGHT

BG       = _p['BG']
SURFACE  = _p['SURFACE']
CARD     = _p['CARD']
BORDER   = _p['BORDER']
TEXT     = _p['TEXT']
MUTED    = _p['MUTED']
ACCENT   = _p['ACCENT']
ACCENT2  = _p['ACCENT2']
SUCCESS  = _p['SUCCESS']
DANGER   = _p['DANGER']
WARN     = _p['WARN']
INPUT_BG = _p['INPUT_BG']
IS_DARK  = _p['IS_DARK']
