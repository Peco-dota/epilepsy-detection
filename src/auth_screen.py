"""Login / register screen."""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

import account_store

BG      = '#f4f3ee'
TEXT    = '#1c1917'
MUTED   = '#8a847a'
ACCENT  = '#c15f3c'
ACCENT2 = '#d4724e'
DANGER  = '#b91c1c'

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: -apple-system, 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif;
}}
QLabel {{ background: transparent; color: {TEXT}; }}
QLineEdit {{
    background-color: #ffffff;
    color: {TEXT};
    border: 1px solid rgba(177,173,161,0.55);
    border-radius: 12px;
    padding: 14px 18px;
    font-size: 15px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
    background-color: rgba(193,95,60,0.04);
}}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});
    color: #ffffff;
    border-radius: 12px;
    font-size: 15px;
    font-weight: bold;
    border: none;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444);
}}
QPushButton#link {{
    background: transparent;
    color: {ACCENT};
    border: none;
    font-size: 13px;
    padding: 0;
    text-decoration: underline;
}}
QPushButton#link:hover {{ color: #ad5434; }}
"""


class AuthScreen(QMainWindow):
    def __init__(self):
        super().__init__()
        self.result = None
        self._mode = 'login'
        self.setWindowTitle('EpiGuard')
        self.setFixedSize(460, 560)
        self.setStyleSheet(STYLE)
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 460) // 2, (screen.height() - 560) // 2)
        self._build()

    def _build(self):
        if self.centralWidget():
            self.centralWidget().deleteLater()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(64, 44, 64, 44)
        layout.setSpacing(0)
        layout.addStretch(1)

        logo = QLabel('🛡️')
        logo.setFont(QFont('-apple-system', 48))
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet('background: transparent;')
        logo.setFixedHeight(64)
        layout.addWidget(logo)
        layout.addSpacing(12)

        title = QLabel('EpiGuard')
        title.setFont(QFont('-apple-system', 28, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f'background: transparent; color: {TEXT};')
        layout.addWidget(title)
        layout.addSpacing(6)

        subtitle_text = 'Sign in to continue' if self._mode == 'login' else 'Create your account'
        subtitle = QLabel(subtitle_text)
        subtitle.setFont(QFont('-apple-system', 13))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f'background: transparent; color: {MUTED};')
        layout.addWidget(subtitle)
        layout.addStretch(1)

        # Email
        lbl = QLabel('EMAIL')
        lbl.setFont(QFont('-apple-system', 11))
        lbl.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        layout.addWidget(lbl)
        layout.addSpacing(6)
        self._email = QLineEdit()
        self._email.setPlaceholderText('you@example.com')
        self._email.setFixedHeight(50)
        layout.addWidget(self._email)
        layout.addSpacing(14)

        # Password
        lbl2 = QLabel('PASSWORD')
        lbl2.setFont(QFont('-apple-system', 11))
        lbl2.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        layout.addWidget(lbl2)
        layout.addSpacing(6)
        self._password = QLineEdit()
        self._password.setPlaceholderText('••••••••')
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setFixedHeight(50)
        self._password.returnPressed.connect(self._submit)
        layout.addWidget(self._password)

        # Confirm password (register only)
        if self._mode == 'register':
            layout.addSpacing(14)
            lbl3 = QLabel('CONFIRM PASSWORD')
            lbl3.setFont(QFont('-apple-system', 11))
            lbl3.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
            layout.addWidget(lbl3)
            layout.addSpacing(6)
            self._confirm = QLineEdit()
            self._confirm.setPlaceholderText('••••••••')
            self._confirm.setEchoMode(QLineEdit.Password)
            self._confirm.setFixedHeight(50)
            self._confirm.returnPressed.connect(self._submit)
            layout.addWidget(self._confirm)

        layout.addSpacing(6)
        self._error = QLabel('')
        self._error.setFont(QFont('-apple-system', 12))
        self._error.setStyleSheet(f'color: {DANGER};')
        self._error.setAlignment(Qt.AlignCenter)
        self._error.setWordWrap(True)
        self._error.setFixedHeight(18)
        layout.addWidget(self._error)
        layout.addSpacing(14)

        action_lbl = 'Sign in' if self._mode == 'login' else 'Create account'
        submit_btn = QPushButton(action_lbl)
        submit_btn.setObjectName('primary')
        submit_btn.setFixedHeight(50)
        submit_btn.clicked.connect(self._submit)
        layout.addWidget(submit_btn)
        layout.addSpacing(16)

        toggle_row = QHBoxLayout()
        toggle_row.setAlignment(Qt.AlignCenter)
        hint_text = "Don't have an account?" if self._mode == 'login' else 'Already have an account?'
        toggle_lbl = QLabel(hint_text)
        toggle_lbl.setFont(QFont('-apple-system', 13))
        toggle_lbl.setStyleSheet(f'color: {MUTED};')
        toggle_row.addWidget(toggle_lbl)
        toggle_row.addSpacing(6)
        link_text = 'Create one' if self._mode == 'login' else 'Sign in'
        link_btn = QPushButton(link_text)
        link_btn.setObjectName('link')
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.clicked.connect(self._toggle)
        toggle_row.addWidget(link_btn)
        layout.addLayout(toggle_row)
        layout.addStretch(2)

        effect = QGraphicsOpacityEffect(root)
        root.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b'opacity', root)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuart)
        anim.start()

    def _toggle(self):
        self._mode = 'register' if self._mode == 'login' else 'login'
        self._build()

    def _submit(self):
        email = self._email.text().strip()
        password = self._password.text()

        if self._mode == 'login':
            ok, err = account_store.login(email, password)
        else:
            confirm = getattr(self, '_confirm', None)
            if confirm and confirm.text() != password:
                self._error.setText('Passwords do not match')
                return
            ok, err = account_store.register(email, password)

        if ok:
            self.result = account_store.current_email()
            self.close()
        else:
            self._error.setText(err)


def show_auth() -> str | None:
    """Returns logged-in email, or None if window was closed."""
    saved = account_store.current_email()
    if saved:
        return saved
    app = QApplication.instance() or QApplication(sys.argv)
    win = AuthScreen()
    win.show()
    app.exec()
    return win.result
