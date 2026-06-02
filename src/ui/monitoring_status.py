from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

_BG     = "#f4f3ee"
_BORDER = "rgba(193,95,60,0.4)"


class MonitoringStatusWindow(QWidget):
    def __init__(self, patient_name="", on_stop=None, on_feedback=None):
        super().__init__()
        self.on_stop     = on_stop
        self.on_feedback = on_feedback
        self.setWindowTitle("EpiGuard Status")
        self.setFixedWidth(320)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet(
            f"QWidget {{ background: {_BG}; }}"
            "QLabel  { border: none; background: transparent; }"
            "QPushButton { border: none; }"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(10)

        # ── Name ──────────────────────────────────────────────────────────
        self._name_lbl = QLabel(f"Monitoring {patient_name}")
        self._name_lbl.setFont(QFont('', 14, QFont.Bold))
        self._name_lbl.setStyleSheet("color: #1c1917;")
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._name_lbl)

        # ── Spinner ───────────────────────────────────────────────────────
        self._spinner = QLabel("⠋  Live")
        self._spinner.setFont(QFont('', 12))
        self._spinner.setStyleSheet("color: #c15f3c;")
        self._spinner.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._spinner)

        # ── Pre-ictal banner (hidden) ──────────────────────────────────────
        self._pi_banner = QLabel("")
        self._pi_banner.setFont(QFont('', 11, QFont.Bold))
        self._pi_banner.setAlignment(Qt.AlignCenter)
        self._pi_banner.setStyleSheet(
            "background: #fef3c7; color: #92400e; border-radius: 8px;"
            "padding: 6px 10px; border: 1px solid #fcd34d;"
        )
        self._pi_banner.hide()
        self._layout.addWidget(self._pi_banner)

        # ── Alert card (hidden) ───────────────────────────────────────────
        self._alert_card = QFrame()
        self._alert_card.setStyleSheet(
            "QFrame { background: #fef2f2; border-radius: 12px; border: 1px solid #fca5a5; }"
            "QLabel { background: transparent; border: none; }"
        )
        ac = QVBoxLayout(self._alert_card)
        ac.setContentsMargins(14, 12, 14, 12)
        ac.setSpacing(6)

        # Title row
        self._alert_title = QLabel("⚠  Seizure Risk Detected")
        self._alert_title.setFont(QFont('', 13, QFont.Bold))
        self._alert_title.setStyleSheet("color: #b91c1c;")
        self._alert_title.setAlignment(Qt.AlignCenter)
        ac.addWidget(self._alert_title)

        # Type badge
        self._alert_type = QLabel("")
        self._alert_type.setFont(QFont('', 11, QFont.Bold))
        self._alert_type.setStyleSheet(
            "color: #7f1d1d; background: #fee2e2; border-radius: 6px; padding: 2px 8px;"
        )
        self._alert_type.setAlignment(Qt.AlignCenter)
        ac.addWidget(self._alert_type)

        # SMS / countdown status
        self._alert_sms = QLabel("")
        self._alert_sms.setFont(QFont('', 10))
        self._alert_sms.setStyleSheet("color: #991b1b;")
        self._alert_sms.setAlignment(Qt.AlignCenter)
        ac.addWidget(self._alert_sms)

        # Contributors section (hidden until populated)
        self._contrib_widget = QWidget()
        self._contrib_widget.setStyleSheet("background: transparent;")
        self._contrib_layout = QVBoxLayout(self._contrib_widget)
        self._contrib_layout.setContentsMargins(0, 4, 0, 0)
        self._contrib_layout.setSpacing(3)

        contrib_header = QLabel("Top signals")
        contrib_header.setFont(QFont('', 9))
        contrib_header.setStyleSheet("color: #b91c1c; letter-spacing: 0.5px;")
        self._contrib_layout.addWidget(contrib_header)

        # Placeholder rows — filled in show_alert()
        self._contrib_rows = []
        for _ in range(3):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel()
            lbl.setFont(QFont('', 11))
            lbl.setStyleSheet("color: #7f1d1d;")
            pct = QLabel()
            pct.setFont(QFont('', 11, QFont.Bold))
            pct.setStyleSheet("color: #b91c1c;")
            pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lbl, stretch=1)
            row.addWidget(pct)
            self._contrib_rows.append((lbl, pct))
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_w.setLayout(row)
            self._contrib_layout.addWidget(row_w)

        self._contrib_widget.hide()
        ac.addWidget(self._contrib_widget)

        self._alert_card.hide()
        self._layout.addWidget(self._alert_card)

        # ── Feedback buttons (hidden, stacked vertically) ─────────────────
        self._yes_btn = QPushButton("✓   Real seizure")
        self._no_btn  = QPushButton("✗   False alarm")
        for btn in (self._yes_btn, self._no_btn):
            btn.setFont(QFont('', 12, QFont.Bold))
            btn.setFixedHeight(40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.hide()
        self._yes_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #15803d; }"
        )
        self._no_btn.setStyleSheet(
            "QPushButton { background: #6b7280; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #4b5563; }"
        )
        self._yes_btn.clicked.connect(lambda: self._on_feedback(True))
        self._no_btn.clicked.connect(lambda: self._on_feedback(False))
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
        self._alert_type.setText(f"{alert_type.title()} seizure")
        self._alert_sms.setText("SMS sent ✓" if sms_sent else "Waiting for response…")

        if contributors:
            for i, (lbl_w, pct_w) in enumerate(self._contrib_rows):
                if i < len(contributors):
                    lbl_w.setText(contributors[i][0])
                    pct_w.setText(f"{contributors[i][1]}%")
                    lbl_w.parent().show()
                else:
                    lbl_w.parent().hide()
            self._contrib_widget.show()
        else:
            self._contrib_widget.hide()

        self._alert_card.show()
        self._yes_btn.show()
        self._no_btn.show()
        self.adjustSize()

    def update_countdown(self, secs: int):
        if not self._alert_card.isVisible():
            return
        if secs == 0:
            self._alert_sms.setText("SMS sent automatically ✓")
        else:
            self._alert_sms.setText(f"Sending SMS in {secs}s…")
        self.adjustSize()

    # ── Private ───────────────────────────────────────────────────────────

    def _tick(self):
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_frames)
        self._spinner.setText(f"{self._spin_frames[self._spin_idx]}  Live")

    def _stop_clicked(self):
        self.stop_btn.setText("Stopping…")
        self.stop_btn.setEnabled(False)
        if self.on_stop:
            self.on_stop()

    def _on_feedback(self, correct: bool):
        self._alert_card.hide()
        self._contrib_widget.hide()
        self._yes_btn.hide()
        self._no_btn.hide()
        self.adjustSize()
        if self.on_feedback:
            self.on_feedback(correct)
