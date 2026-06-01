"""
Patient selector screen.
Shows all patients for the current account. Handles adding and recalibrating
patients by running the setup wizard modally via QEventLoop.
Returns the selected patient dict, or None on sign-out / close.
"""
import os
import sys
import shutil
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame,
    QGraphicsOpacityEffect, QDialog, QFileDialog, QGridLayout,
    QButtonGroup, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from core import account_store
from ui.theme import BG, SURFACE, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, SUCCESS, DANGER, WARN, IS_DARK, INPUT_BG

# (emoji, accent-color)
PRESET_AVATARS = [
    ("🦁", "#B45309"), ("🐯", "#B91C1C"), ("🐻", "#78350F"),
    ("🐼", "#1F2937"), ("🦊", "#C2410C"), ("🐨", "#4B5563"),
    ("🐸", "#15803D"), ("🦋", "#6D28D9"), ("🐬", "#0369A1"),
    ("🦜", "#9D174D"), ("🐘", "#374151"), ("🦒", "#A16207"),
    ("🐉", "#991B1B"), ("⭐", "#92400E"), ("🌸", "#BE185D"),
    ("🌈", "#5B21B6"), ("🚀", "#1D4ED8"), ("🎈", "#B91C1C"),
    ("🌊", "#0E7490"), ("🌙", "#4338CA"),
]

def _make_style():
    return f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif;
}}
QLabel {{ background: transparent; color: {TEXT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 4px; border-radius: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(177,173,161,0.5); border-radius: 2px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 14px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});
    color: #ffffff; border-radius: 10px; font-size: 14px; font-weight: bold; border: none;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444);
}}
QPushButton#start {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {SUCCESS},stop:1 #1b5e20);
    color: #ffffff; border-radius: 8px; font-size: 13px; font-weight: bold; border: none;
}}
QPushButton#start:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #388e3c,stop:1 {SUCCESS});
}}
QPushButton#ghost {{
    background: transparent; color: {MUTED};
    border: 1px solid {BORDER}; border-radius: 8px; font-size: 12px;
}}
QPushButton#ghost:hover {{
    background: rgba(193,95,60,0.06); color: {TEXT};
    border-color: rgba(193,95,60,0.35);
}}
QPushButton#danger_ghost {{
    background: transparent; color: rgba(185,28,28,0.6);
    border: 1px solid rgba(185,28,28,0.2); border-radius: 8px; font-size: 12px;
}}
QPushButton#danger_ghost:hover {{
    background: rgba(185,28,28,0.06); color: {DANGER};
    border-color: rgba(185,28,28,0.4);
}}
QFrame#card {{
    background-color: {CARD}; border-radius: 16px; border: 1px solid {BORDER};
}}
QPushButton#av_btn {{
    background: transparent; border: none;
    border-radius: 22px; font-size: 22px; padding: 0; outline: none;
}}
QPushButton#av_btn:checked {{ background: transparent; border: none; font-size: 28px; }}
QPushButton#av_btn:hover:!checked {{ font-size: 25px; }}
QDialog {{ background-color: {CARD}; }}
QDialog QLabel {{ background: transparent; }}
QDialog QPushButton#dialog_primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});
    color: white; border-radius: 8px; font-size: 13px; font-weight: bold;
    border: none; padding: 10px 24px;
}}
QDialog QPushButton#dialog_primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444);
}}
QDialog QPushButton#dialog_cancel {{
    background: rgba(177,173,161,0.15); color: {MUTED};
    border: 1px solid rgba(177,173,161,0.4); border-radius: 8px;
    font-size: 13px; padding: 10px 20px;
}}
QDialog QPushButton#dialog_cancel:hover {{ background: rgba(177,173,161,0.28); color: {TEXT}; }}
QDialog QPushButton#dialog_secondary {{
    background: {CARD}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    font-size: 13px; padding: 10px 20px;
}}
QDialog QPushButton#dialog_secondary:hover {{ background: rgba(177,173,161,0.15); }}
"""

STYLE = _make_style()


# ── Avatar helpers ─────────────────────────────────────────────────────────────

def _hex_rgba(hex_color: str, alpha: int = 45) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _circular_pixmap(path: str, size: int) -> QPixmap:
    src = QPixmap(path)
    if src.isNull():
        return QPixmap()
    src = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    ox = (src.width() - size) // 2
    oy = (src.height() - size) // 2
    src = src.copy(ox, oy, size, size)
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, float(size), float(size))
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, src)
    painter.end()
    return result


def _make_avatar_label(avatar: dict, name: str, size: int = 52) -> QLabel:
    """Return a square QLabel rendering the patient's avatar."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignCenter)
    r = size // 2

    if avatar and avatar.get('type') == 'photo':
        path = avatar.get('path', '')
        if os.path.exists(path):
            lbl.setPixmap(_circular_pixmap(path, size))
            return lbl
        # fall through to default on missing file

    if avatar and avatar.get('type') == 'preset':
        emoji = avatar.get('emoji', '?')
        bg = _hex_rgba(avatar.get('bg', '#7c3aed'), 50)
        lbl.setText(emoji)
        lbl.setFont(QFont('', int(size * 0.44)))
        lbl.setStyleSheet(f'background: {bg}; border-radius: {r}px;')
    else:
        # default: initial letter
        letter = name[0].upper() if name else '?'
        lbl.setText(letter)
        lbl.setFont(QFont('', int(size * 0.35), QFont.Bold))
        lbl.setStyleSheet(
            f'background: rgba(193,95,60,0.15); color: #c15f3c; border-radius: {r}px;'
        )
    return lbl


# ── Avatar picker widget ───────────────────────────────────────────────────────

class _AvatarPicker(QWidget):
    """Preset grid + upload button. `selected` property returns avatar dict or None."""

    changed = Signal(object)  # emits avatar dict or None

    def __init__(self, initial: dict = None, parent=None):
        super().__init__(parent)
        self._avatar = initial
        self._photo_path = None
        self._btns: list[tuple[QPushButton, dict]] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.setStyleSheet('background: transparent;')
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Preview row: shows currently selected avatar large
        self._preview = QLabel()
        self._preview.setFixedSize(64, 64)
        self._preview.setAlignment(Qt.AlignCenter)
        self._update_preview()
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self._preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        # Preset grid (4 columns × 5 rows)
        grid = QWidget()
        grid.setStyleSheet('background: transparent;')
        gl = QGridLayout(grid)
        gl.setSpacing(10)
        gl.setContentsMargins(0, 0, 0, 0)
        cols = 5

        for i, (emoji, bg) in enumerate(PRESET_AVATARS):
            btn = QPushButton(emoji)
            btn.setObjectName('av_btn')
            btn.setFixedSize(44, 44)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            av = {'type': 'preset', 'emoji': emoji, 'bg': bg}
            already_selected = (
                self._avatar and
                self._avatar.get('type') == 'preset' and
                self._avatar.get('emoji') == emoji
            )
            if already_selected:
                btn.setChecked(True)
            btn.clicked.connect(lambda _, a=av, b=btn: self._select_preset(a, b))
            self._group.addButton(btn)
            self._btns.append((btn, av))
            gl.addWidget(btn, i // cols, i % cols)

        layout.addWidget(grid)

        # Restore shadow on initially-selected button
        for b, av in self._btns:
            if b.isChecked():
                self._apply_shadow(b)
                break

        # Upload button
        upload_btn = QPushButton('  Upload your own photo')
        upload_btn.setObjectName('ghost')
        upload_btn.setFixedHeight(36)
        upload_btn.clicked.connect(self._upload)
        layout.addWidget(upload_btn)

    def _select_preset(self, av: dict, btn: QPushButton):
        self._avatar = av
        self._photo_path = None
        self._apply_shadow(btn)
        self._update_preview()
        self.changed.emit(av)

    def _apply_shadow(self, selected_btn):
        for b, _ in self._btns:
            b.setGraphicsEffect(None)
        if selected_btn is None:
            return
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(100, 45, 15, 130))
        selected_btn.setGraphicsEffect(shadow)

    def _upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select a photo', '',
            'Images (*.jpg *.jpeg *.png *.webp *.bmp)'
        )
        if not path:
            return
        self._photo_path = path
        self._avatar = {'type': 'photo', 'path': path}
        for btn, _ in self._btns:
            btn.setChecked(False)
        self._apply_shadow(None)
        self._update_preview()
        self.changed.emit(self._avatar)

    def _update_preview(self):
        if not self._avatar:
            self._preview.setText('?')
            self._preview.setFont(QFont('', 22, QFont.Bold))
            self._preview.setStyleSheet(
                'background: rgba(193,95,60,0.12); color: #c15f3c; border-radius: 32px;'
            )
            return

        if self._avatar.get('type') == 'photo' and self._avatar.get('path'):
            pm = _circular_pixmap(self._avatar['path'], 64)
            if not pm.isNull():
                self._preview.setPixmap(pm)
                self._preview.setStyleSheet('')
                return

        if self._avatar.get('type') == 'preset':
            emoji = self._avatar.get('emoji', '?')
            bg = _hex_rgba(self._avatar.get('bg', '#7c3aed'), 55)
            self._preview.setText(emoji)
            self._preview.setFont(QFont('', 28))
            self._preview.setStyleSheet(
                f'background: {bg}; border-radius: 32px;'
            )

    @property
    def selected(self) -> dict:
        return self._avatar


# ── Add patient dialog ─────────────────────────────────────────────────────────

class _AddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Patient')
        self.setFixedSize(500, 700)
        self.setStyleSheet(STYLE)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.setSpacing(0)

        title = QLabel('Add a patient')
        title.setFont(QFont('', 17, QFont.Bold))
        layout.addWidget(title)
        layout.addSpacing(3)
        sub = QLabel("Choose an avatar and fill in the details. Symptom survey is next.")
        sub.setFont(QFont('', 12))
        sub.setStyleSheet(f'color: {MUTED};')
        layout.addWidget(sub)
        layout.addSpacing(18)

        # Avatar section label
        av_lbl = QLabel('AVATAR')
        av_lbl.setFont(QFont('', 11))
        av_lbl.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        layout.addWidget(av_lbl)
        layout.addSpacing(8)

        self._avatar_picker = _AvatarPicker(parent=self)
        layout.addWidget(self._avatar_picker)
        layout.addSpacing(18)

        # Name
        name_lbl = QLabel('NAME')
        name_lbl.setFont(QFont('', 11))
        name_lbl.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        layout.addWidget(name_lbl)
        layout.addSpacing(6)
        self._name = QLineEdit()
        self._name.setPlaceholderText('e.g. Emma')
        self._name.setFixedHeight(44)
        layout.addWidget(self._name)
        layout.addSpacing(12)

        # Age
        age_lbl = QLabel('AGE  (optional)')
        age_lbl.setFont(QFont('', 11))
        age_lbl.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        layout.addWidget(age_lbl)
        layout.addSpacing(6)
        self._age = QLineEdit()
        self._age.setPlaceholderText('e.g. 8')
        self._age.setFixedHeight(44)
        self._age.setFixedWidth(100)
        layout.addWidget(self._age)
        layout.addSpacing(8)

        self._err = QLabel('')
        self._err.setStyleSheet(f'color: {DANGER}; font-size: 12px;')
        self._err.setFixedHeight(16)
        layout.addWidget(self._err)
        layout.addSpacing(14)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setObjectName('dialog_cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addSpacing(8)
        ok_btn = QPushButton('Continue  →')
        ok_btn.setObjectName('dialog_primary')
        ok_btn.clicked.connect(self._accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _accept(self):
        if not self._name.text().strip():
            self._err.setText('Please enter a name')
            return
        self.accept()

    @property
    def name(self): return self._name.text().strip()
    @property
    def age(self): return self._age.text().strip()
    @property
    def avatar(self): return self._avatar_picker.selected


# ── Avatar edit dialog (for existing patients) ────────────────────────────────

class _AvatarEditDialog(QDialog):
    def __init__(self, current_avatar: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Change Avatar')
        self.setFixedSize(440, 480)
        self.setStyleSheet(STYLE)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(0)

        title = QLabel('Choose an avatar')
        title.setFont(QFont('', 16, QFont.Bold))
        layout.addWidget(title)
        layout.addSpacing(16)

        self._picker = _AvatarPicker(initial=current_avatar, parent=self)
        layout.addWidget(self._picker)
        layout.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setObjectName('dialog_cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addSpacing(8)
        save_btn = QPushButton('Save')
        save_btn.setObjectName('dialog_primary')
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    @property
    def avatar(self): return self._picker.selected


# ── Patient card ───────────────────────────────────────────────────────────────


class _CheckinPromptDialog(QDialog):
    def __init__(self, patient_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Start Monitoring')
        self.setFixedSize(440, 220)
        self.setStyleSheet(STYLE)
        self.setModal(True)
        self.result_action = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)

        title = QLabel(f"Start monitoring {patient_name}?")
        title.setFont(QFont('', 16, QFont.Bold))
        layout.addWidget(title)

        sub = QLabel("You have already completed the daily survey today.")
        sub.setFont(QFont('', 12))
        sub.setStyleSheet(f'color: {MUTED};')
        layout.addWidget(sub)
        layout.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setObjectName('dialog_cancel')
        cancel_btn.clicked.connect(self.reject)
        
        retake_btn = QPushButton('Retake Survey')
        retake_btn.setObjectName('dialog_secondary')
        retake_btn.clicked.connect(self._retake)
        
        start_btn = QPushButton('Start Monitoring')
        start_btn.setObjectName('dialog_primary')
        start_btn.clicked.connect(self._start)
        
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(retake_btn)
        btn_row.addWidget(start_btn)
        
        layout.addLayout(btn_row)
        
    def _retake(self):
        self.result_action = 'retake'
        self.accept()
        
    def _start(self):
        self.result_action = 'start'
        self.accept()

class _PatientCard(QFrame):
    """Fully-clickable patient card with hover-lift and pointer cursor."""

    def __init__(self, patient, on_start, on_wizard, on_remove, on_edit_avatar, parent=None):
        super().__init__(parent)
        self._patient = patient
        self._on_start = on_start
        self._on_wizard = on_wizard
        self._on_remove = on_remove
        self._on_edit_avatar = on_edit_avatar
        self._is_setup = patient.get('setup_complete', False)

        self.setObjectName('card')
        self.setFixedSize(240, 270)
        self.setCursor(Qt.PointingHandCursor)

        border = '1.5px solid rgba(180,83,9,0.5)' if not self._is_setup else f'1px solid {BORDER}'
        self._base_style = (
            f'QFrame#card {{ background-color: {CARD}; border-radius: 16px; border: {border}; }}'
        )
        self._hover_style = (
            f'QFrame#card {{ background-color: {CARD}; border-radius: 16px;'
            f' border: {"1.5px solid rgba(180,83,9,0.7)" if not self._is_setup else "1px solid rgba(193,95,60,0.45)"}; }}'
        )
        self.setStyleSheet(self._base_style)
        self._build()

    def _build(self):
        cl = QVBoxLayout(self)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # ── Amber banner for incomplete patients ──────────────────────────────
        if not self._is_setup:
            banner = QWidget()
            banner.setFixedHeight(28)
            banner.setStyleSheet(
                'background: rgba(180,83,9,0.08);'
                'border-top-left-radius: 15px; border-top-right-radius: 15px;'
                'border-bottom: 1px solid rgba(180,83,9,0.12);'
            )
            bl = QHBoxLayout(banner)
            bl.setContentsMargins(12, 0, 12, 0)
            bang = QLabel('⚠')
            bang.setStyleSheet(f'color: {WARN}; font-size: 11px; background: transparent;')
            bl.addWidget(bang)
            bl.addSpacing(4)
            warn_lbl = QLabel('Setup not complete')
            warn_lbl.setFont(QFont('', 11, QFont.Medium))
            warn_lbl.setStyleSheet(f'color: {WARN}; background: transparent;')
            bl.addWidget(warn_lbl)
            bl.addStretch()
            cl.addWidget(banner)

        # ── Body ──────────────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet('background: transparent;')
        bl2 = QVBoxLayout(body)
        bl2.setContentsMargins(20, 14 if not self._is_setup else 18, 20, 14)
        bl2.setSpacing(0)

        # Avatar row + edit pencil
        av_row = QHBoxLayout()
        av_row.setSpacing(0)
        avatar_lbl = _make_avatar_label(self._patient.get('avatar'), self._patient['name'], size=52)
        av_row.addWidget(avatar_lbl)
        av_row.addStretch()

        edit_btn = QPushButton('✎')
        edit_btn.setFixedSize(26, 26)
        edit_btn.setStyleSheet(
            f'background: rgba(177,173,161,0.2); color: {MUTED};'
            f'border: 1px solid rgba(177,173,161,0.4); border-radius: 13px;'
            f'font-size: 12px; padding: 0;'
        )
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self._on_edit_avatar(self._patient))
        av_row.addWidget(edit_btn, alignment=Qt.AlignTop)
        bl2.addLayout(av_row)
        bl2.addSpacing(10)

        name_lbl = QLabel(self._patient['name'])
        name_lbl.setFont(QFont('', 16, QFont.Bold))
        bl2.addWidget(name_lbl)

        if self._patient.get('age'):
            age_lbl = QLabel(f"Age {self._patient['age']}")
            age_lbl.setFont(QFont('', 12))
            age_lbl.setStyleSheet(f'color: {MUTED};')
            bl2.addWidget(age_lbl)

        bl2.addSpacing(4)
        if self._is_setup:
            cal = self._patient.get('last_calibration', '')
            try:
                cal_text = f"Calibrated {datetime.fromisoformat(cal).strftime('%b %d')}"
            except Exception:
                cal_text = 'Calibrated'
            cal_lbl = QLabel(cal_text)
            cal_lbl.setFont(QFont('', 11))
            cal_lbl.setStyleSheet(f'color: {MUTED};')
            bl2.addWidget(cal_lbl)

        bl2.addStretch()

        if self._is_setup:
            # Primary CTA — full width, taller so it's clearly tappable
            start_btn = QPushButton('▶  Start monitoring')
            start_btn.setObjectName('start')
            start_btn.setFixedHeight(38)
            start_btn.setCursor(Qt.PointingHandCursor)
            start_btn.clicked.connect(lambda: self._on_start(self._patient))
            bl2.addWidget(start_btn)
            bl2.addSpacing(6)

            br = QHBoxLayout()
            br.setSpacing(6)
            recal_btn = QPushButton('Recalibrate')
            recal_btn.setObjectName('ghost')
            recal_btn.setFixedHeight(28)
            recal_btn.setCursor(Qt.PointingHandCursor)
            recal_btn.clicked.connect(lambda: self._on_wizard(self._patient))
            br.addWidget(recal_btn)
            del_btn = QPushButton('Remove')
            del_btn.setObjectName('danger_ghost')
            del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda: self._on_remove(self._patient))
            br.addWidget(del_btn)
            bl2.addLayout(br)
        else:
            setup_btn = QPushButton('Complete setup →')
            setup_btn.setObjectName('primary')
            setup_btn.setFixedHeight(38)
            setup_btn.setCursor(Qt.PointingHandCursor)
            setup_btn.clicked.connect(lambda: self._on_wizard(self._patient))
            bl2.addWidget(setup_btn)
            bl2.addSpacing(6)
            del_btn = QPushButton('Remove')
            del_btn.setObjectName('danger_ghost')
            del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda: self._on_remove(self._patient))
            bl2.addWidget(del_btn)

        cl.addWidget(body, stretch=1)

    # ── Hover: lift shadow ────────────────────────────────────────────────────

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(193, 95, 60, 55) if self._is_setup else QColor(180, 83, 9, 55))
        self.setGraphicsEffect(shadow)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._base_style)
        self.setGraphicsEffect(None)
        super().leaveEvent(event)

    # ── Click anywhere on the card background ─────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._is_setup:
                self._on_start(self._patient)
            else:
                self._on_wizard(self._patient)
        super().mousePressEvent(event)


# ── Patients screen ────────────────────────────────────────────────────────────

class PatientsScreen(QMainWindow):
    def __init__(self, client=None, twilio_client=None):
        super().__init__()
        self.client = client
        self.twilio_client = twilio_client
        self.result = None
        self.setWindowTitle('EpiGuard')
        self.setMinimumSize(960, 640)
        self.resize(960, 640)
        self.setStyleSheet(STYLE)
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 960) // 2, (screen.height() - 640) // 2)
        self._refresh()

    def _refresh(self):
        # Rebind module-level colour constants from current theme so all
        # f-strings below and in helper methods pick up the right values.
        from ui import theme as _t
        global BG, SURFACE, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2
        global SUCCESS, DANGER, WARN, IS_DARK, INPUT_BG, STYLE
        BG = _t.BG; SURFACE = _t.SURFACE; CARD = _t.CARD; BORDER = _t.BORDER
        TEXT = _t.TEXT; MUTED = _t.MUTED; ACCENT = _t.ACCENT; ACCENT2 = _t.ACCENT2
        SUCCESS = _t.SUCCESS; DANGER = _t.DANGER; WARN = _t.WARN
        IS_DARK = _t.IS_DARK; INPUT_BG = _t.INPUT_BG
        STYLE = _make_style()
        self.setStyleSheet(STYLE)

        if self.centralWidget():
            self.centralWidget().deleteLater()
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(f'background-color: {SURFACE}; border-bottom: 1px solid {BORDER};')
        header.setFixedHeight(60)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(32, 0, 32, 0)
        self._brand_lbl = QLabel('EpiGuard')
        self._brand_lbl.setFont(QFont('', 17, QFont.Bold))
        hl.addWidget(self._brand_lbl)
        hl.addStretch()
        self._email_lbl = QLabel(account_store.current_email())
        self._email_lbl.setFont(QFont('', 12))
        self._email_lbl.setStyleSheet(f'color: {MUTED};')
        hl.addWidget(self._email_lbl)
        hl.addSpacing(12)
        self._settings_btn = QPushButton('⚙')
        self._settings_btn.setFixedHeight(32)
        self._settings_btn.setFocusPolicy(Qt.NoFocus)
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.setStyleSheet(self._header_btn_style())
        self._settings_btn.clicked.connect(self._toggle_settings)
        hl.addWidget(self._settings_btn)
        hl.addSpacing(4)
        self._so_btn = QPushButton('Sign out')
        self._so_btn.setFixedHeight(32)
        self._so_btn.setFocusPolicy(Qt.NoFocus)
        self._so_btn.setCursor(Qt.PointingHandCursor)
        self._so_btn.setStyleSheet(self._header_btn_style(muted=True))
        self._so_btn.clicked.connect(self._sign_out)
        hl.addWidget(self._so_btn)
        outer.addWidget(header)

        # ── Stacked content (page 0 = patients, page 1 = settings) ───────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet('background: transparent;')
        self._stack.addWidget(self._build_patients_page())
        self._stack.addWidget(self._build_settings_page())
        self._stack.setCurrentIndex(0)
        outer.addWidget(self._stack, stretch=1)

        effect = QGraphicsOpacityEffect(root)
        root.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b'opacity', root)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuart)
        anim.start()

    # ── Page builders ─────────────────────────────────────────────────────────

    def _build_patients_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setStyleSheet('background: transparent;')
        bl = QVBoxLayout(body)
        bl.setContentsMargins(48, 36, 48, 36)
        bl.setSpacing(0)

        title_lbl = QLabel('Who are you monitoring today?')
        title_lbl.setFont(QFont('', 26, QFont.Bold))
        bl.addWidget(title_lbl)
        bl.addSpacing(6)
        sub = QLabel('Select a patient to start a session, or add a new one.')
        sub.setFont(QFont('', 13))
        sub.setStyleSheet(f'color: {MUTED};')
        bl.addWidget(sub)
        bl.addSpacing(32)

        grid = QHBoxLayout()
        grid.setSpacing(18)
        grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        for p in account_store.get_patients():
            grid.addWidget(self._build_card(p))

        add_tile = QFrame()
        add_tile.setObjectName('card')
        add_tile.setFixedSize(240, 260)
        add_tile.setCursor(Qt.PointingHandCursor)
        add_tile.setStyleSheet(
            'QFrame#card { background: transparent; border: 1.5px dashed rgba(193,95,60,0.35); border-radius: 16px; }'
            'QFrame#card:hover { border-color: rgba(193,95,60,0.65); background: rgba(193,95,60,0.04); }'
        )
        atl = QVBoxLayout(add_tile)
        atl.setAlignment(Qt.AlignCenter)
        plus = QLabel('+')
        plus.setFont(QFont('', 36, QFont.Light))
        plus.setStyleSheet(f'color: {ACCENT};')
        plus.setAlignment(Qt.AlignCenter)
        atl.addWidget(plus)
        add_lbl = QLabel('Add patient')
        add_lbl.setFont(QFont('', 14))
        add_lbl.setStyleSheet(f'color: {ACCENT};')
        add_lbl.setAlignment(Qt.AlignCenter)
        atl.addWidget(add_lbl)
        add_tile.mousePressEvent = lambda _: self._add_patient()
        grid.addWidget(add_tile)
        grid.addStretch()

        bl.addLayout(grid)
        bl.addStretch()
        scroll.setWidget(body)
        return scroll

    def _build_settings_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('background: transparent;')
        body = QWidget()
        body.setStyleSheet('background: transparent;')
        bl = QVBoxLayout(body)
        bl.setContentsMargins(48, 36, 48, 48)
        bl.setSpacing(20)
        scroll.setWidget(body)

        def _section(text):
            w = QWidget(); w.setStyleSheet("background: transparent;")
            row = QHBoxLayout(w); row.setContentsMargins(0, 4, 0, 4); row.setSpacing(8)
            bar = QWidget(); bar.setFixedSize(3, 14)
            bar.setStyleSheet(f"background: {ACCENT}; border-radius: 1px;")
            row.addWidget(bar, alignment=Qt.AlignVCenter)
            lbl = QLabel(text.upper())
            lbl.setFont(QFont('', 10, QFont.Bold))
            lbl.setStyleSheet(f"color: {MUTED}; letter-spacing: 0.8px;")
            row.addWidget(lbl); row.addStretch()
            return w

        def _card():
            f = QFrame()
            f.setStyleSheet(
                f"QFrame {{ background: {CARD}; border-radius: 14px; border: 1px solid {BORDER}; }}"
            )
            return f

        def _card_title(t):
            l = QLabel(t); l.setFont(QFont('', 13, QFont.Bold))
            l.setStyleSheet(f"color: {TEXT}; background: transparent;"); return l

        def _field(placeholder, password=False):
            f = QLineEdit(); f.setPlaceholderText(placeholder); f.setFixedHeight(44)
            f.setStyleSheet(
                f"QLineEdit {{ background: {INPUT_BG}; color: {TEXT};"
                f" border: 1.5px solid {BORDER}; border-radius: 10px; padding: 10px 14px; font-size: 14px; }}"
                f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
            )
            if password: f.setEchoMode(QLineEdit.Password)
            return f

        def _msg():
            l = QLabel(''); l.setFont(QFont('', 11))
            l.setWordWrap(True); l.setFixedHeight(16)
            l.setStyleSheet("background: transparent;"); return l

        def _show(lbl, text, ok):
            lbl.setText(text)
            lbl.setStyleSheet(f"color: {SUCCESS if ok else DANGER}; font-size: 11px; background: transparent;")

        def _primary_btn(text, h=42):
            b = QPushButton(text); b.setFixedHeight(h)
            b.setFocusPolicy(Qt.NoFocus); b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {ACCENT},stop:1 {ACCENT2}); color: #ffffff; border: none;"
                f" border-radius: 10px; font-size: 14px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 #ad5434,stop:1 #c46444); }}"
            )
            return b

        # ── ACCOUNT ──────────────────────────────────────────────────────────
        bl.addWidget(_section('Account'))

        ec = _card(); ecl = QVBoxLayout(ec)
        ecl.setContentsMargins(20, 18, 20, 20); ecl.setSpacing(10)
        ecl.addWidget(_card_title('Change Email'))
        new_email_f = _field('New email address')
        email_pw_f  = _field('Current password (to confirm)', password=True)
        email_msg   = _msg()
        save_email  = _primary_btn('Update Email')
        for w in (new_email_f, email_pw_f, email_msg, save_email): ecl.addWidget(w)
        def _do_email():
            ok, err = account_store.change_email(
                account_store.current_email(), new_email_f.text().strip(), email_pw_f.text())
            if ok:
                _show(email_msg, 'Email updated.', True)
                new_email_f.clear(); email_pw_f.clear()
                self._email_lbl.setText(account_store.current_email())
            else:
                _show(email_msg, err, False)
        save_email.clicked.connect(_do_email)
        bl.addWidget(ec)

        pc = _card(); pcl = QVBoxLayout(pc)
        pcl.setContentsMargins(20, 18, 20, 20); pcl.setSpacing(10)
        pcl.addWidget(_card_title('Change Password'))
        cur_pw_f = _field('Current password', password=True)
        new_pw_f = _field('New password', password=True)
        con_pw_f = _field('Confirm new password', password=True)
        pw_msg   = _msg()
        save_pw  = _primary_btn('Update Password')
        for w in (cur_pw_f, new_pw_f, con_pw_f, pw_msg, save_pw): pcl.addWidget(w)
        def _do_pw():
            if new_pw_f.text() != con_pw_f.text():
                _show(pw_msg, 'New passwords do not match.', False); return
            ok, err = account_store.change_password(
                account_store.current_email(), cur_pw_f.text(), new_pw_f.text())
            if ok:
                _show(pw_msg, 'Password updated.', True)
                cur_pw_f.clear(); new_pw_f.clear(); con_pw_f.clear()
            else:
                _show(pw_msg, err, False)
        save_pw.clicked.connect(_do_pw)
        bl.addWidget(pc)

        # ── NOTIFICATIONS ─────────────────────────────────────────────────────
        bl.addWidget(_section('Notifications'))

        nc = _card(); ncl = QVBoxLayout(nc)
        ncl.setContentsMargins(20, 18, 20, 20); ncl.setSpacing(10)
        ncl.addWidget(_card_title('Alert Phone Numbers'))
        hint = QLabel(
            'These numbers receive WhatsApp alerts when a seizure is detected. '
            'Add parents, caregivers, or anyone who should be notified.')
        hint.setWordWrap(True)
        hint.setStyleSheet(f'color: {MUTED}; font-size: 12px;')
        ncl.addWidget(hint)

        phones_ctr = QWidget(); phones_ctr.setStyleSheet("background: transparent;")
        phones_vl = QVBoxLayout(phones_ctr)
        phones_vl.setContentsMargins(0, 0, 0, 0); phones_vl.setSpacing(6)
        ncl.addWidget(phones_ctr)

        def _refresh_phones():
            while phones_vl.count():
                item = phones_vl.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            for ph in account_store.get_notification_phones():
                rw = QWidget(); rw.setStyleSheet("background: transparent;")
                rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(8)
                pl = QLabel(ph); pl.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
                rm = QPushButton('Remove'); rm.setObjectName('ghost')
                rm.setFocusPolicy(Qt.NoFocus); rm.setCursor(Qt.PointingHandCursor)
                rm.setFixedHeight(28)
                rm.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {MUTED}; font-size: 11px;"
                    f" border: 1px solid {BORDER}; border-radius: 6px; padding: 0 8px; }}"
                    f"QPushButton:hover {{ color: {DANGER}; border-color: {DANGER}; }}"
                )
                def _rm(_, p=ph):
                    phones = [x for x in account_store.get_notification_phones() if x != p]
                    account_store.save_notification_phones(phones)
                    _refresh_phones()
                rm.clicked.connect(_rm)
                rl.addWidget(pl, stretch=1); rl.addWidget(rm)
                phones_vl.addWidget(rw)

        _refresh_phones()

        add_row = QHBoxLayout()
        new_phone_f = _field('+1 (555) 123-4567')
        new_phone_f.setFixedHeight(40)
        add_btn = QPushButton('Add')
        add_btn.setFixedHeight(40); add_btn.setFocusPolicy(Qt.NoFocus)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT2}); color: #ffffff; border: none;"
            f" border-radius: 10px; font-size: 13px; font-weight: bold; padding: 0 18px; }}"
            f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 #ad5434,stop:1 #c46444); }}"
        )
        def _add_phone():
            ph = new_phone_f.text().strip()
            if not ph: return
            phones = account_store.get_notification_phones()
            if ph not in phones: phones.append(ph)
            account_store.save_notification_phones(phones)
            new_phone_f.clear(); _refresh_phones()
        add_btn.clicked.connect(_add_phone)
        new_phone_f.returnPressed.connect(_add_phone)
        add_row.addWidget(new_phone_f, stretch=1); add_row.addWidget(add_btn)
        ncl.addLayout(add_row)
        bl.addWidget(nc)

        # ── APPEARANCE ────────────────────────────────────────────────────────
        bl.addWidget(_section('Appearance'))

        ac = _card(); acl = QVBoxLayout(ac)
        acl.setContentsMargins(20, 18, 20, 20); acl.setSpacing(12)
        acl.addWidget(_card_title('Theme'))
        theme_row = QHBoxLayout(); theme_row.setSpacing(8)
        light_btn = QPushButton('Light'); light_btn.setCheckable(True)
        dark_btn  = QPushButton('Dark');  dark_btn.setCheckable(True)
        for b in (light_btn, dark_btn):
            b.setFocusPolicy(Qt.NoFocus); b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(36)
            b.setStyleSheet(
                f"QPushButton {{ background: {'rgba(60,55,50,0.4)' if IS_DARK else 'rgba(177,173,161,0.18)'};"
                f" color: {MUTED}; border: 1.5px solid {BORDER}; border-radius: 8px;"
                " padding: 0 20px; font-weight: 600; }"
                f"QPushButton:checked {{ background: {ACCENT}; color: #ffffff; border-color: {ACCENT}; }}"
            )
        (dark_btn if IS_DARK else light_btn).setChecked(True)
        theme_msg = QLabel(''); theme_msg.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        def _set_theme(name):
            from ui import theme as _t
            _t.set_active(name)  # updates theme module vars in-process
            light_btn.setChecked(name == 'light'); dark_btn.setChecked(name == 'dark')
            QTimer.singleShot(0, self._refresh)  # rebuild after current event finishes
        light_btn.clicked.connect(lambda: _set_theme('light'))
        dark_btn.clicked.connect(lambda: _set_theme('dark'))
        theme_row.addWidget(light_btn); theme_row.addWidget(dark_btn); theme_row.addStretch()
        acl.addLayout(theme_row); acl.addWidget(theme_msg)
        bl.addWidget(ac)

        # ── Sign out ──────────────────────────────────────────────────────────
        bl.addSpacing(8)
        so = QPushButton('Sign Out')
        so.setFixedHeight(44); so.setFocusPolicy(Qt.NoFocus); so.setCursor(Qt.PointingHandCursor)
        so.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {DANGER};"
            f" border: 1px solid rgba(185,28,28,0.25); border-radius: 10px;"
            " font-size: 13px; font-weight: bold; padding: 0 20px; }"
            f"QPushButton:hover {{ background: rgba(185,28,28,0.06); }}"
        )
        so.clicked.connect(self._sign_out)
        bl.addWidget(so)
        bl.addStretch()
        return scroll

    def _build_card(self, patient: dict) -> '_PatientCard':
        return _PatientCard(
            patient=patient,
            on_start=self._start,
            on_wizard=self._run_wizard,
            on_remove=self._remove,
            on_edit_avatar=self._edit_avatar,
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add_patient(self):
        dlg = _AddDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        patient = account_store.add_patient(dlg.name, dlg.age)
        avatar = dlg.avatar
        if avatar:
            if avatar.get('type') == 'photo' and avatar.get('path'):
                dest = account_store.save_avatar_photo(patient['id'], avatar['path'])
                avatar = {'type': 'photo', 'path': dest}
            patient['avatar'] = avatar
            account_store.save_patient(patient)
        self._run_wizard(patient)

    def _edit_avatar(self, patient: dict):
        dlg = _AvatarEditDialog(patient.get('avatar'), self)
        if dlg.exec() != QDialog.Accepted:
            return
        avatar = dlg.avatar
        if avatar:
            if avatar.get('type') == 'photo' and avatar.get('path'):
                # Only copy if it's a new file (not already in data/avatars)
                avatars_dir = str(account_store.DATA_DIR / 'avatars')
                if not avatar['path'].startswith(avatars_dir):
                    dest = account_store.save_avatar_photo(patient['id'], avatar['path'])
                    avatar = {'type': 'photo', 'path': dest}
            patient['avatar'] = avatar
            account_store.save_patient(patient)
        self._refresh()

    def _run_wizard(self, patient: dict):
        from ui.setup_wizard import SetupWizard
        self._wizard_window = SetupWizard(
            client=self.client,
            twilio_client=self.twilio_client,
            patient=patient,
        )
        self._wizard_window.setAttribute(Qt.WA_DeleteOnClose)
        # Qt auto-disconnects when either object is destroyed — safe to connect directly
        self._wizard_window.destroyed.connect(self._on_wizard_closed)
        self.hide()
        self._wizard_window.show()

    def _on_wizard_closed(self):
        self._refresh()
        self.show()

    def _remove(self, patient: dict):
        account_store.delete_patient(patient['id'])
        self._refresh()


    def _start(self, patient: dict):
        from ui.menu import EpiGuardMenu
        from datetime import datetime
        refreshed = account_store.get_patient(patient['id'])
        p = refreshed or patient
        
        today = datetime.now().strftime('%Y-%m-%d')
        last_survey = p.get('last_daily_survey_date')
        
        if last_survey == today:
            prompt = _CheckinPromptDialog(p.get('name', ''), self)
            if prompt.exec() == QDialog.Accepted:
                if prompt.result_action == 'start':
                    # Directly start monitoring using the cached last config
                    self.result = {'patient': p, 'config': p.get('last_daily_survey_config', {})}
                    self.close()
                    return
                elif prompt.result_action == 'retake':
                    pass # Continue to menu
            else:
                return # Cancelled
                
        self._checkin_window = EpiGuardMenu(client=self.client, mode='checkin', patient_name=p.get('name', ''))
        self._checkin_window.setAttribute(Qt.WA_DeleteOnClose)
        self._checkin_window.done.connect(lambda config: self._on_checkin_done(p, config))
        self.hide()
        self._checkin_window.show()

    def _on_checkin_done(self, patient: dict, config):
        if config is not None:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            patient['last_daily_survey_date'] = today
            patient['last_daily_survey_config'] = config
            account_store.save_patient(patient)
            
            self.result = {'patient': patient, 'config': config}
            self.close()   # closes patients screen → app.exec() returns
        else:
            self.show()    # user pressed X → go back to patient selection

    def _header_btn_style(self, muted=False):
        color = MUTED if muted else ACCENT
        hover = TEXT if muted else ACCENT2
        return (
            f"QPushButton {{ background: transparent; color: {color}; border: none;"
            f" border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 10px; }}"
            f"QPushButton:hover {{ color: {hover}; background: rgba(193,95,60,0.07); }}"
        )

    def _toggle_settings(self):
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._brand_lbl.setText('Settings')
            self._settings_btn.setText('← Back')
            self._email_lbl.hide()
        else:
            self._stack.setCurrentIndex(0)
            self._brand_lbl.setText('EpiGuard')
            self._settings_btn.setText('⚙')
            self._email_lbl.setText(account_store.current_email())
            self._email_lbl.show()

    def _sign_out(self):
        account_store.logout()
        self.result = None
        self.close()


def show_patients(client=None, twilio_client=None) -> dict | None:
    app = QApplication.instance() or QApplication(sys.argv)
    win = PatientsScreen(client=client, twilio_client=twilio_client)
    win.show()
    app.exec()
    return win.result
