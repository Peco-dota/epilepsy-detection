from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

_BG      = "#f4f3ee"
_BORDER  = "rgba(193,95,60,0.4)"


class MonitoringStatusWindow(QWidget):
    def __init__(self, patient_name="", on_stop=None, on_feedback=None):
        super().__init__()
        self.on_stop     = on_stop
        self.on_feedback = on_feedback  # callable(correct: bool)
        self.setWindowTitle("EpiGuard Status")
        self.setMinimumWidth(300)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet(
            f"QWidget {{ background: {_BG}; border: 1px solid {_BORDER}; border-radius: 14px; }}"
            "QLabel  { border: none; background: transparent; }"
            "QPushButton { border: none; }"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(8)

        # ── Name ──────────────────────────────────────────────────────────
        self._name_lbl = QLabel(f"Monitoring {patient_name}...")
        self._name_lbl.setFont(QFont('', 15, QFont.Bold))
        self._name_lbl.setStyleSheet("color: #1c1917;")
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._name_lbl)

        # ── Spinner ───────────────────────────────────────────────────────
        self._spinner = QLabel("⠋  Live")
        self._spinner.setFont(QFont('', 13))
        self._spinner.setStyleSheet("color: #c15f3c;")
        self._spinner.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._spinner)

        # ── Pre-ictal banner (hidden by default) ──────────────────────────
        self._pi_banner = QLabel("")
        self._pi_banner.setFont(QFont('', 11, QFont.Bold))
        self._pi_banner.setAlignment(Qt.AlignCenter)
        self._pi_banner.setStyleSheet(
            "background: #fef3c7; color: #92400e; border-radius: 8px; padding: 6px;"
        )
        self._pi_banner.hide()
        self._layout.addWidget(self._pi_banner)

        # ── Alert card (hidden by default) ────────────────────────────────
        self._alert_card = QFrame()
        self._alert_card.setStyleSheet(
            "QFrame { background: #fef2f2; border-radius: 10px; border: 1px solid #fca5a5; }"
            "QLabel { background: transparent; border: none; }"
        )
        ac = QVBoxLayout(self._alert_card)
        ac.setContentsMargins(12, 10, 12, 10)
        ac.setSpacing(2)

        self._alert_title = QLabel("⚠  Seizure Risk Detected")
        self._alert_title.setFont(QFont('', 13, QFont.Bold))
        self._alert_title.setStyleSheet("color: #b91c1c;")
        self._alert_title.setAlignment(Qt.AlignCenter)

        self._alert_type = QLabel("")
        self._alert_type.setFont(QFont('', 11))
        self._alert_type.setStyleSheet("color: #7f1d1d;")
        self._alert_type.setAlignment(Qt.AlignCenter)

        self._alert_sms = QLabel("")
        self._alert_sms.setFont(QFont('', 10))
        self._alert_sms.setStyleSheet("color: #b91c1c;")
        self._alert_sms.setAlignment(Qt.AlignCenter)

        self._alert_contrib = QLabel("")
        self._alert_contrib.setFont(QFont('', 10))
        self._alert_contrib.setStyleSheet("color: #7f1d1d;")
        self._alert_contrib.setAlignment(Qt.AlignCenter)
        self._alert_contrib.setWordWrap(True)

        ac.addWidget(self._alert_title)
        ac.addWidget(self._alert_type)
        ac.addWidget(self._alert_sms)
        ac.addWidget(self._alert_contrib)
        self._alert_card.hide()
        self._layout.addWidget(self._alert_card)

        # ── Feedback buttons (hidden by default, stacked vertically) ──────
        self._yes_btn = QPushButton("✓   Real seizure")
        self._no_btn  = QPushButton("✗   False alarm")
        self._yes_btn.setFont(QFont('', 12, QFont.Bold))
        self._no_btn.setFont(QFont('', 12, QFont.Bold))
        self._yes_btn.setFixedHeight(40)
        self._no_btn.setFixedHeight(40)
        self._yes_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #15803d; }"
        )
        self._no_btn.setStyleSheet(
            "QPushButton { background: #6b7280; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #4b5563; }"
        )
        self._yes_btn.setCursor(Qt.PointingHandCursor)
        self._no_btn.setCursor(Qt.PointingHandCursor)
        self._yes_btn.clicked.connect(lambda: self._on_feedback(True))
        self._no_btn.clicked.connect(lambda: self._on_feedback(False))
        self._yes_btn.hide()
        self._no_btn.hide()
        self._layout.addWidget(self._yes_btn)
        self._layout.addWidget(self._no_btn)

        # ── Stop button ───────────────────────────────────────────────────
        self.stop_btn = QPushButton("Stop Monitoring")
        self.stop_btn.setFont(QFont('', 12, QFont.Bold))
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setStyleSheet(
            "QPushButton { background: #c15f3c; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #ad5434; }"
        )
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self._stop_clicked)
        self._layout.addWidget(self.stop_btn)

        self._spin_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spin_idx = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

        self.adjustSize()

    # ── Public API ────────────────────────────────────────────────────────

    def show_pre_ictal_warning(self, stage_label: str):
        self._pi_banner.setText(f"⚠  Pre-ictal warning · {stage_label}")
        self._pi_banner.show()
        self.adjustSize()

    def clear_pre_ictal_warning(self):
        self._pi_banner.hide()
        self.adjustSize()

    def show_alert(self, alert_type: str, sms_sent: bool,
                   contributors: list | None = None):
        self._alert_type.setText(f"{alert_type.title()} seizure risk")
        self._alert_sms.setText("SMS alert sent" if sms_sent else "SMS not configured")
        if contributors:
            lines = "  ·  ".join(f"{lbl} {pct}%" for lbl, pct in contributors)
            self._alert_contrib.setText(lines)
            self._alert_contrib.show()
        else:
            self._alert_contrib.hide()
        self._alert_card.show()
        self._yes_btn.show()
        self._no_btn.show()
        self.adjustSize()

    # ── Private ───────────────────────────────────────────────────────────

    def _tick(self):
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_frames)
        self._spinner.setText(f"{self._spin_frames[self._spin_idx]}  Live")

    def _stop_clicked(self):
        self.stop_btn.setText("Stopping...")
        self.stop_btn.setEnabled(False)
        if self.on_stop:
            self.on_stop()

    def _on_feedback(self, correct: bool):
        self._alert_card.hide()
        self._alert_contrib.hide()
        self._yes_btn.hide()
        self._no_btn.hide()
        self.adjustSize()
        if self.on_feedback:
            self.on_feedback(correct)
