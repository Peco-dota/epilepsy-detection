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

from ui.theme import BG, CARD, TEXT, MUTED, ACCENT, ACCENT2, BORDER, INPUT_BG

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'SF Pro Text', 'Segoe UI', sans-serif;
}}
QLabel {{ color: {TEXT}; }}
QTextEdit {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
}}
QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QPushButton {{
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
    border: none;
}}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});
    color: #ffffff;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444);
}}
QPushButton#primary:disabled {{ background-color: rgba(177,173,161,0.35); color: #b1ada1; }}
QPushButton#secondary {{
    background-color: rgba(177,173,161,0.2);
    color: {TEXT};
    border: 1px solid rgba(177,173,161,0.5);
}}
QPushButton#secondary:hover {{ background-color: rgba(177,173,161,0.35); }}
QScrollArea {{ border: none; background-color: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 4px; border-radius: 2px;
}}
QScrollBar::handle:vertical {{ background: rgba(177,173,161,0.5); border-radius: 2px; }}
QSlider::groove:horizontal {{
    height: 4px; background: rgba(177,173,161,0.4); border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QFrame#card {{ background-color: {CARD}; border-radius: 12px; border: 1px solid {BORDER}; }}
QPushButton#chip {{
    background-color: {CARD};
    color: {MUTED};
    border: 1.5px solid rgba(177,173,161,0.6);
    border-radius: 8px;
    padding: 0px;
    font-size: 13px;
    font-weight: normal;
}}
QPushButton#chip:checked {{
    background-color: {ACCENT};
    color: #ffffff;
    border: 1.5px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#chip:hover:!checked {{
    border-color: {ACCENT};
    background-color: rgba(193,95,60,0.04);
    color: {TEXT};
}}
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
    # Emits the result dict when check-in completes, or None if the window is closed
    done = Signal(object)

    def __init__(self, client=None, mode='full', patient_name=''):
        """
        mode='full'    → 3 screens: context → symptoms → thresholds
        mode='checkin' → context screen only, "Start Monitoring" goes direct to submit
        """
        super().__init__()
        self.client = client
        self.mode = mode
        self.patient_name = patient_name or 'your child'
        self.result = None
        self.context_multipliers = {}
        self.context_summary = ""
        self.defaults = {
            'blink_detection': 50, 'eye_tracking': 50, 'face_freeze': 50,
            'face_asymmetry': 50, 'seizure_twitch': 50, 'bpm': 50, 'face_color': 50
        }
        self.sliders = {}

        self.setWindowTitle("EPIGUARD")
        self.setFixedSize(860, 760)
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
                f"color: {'#c15f3c' if i == current else '#b1ada1'}; font-size: 12px;"
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
        layout.setContentsMargins(56, 24, 56, 24)
        layout.setSpacing(0)

        if self.mode != 'checkin':
            layout.addWidget(self._step_indicator(0))
            layout.addSpacing(12)

        title = QLabel("Good to see you!")
        title.setFont(QFont("SF Pro Display", 24, QFont.Bold))
        title.setStyleSheet("color: #c15f3c;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(3)

        sub = QLabel(f"Before monitoring {self.patient_name}, tell us how they're doing today.")
        sub.setFont(QFont("SF Pro Text", 13))
        sub.setStyleSheet("color: #8a847a;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        layout.addSpacing(16)

        def _section(question, options, group_attr, chips_attr):
            lbl = QLabel(question)
            lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
            lbl.setStyleSheet("color: #1c1917;")
            layout.addWidget(lbl)
            layout.addSpacing(7)

            row = QHBoxLayout()
            row.setSpacing(8)
            grp = QButtonGroup(self)
            grp.setExclusive(True)
            chips = []
            for text in options:
                c = _Chip(text)
                c.setFixedHeight(40)
                grp.addButton(c)
                chips.append(c)
                row.addWidget(c, stretch=1)
            layout.addLayout(row)
            layout.addSpacing(16)

            setattr(self, group_attr, grp)
            setattr(self, chips_attr, chips)

        _section("How much did they sleep last night?",
                 ["< 4 hours", "4–6 hours", "6–8 hours", "8+ hours"],
                 '_sleep_group', '_sleep_chips')
        _section("Stress or anxiety level today?",
                 ["Calm", "Mildly stressed", "Very stressed"],
                 '_stress_group', '_stress_chips')
        _section("Medication status today?",
                 ["Taken on time", "Taken late", "Missed dose", "No medication"],
                 '_med_group', '_med_chips')
        _section("Screen exposure in the last 2 hours?",
                 ["None", "Some", "A lot"],
                 '_screen_group', '_screen_chips')

        other_lbl = QLabel("Anything else to note? (optional)")
        other_lbl.setFont(QFont("SF Pro Text", 13, QFont.Bold))
        other_lbl.setStyleSheet("color: #1c1917;")
        layout.addWidget(other_lbl)
        layout.addSpacing(7)
        self.context_textbox = QTextEdit()
        self.context_textbox.setPlaceholderText(
            "e.g. Had a fever yesterday, seemed more tired than usual..."
        )
        self.context_textbox.setFixedHeight(60)
        layout.addWidget(self.context_textbox)
        layout.addSpacing(16)

        # Audio monitoring toggle
        self._audio_enabled = False
        audio_row = QHBoxLayout()
        audio_row.setSpacing(12)
        self._audio_btn = QPushButton("Enable audio monitoring")
        self._audio_btn.setCheckable(True)
        self._audio_btn.setFocusPolicy(Qt.NoFocus)
        self._audio_btn.setCursor(Qt.PointingHandCursor)
        self._audio_btn.setFixedHeight(40)
        self._audio_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD}; color: {MUTED};
                border: 1.5px solid rgba(177,173,161,0.6);
                border-radius: 8px; padding: 0 16px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:checked {{
                background: {ACCENT}; color: #ffffff;
                border-color: {ACCENT};
            }}
        """)
        audio_hint = QLabel("Detects groans and unusual sounds during a seizure")
        audio_hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        audio_hint.setAlignment(Qt.AlignVCenter)

        def _toggle_audio(checked):
            self._audio_enabled = checked
        self._audio_btn.toggled.connect(_toggle_audio)

        audio_row.addWidget(self._audio_btn)
        audio_row.addWidget(audio_hint, stretch=1)
        layout.addLayout(audio_row)

        layout.addStretch()
        layout.addSpacing(14)

        if self.mode == 'checkin':
            btn_row = QHBoxLayout()
            btn_row.setSpacing(12)

            skip_btn = QPushButton("Skip check-in")
            skip_btn.setObjectName("secondary")
            skip_btn.setFixedHeight(44)
            skip_btn.clicked.connect(self._checkin_submit_empty)
            btn_row.addWidget(skip_btn, stretch=1)

            self.context_btn = QPushButton("▶  Start Monitoring")
            self.context_btn.setObjectName("primary")
            self.context_btn.setFixedHeight(44)
            self.context_btn.clicked.connect(self._go_to_screen_1)
            btn_row.addWidget(self.context_btn, stretch=2)

            layout.addLayout(btn_row)
        else:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(10)
            self.context_btn = QPushButton("Continue →")
            self.context_btn.setObjectName("primary")
            self.context_btn.setFixedHeight(44)
            self.context_btn.clicked.connect(self._go_to_screen_1)
            btn_row.addWidget(self.context_btn)
            skip_btn = QPushButton("Skip")
            skip_btn.setObjectName("secondary")
            skip_btn.setFixedHeight(44)
            skip_btn.setFixedWidth(90)
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
            if self.mode == 'checkin':
                self._checkin_submit_empty()
            else:
                self._show_screen_1()
            return

        self._context_text = '\n'.join(parts)
        self.context_btn.setText("Analysing...")
        self.context_btn.setEnabled(False)

        if self.client is not None:
            self._ctx_worker = AIWorker(
                lambda: self.client.assess_context(self._context_text)
            )
            self._ctx_worker.finished.connect(self._on_context_response)
            self._ctx_worker.start()
        else:
            if self.mode == 'checkin':
                self._checkin_submit_empty()
            else:
                self._show_screen_1()

    def _checkin_submit_empty(self):
        self.result = {
            'context_multipliers': {},
            'context_summary': '',
            'audio_enabled': getattr(self, '_audio_enabled', False),
            'screen_protection_enabled': getattr(self, '_screen_protection_enabled', True),
        }
        self.done.emit(self.result)
        self.close()

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
        if self.mode == 'checkin':
            self.result = {
                'context_multipliers': self.context_multipliers,
                'context_summary': self.context_summary,
                'audio_enabled': getattr(self, '_audio_enabled', False),
                'screen_protection_enabled': getattr(self, '_screen_protection_enabled', True),
            }
            self.done.emit(self.result)
            self.close()
        else:
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
                "background-color: rgba(193,95,60,0.07); border-radius: 8px; border-left: 3px solid #c15f3c;"
            )
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(14, 10, 14, 10)
            icon = QLabel("📋")
            icon.setFont(QFont("SF Pro Text", 16))
            banner_layout.addWidget(icon)
            msg = QLabel(self.context_summary)
            msg.setWordWrap(True)
            msg.setStyleSheet("color: #c15f3c; font-size: 12px; background: transparent;")
            banner_layout.addWidget(msg, stretch=1)
            layout.addWidget(banner)
            layout.addSpacing(16)

        title = QLabel("Patient Symptoms")
        title.setFont(QFont("SF Pro Display", 28, QFont.Bold))
        title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(title)

        sub = QLabel("Describe the typical seizure symptoms to calibrate detection.")
        sub.setFont(QFont("SF Pro Text", 13))
        sub.setStyleSheet("color: #8a847a; margin-bottom: 20px;")
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
        hint.setStyleSheet("color: #8a847a; margin-bottom: 16px;")
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
                badge.setStyleSheet("color: #b45309; font-size: 11px;")
                top_row.addWidget(badge)
            elif mult < 0.95:
                badge = QLabel(f"  ✓ -{int((1-mult)*100)}% sensitivity")
                badge.setStyleSheet("color: #2e7d32; font-size: 11px;")
                top_row.addWidget(badge)

            top_row.addStretch()

            val_label = QLabel(str(self.defaults.get(key, 50)))
            val_label.setFont(QFont("SF Pro Text", 13, QFont.Bold))
            val_label.setStyleSheet("color: #c15f3c; min-width: 32px;")
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

    def closeEvent(self, event):
        # If window is closed (X button) before a result was emitted, signal cancellation
        if self.result is None and self.mode == 'checkin':
            self.done.emit(None)
        event.accept()


def show_menu_modern(client=None):
    app = QApplication.instance() or QApplication(sys.argv)
    window = EpiGuardMenu(client=client, mode='full')
    window.show()
    app.exec()
    return window.result


def show_checkin(client=None, patient_name=''):
    """Daily quick check-in — context screen only, then starts monitoring."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = EpiGuardMenu(client=client, mode='checkin', patient_name=patient_name)
    window.show()
    app.exec()
    return window.result


if __name__ == "__main__":
    print(show_menu_modern())
