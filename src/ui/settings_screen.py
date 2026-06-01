"""Settings screen — account, notifications, appearance."""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

from core import account_store
from ui import theme

BG      = theme.BG
CARD    = theme.CARD
TEXT    = theme.TEXT
MUTED   = theme.MUTED
ACCENT  = theme.ACCENT
ACCENT2 = theme.ACCENT2
SURFACE = theme.SURFACE
BORDER  = theme.BORDER
DANGER  = theme.DANGER
SUCCESS = theme.SUCCESS
INPUT_BG = theme.INPUT_BG
IS_DARK  = theme.IS_DARK


def _style():
    return f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {TEXT};
    font-family: 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLineEdit {{
    background-color: {INPUT_BG}; color: {TEXT};
    border: 1.5px solid {BORDER}; border-radius: 10px;
    padding: 12px 16px; font-size: 14px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; background-color: {INPUT_BG}; }}
QPushButton {{ border: none; border-radius: 10px; font-size: 13px;
    font-weight: bold; padding: 10px 20px; }}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});
    color: #ffffff; }}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444); }}
QPushButton#secondary {{
    background: {'rgba(60,55,50,0.4)' if IS_DARK else 'rgba(177,173,161,0.18)'};
    color: {TEXT}; border: 1px solid {BORDER}; }}
QPushButton#secondary:hover {{
    background: {'rgba(70,65,60,0.5)' if IS_DARK else 'rgba(177,173,161,0.3)'}; }}
QPushButton#danger {{
    background: transparent; color: {DANGER};
    border: 1px solid {'rgba(248,113,113,0.3)' if IS_DARK else 'rgba(185,28,28,0.2)'}; }}
QPushButton#danger:hover {{
    background: {'rgba(248,113,113,0.1)' if IS_DARK else 'rgba(185,28,28,0.06)'}; }}
QPushButton#remove {{
    background: transparent; color: {MUTED};
    border: 1px solid {BORDER}; border-radius: 8px;
    font-size: 11px; padding: 4px 10px; }}
QPushButton#remove:hover {{ color: {DANGER}; border-color: {DANGER}; }}
QPushButton#chip_theme {{
    background: {'rgba(60,55,50,0.5)' if IS_DARK else 'rgba(177,173,161,0.18)'};
    color: {MUTED}; border: 1.5px solid {BORDER};
    border-radius: 8px; padding: 8px 20px; font-weight: 600; }}
QPushButton#chip_theme:checked {{
    background: {ACCENT}; color: #ffffff; border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 4px; border-radius: 2px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame#card {{ background-color: {CARD}; border-radius: 14px;
    border: 1px solid {BORDER}; }}
"""


class SettingsScreen(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('EpiGuard — Settings')
        self.setFixedSize(540, 780)
        self.setStyleSheet(_style())
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 540) // 2, (screen.height() - 780) // 2)
        self._phone_rows = []
        self._build()
        # fade in
        eff = QGraphicsOpacityEffect(self.centralWidget())
        self.centralWidget().setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b'opacity', self)
        anim.setDuration(180); anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuart); anim.start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # accent stripe
        stripe = QWidget(); stripe.setFixedHeight(3)
        stripe.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT2});"
        )
        vbox.addWidget(stripe)

        # header
        hdr = QWidget()
        hdr.setFixedHeight(62)
        hdr.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(24, 0, 24, 0)
        hrow.setSpacing(10)
        logo = QLabel('EG')
        logo.setFixedSize(30, 30)
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont('', 11, QFont.Bold))
        logo.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {ACCENT},stop:1 {ACCENT2});"
            "color: #ffffff; border-radius: 8px;"
        )
        hrow.addWidget(logo)
        title = QLabel('Settings')
        title.setFont(QFont('', 16, QFont.Bold))
        hrow.addWidget(title)
        hrow.addStretch()
        close_btn = QPushButton('Done')
        close_btn.setFixedHeight(34)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ACCENT}; border: none;"
            f" font-size: 14px; font-weight: 600; padding: 0 10px; }}"
            f"QPushButton:hover {{ color: {ACCENT2}; }}"
        )
        close_btn.clicked.connect(self.close)
        hrow.addWidget(close_btn)
        vbox.addWidget(hdr)

        # scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget(); body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 32)
        bl.setSpacing(20)
        vbox.addWidget(scroll, stretch=1)
        scroll.setWidget(body)

        # ── ACCOUNT section ───────────────────────────────────────────────────
        bl.addWidget(self._section_label('Account'))

        # Change email card
        email_card = self._card()
        ec = QVBoxLayout(email_card)
        ec.setContentsMargins(18, 16, 18, 18)
        ec.setSpacing(10)
        ec.addWidget(self._card_title('Change Email'))
        self._new_email = self._input('New email address', placeholder='you@example.com')
        self._email_password = self._input('Current password (to confirm)', password=True)
        self._email_msg = self._msg_label()
        ec.addWidget(self._new_email)
        ec.addWidget(self._email_password)
        ec.addWidget(self._email_msg)
        save_email_btn = QPushButton('Update Email')
        save_email_btn.setObjectName('primary')
        save_email_btn.setFixedHeight(42)
        save_email_btn.setFocusPolicy(Qt.NoFocus)
        save_email_btn.clicked.connect(self._do_change_email)
        ec.addWidget(save_email_btn)
        bl.addWidget(email_card)

        # Change password card
        pw_card = self._card()
        pc = QVBoxLayout(pw_card)
        pc.setContentsMargins(18, 16, 18, 18)
        pc.setSpacing(10)
        pc.addWidget(self._card_title('Change Password'))
        self._cur_pw = self._input('Current password', password=True)
        self._new_pw = self._input('New password', password=True)
        self._confirm_pw = self._input('Confirm new password', password=True)
        self._pw_msg = self._msg_label()
        pc.addWidget(self._cur_pw)
        pc.addWidget(self._new_pw)
        pc.addWidget(self._confirm_pw)
        pc.addWidget(self._pw_msg)
        save_pw_btn = QPushButton('Update Password')
        save_pw_btn.setObjectName('primary')
        save_pw_btn.setFixedHeight(42)
        save_pw_btn.setFocusPolicy(Qt.NoFocus)
        save_pw_btn.clicked.connect(self._do_change_password)
        pc.addWidget(save_pw_btn)
        bl.addWidget(pw_card)

        # ── NOTIFICATIONS section ─────────────────────────────────────────────
        bl.addWidget(self._section_label('Notifications'))

        phones_card = self._card()
        phones_outer = QVBoxLayout(phones_card)
        phones_outer.setContentsMargins(18, 16, 18, 18)
        phones_outer.setSpacing(12)
        phones_outer.addWidget(self._card_title('Alert Phone Numbers'))
        hint = QLabel(
            'These numbers receive WhatsApp alerts when a seizure is detected. '
            'Add multiple people — parents, caregivers, or anyone who should know.'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f'color: {MUTED}; font-size: 12px;')
        phones_outer.addWidget(hint)

        # container for existing phone rows (rebuilt in _refresh_phones)
        self._phones_container = QWidget()
        self._phones_container.setStyleSheet("background: transparent;")
        self._phones_layout = QVBoxLayout(self._phones_container)
        self._phones_layout.setContentsMargins(0, 0, 0, 0)
        self._phones_layout.setSpacing(6)
        phones_outer.addWidget(self._phones_container)

        # add-new row
        add_row = QHBoxLayout()
        self._new_phone = QLineEdit()
        self._new_phone.setPlaceholderText('+1 (555) 123-4567')
        self._new_phone.setFixedHeight(40)
        add_row.addWidget(self._new_phone, stretch=1)
        add_phone_btn = QPushButton('Add')
        add_phone_btn.setObjectName('secondary')
        add_phone_btn.setFixedHeight(40)
        add_phone_btn.setFocusPolicy(Qt.NoFocus)
        add_phone_btn.clicked.connect(self._add_phone)
        add_row.addWidget(add_phone_btn)
        phones_outer.addLayout(add_row)
        self._phones_msg = self._msg_label()
        phones_outer.addWidget(self._phones_msg)
        bl.addWidget(phones_card)
        self._refresh_phones()

        # ── APPEARANCE section ────────────────────────────────────────────────
        bl.addWidget(self._section_label('Appearance'))

        appear_card = self._card()
        ac = QVBoxLayout(appear_card)
        ac.setContentsMargins(18, 16, 18, 18)
        ac.setSpacing(12)
        ac.addWidget(self._card_title('Theme'))

        toggle_row = QHBoxLayout()
        self._light_btn = QPushButton('Light')
        self._light_btn.setObjectName('chip_theme')
        self._light_btn.setCheckable(True)
        self._light_btn.setFocusPolicy(Qt.NoFocus)
        self._dark_btn = QPushButton('Dark')
        self._dark_btn.setObjectName('chip_theme')
        self._dark_btn.setCheckable(True)
        self._dark_btn.setFocusPolicy(Qt.NoFocus)
        if IS_DARK:
            self._dark_btn.setChecked(True)
        else:
            self._light_btn.setChecked(True)
        self._light_btn.clicked.connect(lambda: self._set_theme('light'))
        self._dark_btn.clicked.connect(lambda: self._set_theme('dark'))
        toggle_row.addWidget(self._light_btn)
        toggle_row.addWidget(self._dark_btn)
        toggle_row.addStretch()
        ac.addLayout(toggle_row)

        self._theme_msg = QLabel('')
        self._theme_msg.setStyleSheet(f'color: {MUTED}; font-size: 11px;')
        ac.addWidget(self._theme_msg)
        bl.addWidget(appear_card)

        # ── Sign out ──────────────────────────────────────────────────────────
        bl.addSpacing(8)
        signout_btn = QPushButton('Sign Out')
        signout_btn.setObjectName('danger')
        signout_btn.setFixedHeight(44)
        signout_btn.setFocusPolicy(Qt.NoFocus)
        signout_btn.clicked.connect(self._sign_out)
        bl.addWidget(signout_btn)
        bl.addStretch()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section_label(self, text):
        w = QWidget(); w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)
        bar = QWidget(); bar.setFixedSize(3, 14)
        bar.setStyleSheet(f"background: {ACCENT}; border-radius: 1px;")
        row.addWidget(bar, alignment=Qt.AlignVCenter)
        lbl = QLabel(text.upper())
        lbl.setFont(QFont('', 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {MUTED}; letter-spacing: 0.8px;")
        row.addWidget(lbl)
        row.addStretch()
        return w

    def _card(self):
        f = QFrame(); f.setObjectName('card')
        return f

    def _card_title(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont('', 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {TEXT};")
        return lbl

    def _input(self, label_text, placeholder='', password=False):
        field = QLineEdit()
        field.setPlaceholderText(placeholder or label_text)
        field.setFixedHeight(46)
        if password:
            field.setEchoMode(QLineEdit.Password)
        return field

    def _msg_label(self):
        lbl = QLabel('')
        lbl.setFont(QFont('', 11))
        lbl.setWordWrap(True)
        lbl.setFixedHeight(16)
        return lbl

    def _show_msg(self, lbl: QLabel, text: str, ok: bool):
        lbl.setText(text)
        lbl.setStyleSheet(f"color: {SUCCESS if ok else DANGER}; font-size: 11px;")

    # ── Phones ────────────────────────────────────────────────────────────────

    def _refresh_phones(self):
        # clear old rows
        while self._phones_layout.count():
            item = self._phones_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        phones = account_store.get_notification_phones()
        for phone in phones:
            row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            lbl = QLabel(phone)
            lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
            row.addWidget(lbl, stretch=1)
            rm = QPushButton('Remove')
            rm.setObjectName('remove')
            rm.setFocusPolicy(Qt.NoFocus)
            rm.clicked.connect(lambda _, p=phone: self._remove_phone(p))
            row.addWidget(rm)
            self._phones_layout.addWidget(row_w)

    def _add_phone(self):
        phone = self._new_phone.text().strip()
        if not phone:
            return
        phones = account_store.get_notification_phones()
        if phone in phones:
            self._show_msg(self._phones_msg, 'Already in the list.', False)
            return
        phones.append(phone)
        account_store.save_notification_phones(phones)
        self._new_phone.clear()
        self._phones_msg.setText('')
        self._refresh_phones()

    def _remove_phone(self, phone: str):
        phones = account_store.get_notification_phones()
        phones = [p for p in phones if p != phone]
        account_store.save_notification_phones(phones)
        self._refresh_phones()

    # ── Account actions ───────────────────────────────────────────────────────

    def _do_change_email(self):
        new_email = self._new_email.text().strip()
        password = self._email_password.text()
        ok, err = account_store.change_email(
            account_store.current_email(), new_email, password
        )
        if ok:
            self._show_msg(self._email_msg, 'Email updated.', True)
            self._new_email.clear()
            self._email_password.clear()
        else:
            self._show_msg(self._email_msg, err, False)

    def _do_change_password(self):
        cur = self._cur_pw.text()
        new = self._new_pw.text()
        confirm = self._confirm_pw.text()
        if new != confirm:
            self._show_msg(self._pw_msg, 'New passwords do not match.', False)
            return
        ok, err = account_store.change_password(account_store.current_email(), cur, new)
        if ok:
            self._show_msg(self._pw_msg, 'Password updated.', True)
            self._cur_pw.clear(); self._new_pw.clear(); self._confirm_pw.clear()
        else:
            self._show_msg(self._pw_msg, err, False)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _set_theme(self, name: str):
        from ui import theme as _t
        _t.save_name(name)
        self._light_btn.setChecked(name == 'light')
        self._dark_btn.setChecked(name == 'dark')
        self._theme_msg.setText('Restart the app to apply the new theme.')

    # ── Sign out ──────────────────────────────────────────────────────────────

    def _sign_out(self):
        account_store.logout()
        # Signal the patients screen to close entirely by setting a flag
        self.setProperty('signed_out', True)
        self.close()
