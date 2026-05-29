from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QSlider, QScrollArea, QFrame,
    QSizePolicy, QButtonGroup, QAbstractButton
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import sys
import json
import re

STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'SF Pro Text', 'Segoe UI', sans-serif;
}
QLabel { color: #cdd6f4; }
QTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
}
QTextEdit:focus { border: 1px solid #89b4fa; }
QPushButton {
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
    border: none;
}
QPushButton#primary {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QPushButton#primary:hover { background-color: #b4befe; }
QPushButton#primary:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#secondary {
    background-color: #45475a;
    color: #cdd6f4;
}
QPushButton#secondary:hover { background-color: #585b70; }
QScrollArea { border: none; background-color: transparent; }
QScrollBar:vertical {
    background: #313244; width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical { background: #585b70; border-radius: 3px; }
QSlider::groove:horizontal {
    height: 4px; background: #45475a; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
}
QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 2px; }
QFrame#card { background-color: #313244; border-radius: 12px; }
QPushButton#chip {
    background-color: #313244;
    color: #a6adc8;
    border: 1px solid #45475a;
    border-radius: 20px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: normal;
}
QPushButton#chip:checked {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: 1px solid #89b4fa;
    font-weight: bold;
}
QPushButton#chip:hover { border-color: #89b4fa; }
"""


class AIWorker(QThread):
    finished = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn() or "")
        except Exception:
            self.finished.emit("")


class _Chip(QPushButton):
    """Toggleable chip button."""
    def __init__(self, label):
        super().__init__(label)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class EpiGuardMenu(QMainWindow):
    def __init__(self, client=None):
        super().__init__()
        self.client = client
        self.result = None
        self.context_multipliers = {}   # signal → float multiplier from context
        self.context_summary = ""
        self.defaults = {
            'blink_detection': 50, 'eye_tracking': 50, 'face_freeze': 50,
            'face_asymmetry': 50, 'seizure_twitch': 50, 'bpm': 50, 'face_color': 50
        }
        self.sliders = {}

        self.setWindowTitle("EPIGUARD")
        self.setFixedSize(900, 680)
        self.setStyleSheet(STYLE)
        self._center()
        self._show_screen_0()

    def _center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    def _clear(self):
        if self.centralWidget():
            self.centralWidget().deleteLater()

    def _step_indicator(self, current):
        """Returns a widget showing step dots: ● ● ○ etc."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        labels = ["Context", "Symptoms", "Thresholds"]
        for i, lbl in enumerate(labels):
            dot = QLabel(f"{'●' if i == current else '○'}  {lbl}")
            dot.setStyleSheet(
                f"color: {'#89b4fa' if i == current else '#45475a'}; font-size: 12px;"
            )
            row.addWidget(dot)
        row.addStretch()
        w = QWidget()
        w.setLayout(row)
        return w

    # ── Screen 0: context check-in ───────────────────────────────────────
    def _show_screen_0(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(16)

        layout.addWidget(self._step_indicator(0))
        layout.addSpacing(10)

        title = QLabel("EPIGUARD")
        title.setFont(QFont("SF Pro Display", 32, QFont.Bold))
        title.setStyleSheet("color: #89b4fa;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Before we start, tell us how the patient is doing today.")
        sub.setFont(QFont("SF Pro Text", 13))
        sub.setStyleSheet("color: #6c7086;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(8)

        # ── Sleep ────────────────────────────────────────────────────────
        sleep_lbl = QLabel("🌙  How much did they sleep last night?")
        sleep_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        layout.addWidget(sleep_lbl)

        self._sleep_chips = []
        sleep_row = QHBoxLayout()
        sleep_row.setSpacing(8)
        self._sleep_group = QButtonGroup(self)
        self._sleep_group.setExclusive(True)
        for label in ["< 4 hours", "4–6 hours", "6–8 hours", "8+ hours"]:
            c = _Chip(label)
            self._sleep_group.addButton(c)
            self._sleep_chips.append(c)
            sleep_row.addWidget(c)
        sleep_row.addStretch()
        layout.addLayout(sleep_row)

        layout.addSpacing(6)

        # ── Stress ───────────────────────────────────────────────────────
        stress_lbl = QLabel("😰  Stress or anxiety level today?")
        stress_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        layout.addWidget(stress_lbl)

        self._stress_chips = []
        stress_row = QHBoxLayout()
        stress_row.setSpacing(8)
        self._stress_group = QButtonGroup(self)
        self._stress_group.setExclusive(True)
        for label in ["Calm", "Mildly stressed", "Very stressed"]:
            c = _Chip(label)
            self._stress_group.addButton(c)
            self._stress_chips.append(c)
            stress_row.addWidget(c)
        stress_row.addStretch()
        layout.addLayout(stress_row)

        layout.addSpacing(6)

        # ── Medication ───────────────────────────────────────────────────
        med_lbl = QLabel("💊  Medication status today?")
        med_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        layout.addWidget(med_lbl)

        self._med_chips = []
        med_row = QHBoxLayout()
        med_row.setSpacing(8)
        self._med_group = QButtonGroup(self)
        self._med_group.setExclusive(True)
        for label in ["Taken on time", "Taken late", "Missed dose", "No medication"]:
            c = _Chip(label)
            self._med_group.addButton(c)
            self._med_chips.append(c)
            med_row.addWidget(c)
        med_row.addStretch()
        layout.addLayout(med_row)

        layout.addSpacing(6)

        # ── Screen exposure ──────────────────────────────────────────────
        screen_lbl = QLabel("📱  Screen exposure in the last 2 hours?")
        screen_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        layout.addWidget(screen_lbl)

        self._screen_chips = []
        screen_row = QHBoxLayout()
        screen_row.setSpacing(8)
        self._screen_group = QButtonGroup(self)
        self._screen_group.setExclusive(True)
        for label in ["None", "Some", "A lot"]:
            c = _Chip(label)
            self._screen_group.addButton(c)
            self._screen_chips.append(c)
            screen_row.addWidget(c)
        screen_row.addStretch()
        layout.addLayout(screen_row)

        layout.addSpacing(6)

        # ── Free text ────────────────────────────────────────────────────
        other_lbl = QLabel("📝  Anything else to note? (optional)")
        other_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        layout.addWidget(other_lbl)

        self.context_textbox = QTextEdit()
        self.context_textbox.setPlaceholderText(
            "e.g. Had a fever yesterday, seemed more tired than usual..."
        )
        self.context_textbox.setFixedHeight(70)
        layout.addWidget(self.context_textbox)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.context_btn = QPushButton("Continue →")
        self.context_btn.setObjectName("primary")
        self.context_btn.setMinimumHeight(44)
        self.context_btn.clicked.connect(self._go_to_screen_1)
        btn_row.addWidget(self.context_btn)

        skip_btn = QPushButton("Skip")
        skip_btn.setObjectName("secondary")
        skip_btn.setMinimumHeight(44)
        skip_btn.clicked.connect(self._show_screen_1)
        btn_row.addWidget(skip_btn)

        layout.addLayout(btn_row)

    def _go_to_screen_1(self):
        # Build plain-text summary of selected context
        parts = []

        checked_sleep = self._sleep_group.checkedButton()
        if checked_sleep:
            parts.append(f"Sleep last night: {checked_sleep.text()}")

        checked_stress = self._stress_group.checkedButton()
        if checked_stress:
            parts.append(f"Stress level: {checked_stress.text()}")

        checked_med = self._med_group.checkedButton()
        if checked_med:
            parts.append(f"Medication: {checked_med.text()}")

        checked_screen = self._screen_group.checkedButton()
        if checked_screen:
            parts.append(f"Screen exposure: {checked_screen.text()}")

        extra = self.context_textbox.toPlainText().strip()
        if extra:
            parts.append(f"Additional notes: {extra}")

        if not parts:
            # nothing selected — skip context AI call
            self._show_screen_1()
            return

        self._context_text = '\n'.join(parts)
        self.context_btn.setText("Analysing context...")
        self.context_btn.setEnabled(False)

        if self.client is not None:
            self._ctx_worker = AIWorker(
                lambda: self.client.assess_context(self._context_text)
            )
            self._ctx_worker.finished.connect(self._on_context_response)
            self._ctx_worker.start()
        else:
            self._show_screen_1()

    def _on_context_response(self, response):
        if response:
            try:
                cleaned = re.sub(r"```json|```", "", response).strip()
                data = json.loads(cleaned)
                self.context_summary = data.pop('summary', '')
                self.context_multipliers = {
                    k: max(0.5, min(2.0, float(v)))
                    for k, v in data.items()
                    if isinstance(v, (int, float))
                }
                print(f"📋 Context multipliers: {self.context_multipliers}")
                if self.context_summary:
                    print(f"📋 Context summary: {self.context_summary}")
            except Exception as e:
                print(f"Error parsing context response: {e}")
        self._show_screen_1()

    # ── Screen 1: symptom input ──────────────────────────────────────────
    def _show_screen_1(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(0)

        layout.addWidget(self._step_indicator(1))
        layout.addSpacing(20)

        # show context summary if we got one
        if self.context_summary:
            banner = QFrame()
            banner.setStyleSheet(
                "background-color: #1e3a5f; border-radius: 8px; border-left: 3px solid #89b4fa;"
            )
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(14, 10, 14, 10)
            icon = QLabel("📋")
            icon.setFont(QFont("SF Pro Text", 16))
            banner_layout.addWidget(icon)
            msg = QLabel(self.context_summary)
            msg.setWordWrap(True)
            msg.setStyleSheet("color: #89b4fa; font-size: 12px; background: transparent;")
            banner_layout.addWidget(msg, stretch=1)
            layout.addWidget(banner)
            layout.addSpacing(16)

        title = QLabel("Patient Symptoms")
        title.setFont(QFont("SF Pro Display", 28, QFont.Bold))
        title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(title)

        sub = QLabel("Describe the typical seizure symptoms to calibrate detection.")
        sub.setFont(QFont("SF Pro Text", 13))
        sub.setStyleSheet("color: #6c7086; margin-bottom: 20px;")
        layout.addWidget(sub)

        layout.addSpacing(16)

        self.textbox = QTextEdit()
        self.textbox.setPlaceholderText(
            "e.g. She stares blankly for a few seconds, sometimes her right hand twitches..."
        )
        self.textbox.setMinimumHeight(160)
        layout.addWidget(self.textbox)

        layout.addSpacing(24)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.continue_btn = QPushButton("Continue →")
        self.continue_btn.setObjectName("primary")
        self.continue_btn.setMinimumHeight(44)
        self.continue_btn.clicked.connect(self._go_to_screen_2)
        btn_row.addWidget(self.continue_btn)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.setMinimumHeight(44)
        back_btn.clicked.connect(self._show_screen_0)
        btn_row.addWidget(back_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

    # ── Screen 2: threshold sliders ──────────────────────────────────────
    def _show_screen_2(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(0)

        layout.addWidget(self._step_indicator(2))
        layout.addSpacing(16)

        title = QLabel("Detection Thresholds")
        title.setFont(QFont("SF Pro Display", 28, QFont.Bold))
        title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(title)

        hint_text = "Adjusted by symptom profile"
        if self.context_multipliers:
            hint_text += " and today's context"
        hint = QLabel(hint_text)
        hint.setFont(QFont("SF Pro Text", 12))
        hint.setStyleSheet("color: #6c7086; margin-bottom: 16px;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)

        params = [
            ("Blink Detection",  "blink_detection",  "🫦", "blink"),
            ("Eye Tracking",     "eye_tracking",     "👁",  "eye"),
            ("Face Freeze",      "face_freeze",      "🧊",  "freeze"),
            ("Face Asymmetry",   "face_asymmetry",   "↔️",  "asym"),
            ("Seizure / Twitch", "seizure_twitch",   "⚡",  "twitch"),
            ("Heart Rate (BPM)", "bpm",              "❤️",  "bpm"),
            ("Face Color",       "face_color",       "🎨",  "color"),
        ]

        self.sliders = {}
        for label, key, icon, ctx_key in params:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 12, 20, 12)
            card_layout.setSpacing(4)

            top_row = QHBoxLayout()
            lbl = QLabel(f"{icon}  {label}")
            lbl.setFont(QFont("SF Pro Text", 13))
            top_row.addWidget(lbl)

            # show context badge if this signal was boosted
            mult = self.context_multipliers.get(ctx_key, 1.0)
            if mult > 1.05:
                badge = QLabel(f"  ⚠ +{int((mult-1)*100)}% sensitivity")
                badge.setStyleSheet("color: #f9e2af; font-size: 11px;")
                top_row.addWidget(badge)
            elif mult < 0.95:
                badge = QLabel(f"  ✓ -{int((1-mult)*100)}% sensitivity")
                badge.setStyleSheet("color: #a6e3a1; font-size: 11px;")
                top_row.addWidget(badge)

            top_row.addStretch()

            val_label = QLabel(str(self.defaults.get(key, 50)))
            val_label.setFont(QFont("SF Pro Text", 13, QFont.Bold))
            val_label.setStyleSheet("color: #89b4fa; min-width: 32px;")
            val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            top_row.addWidget(val_label)
            card_layout.addLayout(top_row)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(self.defaults.get(key, 50))
            slider.valueChanged.connect(lambda v, l=val_label: l.setText(str(v)))
            card_layout.addWidget(slider)

            self.sliders[key] = slider
            scroll_layout.addWidget(card)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        layout.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        start_btn = QPushButton("▶  Start Detection")
        start_btn.setObjectName("primary")
        start_btn.setMinimumHeight(44)
        start_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(start_btn)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.setMinimumHeight(44)
        back_btn.clicked.connect(self._show_screen_1)
        btn_row.addWidget(back_btn)

        layout.addLayout(btn_row)

    def _go_to_screen_2(self):
        self.user_text = self.textbox.toPlainText().strip()
        if not self.user_text:
            self.textbox.setStyleSheet(
                self.textbox.styleSheet() + "border: 1px solid #f38ba8;"
            )
            return

        self.continue_btn.setText("Asking AI...")
        self.continue_btn.setEnabled(False)

        if self.client is not None:
            self._ai_worker = AIWorker(
                lambda: self.client.get_response(self.user_text)
            )
            self._ai_worker.finished.connect(self._on_ai_response)
            self._ai_worker.start()
        else:
            self._show_screen_2()

    def _on_ai_response(self, response):
        if response:
            try:
                cleaned = re.sub(r"```json|```", "", response).strip()
                data = json.loads(cleaned)
                for key in self.defaults:
                    if key in data:
                        base = int(float(data[key]) * 100)
                        # apply context multiplier to the slider default
                        ctx_map = {
                            'blink_detection': 'blink', 'eye_tracking': 'eye',
                            'face_freeze': 'freeze', 'face_asymmetry': 'asym',
                            'seizure_twitch': 'twitch', 'bpm': 'bpm', 'face_color': 'color'
                        }
                        mult = self.context_multipliers.get(ctx_map.get(key, ''), 1.0)
                        self.defaults[key] = min(100, int(base * mult))
            except Exception as e:
                print(f"Error parsing AI response: {e}")
        else:
            # no AI — still apply context multipliers to default 50
            ctx_map = {
                'blink_detection': 'blink', 'eye_tracking': 'eye',
                'face_freeze': 'freeze', 'face_asymmetry': 'asym',
                'seizure_twitch': 'twitch', 'bpm': 'bpm', 'face_color': 'color'
            }
            for key in self.defaults:
                mult = self.context_multipliers.get(ctx_map.get(key, ''), 1.0)
                self.defaults[key] = min(100, int(50 * mult))
        self._show_screen_2()

    def _on_submit(self):
        self.result = {
            'text': getattr(self, 'user_text', ''),
            'context_multipliers': self.context_multipliers,
            'context_summary': self.context_summary,
            **{key: slider.value() for key, slider in self.sliders.items()}
        }
        self.close()


def show_menu_modern(client=None):
    app = QApplication.instance() or QApplication(sys.argv)
    window = EpiGuardMenu(client=client)
    window.show()
    app.exec()
    return window.result


if __name__ == "__main__":
    print(show_menu_modern())
