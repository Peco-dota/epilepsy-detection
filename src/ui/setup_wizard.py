"""
First-time setup wizard for EpiGuard.
Screens: Welcome → Symptom Survey → Emergency Contact → All Set
Design: minimal dark, inspired by Linear / Arc / Vercel
"""

import sys
import json
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame,
    QSizePolicy, QButtonGroup, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont

from core.profile import save_profile, load_profile
from detectors.face_detection import DEFAULT_WEIGHTS, save_weights

from ui.theme import BG, SURFACE, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, SUCCESS, DANGER

STYLE = f"""
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
QScrollBar::handle:vertical:hover {{ background: rgba(177,173,161,0.7); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

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
    padding: 0px;
    font-size: 15px;
    font-weight: bold;
    border: none;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ad5434,stop:1 #c46444);
}}
QPushButton#primary:disabled {{
    background: rgba(177,173,161,0.3);
    color: {MUTED};
}}
QPushButton#ghost {{
    background: transparent;
    color: {MUTED};
    border: none;
    border-radius: 10px;
    padding: 0px;
    font-size: 14px;
}}
QPushButton#ghost:hover {{
    background: rgba(193,95,60,0.06);
    color: {TEXT};
}}
QPushButton#start {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {SUCCESS},stop:1 #1b5e20);
    color: #ffffff;
    border-radius: 14px;
    font-size: 16px;
    font-weight: bold;
    border: none;
}}
QPushButton#start:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #388e3c,stop:1 {SUCCESS});
}}
QFrame#card {{
    background-color: {CARD};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}
QFrame#card:hover {{
    border-color: rgba(193,95,60,0.3);
}}
QPushButton#answer {{
    background-color: rgba(177,173,161,0.12);
    color: {MUTED};
    border-radius: 10px;
    border: 1px solid rgba(177,173,161,0.35);
    font-size: 13px;
    padding: 0px;
}}
QPushButton#answer:checked {{
    background-color: rgba(193,95,60,0.12);
    border-color: {ACCENT};
    color: {ACCENT};
    font-weight: bold;
}}
QPushButton#answer:hover {{
    border-color: rgba(193,95,60,0.4);
    color: {TEXT};
}}
QPushButton#sms_test {{
    background: transparent;
    color: {ACCENT};
    border: 1px solid rgba(193,95,60,0.35);
    border-radius: 8px;
    padding: 0px;
    font-size: 13px;
}}
QPushButton#sms_test:hover {{
    background: rgba(193,95,60,0.06);
    border-color: {ACCENT};
}}
"""

SURVEY_QUESTIONS = [
    # ── Awareness & Recovery ──────────────────────────────────────────────────
    ("🧠", "unresponsive",
     "During episodes, does {name} seem unaware or unable to respond to you?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("🌫️", "postictal",
     "After an episode, is {name} confused, very tired, or hard to wake for several minutes?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("⚠️", "aura",
     "Does {name} report any warning before an episode — an unusual feeling, smell, or visual change?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Stillness / Absence ───────────────────────────────────────────────────
    ("🧊", "staring",
     "Do episodes involve blank staring or a sudden halt in all activity?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Motor — generalized ───────────────────────────────────────────────────
    ("🪨", "stiffening",
     "Does the body or limbs go suddenly stiff or rigid during episodes?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("⚡", "clonic",
     "Is there rhythmic muscle twitching or repetitive limb shaking during episodes?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("🤸", "myoclonic",
     "Are there sudden, very brief full-body or limb jolts — like a strong startle?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("🪂", "atonic",
     "Does {name} suddenly go completely limp, drop objects, or fall without warning?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Focal features ────────────────────────────────────────────────────────
    ("🔁", "automatisms",
     "During episodes, does {name} make repeated automatic movements — lip smacking, chewing, or hand rubbing?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("↔️", "onesided",
     "Are movements or symptoms clearly stronger or starting on one side of the body or face?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Eye features ──────────────────────────────────────────────────────────
    ("👁", "eyes",
     "Do the eyes roll back, drift sideways, or flutter during episodes?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Autonomic ─────────────────────────────────────────────────────────────
    ("🎨", "color",
     "Does skin color change during episodes — going pale, flushed, or bluish around the lips?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    ("❤️", "heartrate",
     "Is heart rate noticeably fast or irregular before or during episodes?",
     ["Never", "Rarely", "Sometimes", "Often", "Always"]),

    # ── Episode characteristics ───────────────────────────────────────────────
    ("⏱", "duration",
     "How long do episodes typically last?",
     ["< 5 sec", "5–30 sec", "30s–2 min", "2–5 min", "> 5 min"]),

    ("📅", "frequency",
     "How often do episodes occur?",
     ["< Once/month", "Monthly", "Weekly", "Daily", "Multiple/day"]),
]

WEIGHT_PLAIN = {
    'w_shake':    ('Head shaking',       '🤚'),
    'w_twitch':   ('Facial twitching',   '⚡'),
    'w_blink':    ('Blinking patterns',  '👀'),
    'w_freeze':   ('Staring episodes',   '🧊'),
    'w_asym':     ('Face asymmetry',     '↔️'),
    'w_bpm':      ('Heart rate',         '❤️'),
    'w_color':    ('Skin color',         '🎨'),
    'w_blink_nc': ('Absence blinking',   '👁'),
    'w_bpm_nc':   ('Absence heart rate', '💓'),
}


class _AIWorker(QThread):
    finished = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn() or '')
        except Exception:
            self.finished.emit('')


class _StepBar(QWidget):
    STEPS = ['Welcome', 'Symptoms', 'Contact', 'All Set']

    def __init__(self, current: int, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: transparent;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addStretch()

        for i, step in enumerate(self.STEPS):
            done = i < current
            active = i == current

            if done:
                indicator = QLabel('✓')
                indicator.setStyleSheet(
                    f'color: {SUCCESS}; font-size: 10px; font-weight: bold;'
                    f'background: rgba(34,197,94,0.12); border-radius: 8px;'
                    f'padding: 1px 5px;'
                )
            elif active:
                indicator = QLabel('●')
                indicator.setStyleSheet(f'color: {ACCENT}; font-size: 9px;')
            else:
                indicator = QLabel('○')
                indicator.setStyleSheet('color: rgba(177,173,161,0.5); font-size: 9px;')

            indicator.setFixedWidth(22)
            indicator.setAlignment(Qt.AlignCenter)
            layout.addWidget(indicator)

            lbl = QLabel(step)
            lbl.setFont(QFont('', 11, QFont.DemiBold if active else QFont.Normal))
            lbl.setStyleSheet(
                f'background: transparent; color: {TEXT};' if active else
                f'background: transparent; color: {SUCCESS};' if done else
                'background: transparent; color: rgba(177,173,161,0.5);'
            )
            layout.addWidget(lbl)

            if i < len(self.STEPS) - 1:
                sep = QLabel('·')
                sep.setStyleSheet(f'background: transparent; color: {"rgba(177,173,161,0.4)" if not done else "rgba(46,125,50,0.4)"}; font-size: 14px;')
                sep.setFixedWidth(16)
                sep.setAlignment(Qt.AlignCenter)
                layout.addWidget(sep)

        layout.addStretch()
        self.setFixedHeight(28)


class _AnswerButton(QPushButton):
    def __init__(self, label: str, value: int):
        super().__init__(label)
        self.value = value
        self.setObjectName('answer')
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)


class _SurveyQuestion(QWidget):
    def __init__(self, icon: str, key: str, question: str, name: str,
                 answer_labels: list, parent=None):
        super().__init__(parent)
        self.key = key
        self._selected = 0
        self.setStyleSheet('background: transparent;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        q_row = QHBoxLayout()
        q_row.setSpacing(10)
        text = QLabel(question.replace('{name}', name or 'the patient'))
        text.setFont(QFont('', 14))
        text.setStyleSheet(f'color: {TEXT};')
        text.setWordWrap(True)
        q_row.addWidget(text, stretch=1)
        layout.addLayout(q_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for i, label in enumerate(answer_labels):
            btn = _AnswerButton(label, i + 1)
            self._group.addButton(btn)
            btn.toggled.connect(lambda checked, v=i + 1: self._on_toggle(checked, v))
            btn_row.addWidget(btn, stretch=1)

        layout.addLayout(btn_row)

    def _on_toggle(self, checked: bool, value: int):
        if checked:
            self._selected = value

    @property
    def answered(self) -> bool:
        return self._selected > 0

    @property
    def value(self) -> int:
        return self._selected


class SetupWizard(QMainWindow):

    def __init__(self, client=None, twilio_client=None, patient=None):
        super().__init__()
        self.client = client
        self.twilio_client = twilio_client
        self._patient = patient  # None = legacy single-profile mode
        self.profile = load_profile()
        self.profile['setup_complete'] = False
        if patient:
            self.profile['patient_name'] = patient.get('name', '')
            self.profile['patient_age'] = patient.get('age', '')
            self.profile['emergency_contact'] = patient.get('emergency_contact', '')
        self._weights = DEFAULT_WEIGHTS.copy()
        self._questions: list[_SurveyQuestion] = []
        self._dot_state = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._animate_loading)

        self.setWindowTitle('EpiGuard — Setup')
        self.setFixedSize(880, 740)
        self.setStyleSheet(STYLE)
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 880) // 2, (screen.height() - 740) // 2)
        if patient:
            self._show_survey()
        else:
            self._show_welcome()

    # ── Shared ────────────────────────────────────────────────────────────────

    def _clear(self):
        if self.centralWidget():
            self.centralWidget().deleteLater()

    def _name(self) -> str:
        return self.profile.get('patient_name', '') or 'the patient'

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont('', 12))
        lbl.setStyleSheet(f'color: {MUTED}; letter-spacing: 0.5px;')
        return lbl

    def _centered_btn(self, btn: QPushButton, width: int = 260, height: int = 52) -> QHBoxLayout:
        btn.setFixedSize(width, height)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        return row

    def _fade_in(self, widget):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b'opacity', widget)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuart)
        anim.start()

    # ── Screen 0: Welcome ─────────────────────────────────────────────────────

    def _show_welcome(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(72, 36, 72, 44)
        layout.setSpacing(0)

        layout.addWidget(_StepBar(0))
        layout.addStretch(1)

        # Icon — placed directly without a frame to avoid Qt border-radius clipping artifact
        icon_lbl = QLabel('🛡️')
        icon_lbl.setFont(QFont('', 64))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet('background: transparent;')
        icon_lbl.setFixedHeight(80)
        layout.addWidget(icon_lbl)
        layout.addSpacing(16)

        title = QLabel('Welcome to EpiGuard')
        title.setFont(QFont('', 34, QFont.Bold))
        title.setStyleSheet(f'background: transparent; color: {TEXT};')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(8)

        sub = QLabel("Real-time seizure monitoring, personalised to each patient")
        sub.setFont(QFont('', 14))
        sub.setStyleSheet(f'background: transparent; color: {MUTED};')
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        layout.addStretch(2)

        # Form
        name_lbl = self._section_label("PATIENT NAME")
        layout.addWidget(name_lbl)
        layout.addSpacing(8)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText('e.g. Emma')
        self._name_input.setFixedHeight(54)
        if self.profile.get('patient_name'):
            self._name_input.setText(self.profile['patient_name'])
        layout.addWidget(self._name_input)
        layout.addSpacing(20)

        age_lbl = self._section_label('AGE  (optional)')
        layout.addWidget(age_lbl)
        layout.addSpacing(8)

        self._age_input = QLineEdit()
        self._age_input.setPlaceholderText('e.g. 8')
        self._age_input.setFixedHeight(54)
        self._age_input.setFixedWidth(140)
        if self.profile.get('patient_age'):
            self._age_input.setText(self.profile['patient_age'])
        layout.addWidget(self._age_input)
        layout.addStretch(2)

        next_btn = QPushButton("Let's get started  →")
        next_btn.setObjectName('primary')
        next_btn.clicked.connect(self._welcome_next)
        layout.addLayout(self._centered_btn(next_btn, width=280))

        self._fade_in(root)

    def _welcome_next(self):
        name = self._name_input.text().strip()
        if not name:
            self._name_input.setStyleSheet(
                self._name_input.styleSheet() +
                f'border-color: {DANGER}; background: rgba(239,68,68,0.06);'
            )
            return
        self.profile['patient_name'] = name
        self.profile['patient_age'] = self._age_input.text().strip()
        self._show_survey()

    # ── Screen 1: Symptom Survey ──────────────────────────────────────────────

    def _show_survey(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(72, 36, 72, 40)
        layout.setSpacing(0)

        layout.addWidget(_StepBar(1))
        layout.addSpacing(18)

        # Title row + mode toggle
        title_row = QHBoxLayout()
        title = QLabel("Tell us about the episodes")
        title.setFont(QFont('', 24, QFont.Bold))
        title.setStyleSheet(f'background: transparent; color: {TEXT};')
        title_row.addWidget(title)
        title_row.addStretch()

        if self.client is not None:
            self._mode_btn = QPushButton('✍  Just describe it instead')
            self._mode_btn.setObjectName('ghost')
            self._mode_btn.setFixedHeight(34)
            self._mode_btn.setStyleSheet(
                f'background: rgba(193,95,60,0.08); color: {ACCENT};'
                f'border: 1px solid rgba(193,95,60,0.3); border-radius: 8px;'
                f'font-size: 12px; padding: 0 14px;'
            )
            self._mode_btn.clicked.connect(self._toggle_survey_mode)
            title_row.addWidget(self._mode_btn)

        layout.addLayout(title_row)
        layout.addSpacing(4)

        if self.client is not None:
            sub = QLabel("Answer the questions below — or switch to AI mode and describe episodes in your own words.")
        else:
            sub = QLabel("Answer as many questions as you can. Skip any that don't apply.")
        sub.setFont(QFont('', 13))
        sub.setStyleSheet(f'background: transparent; color: {MUTED};')
        layout.addWidget(sub)
        layout.addSpacing(14)

        # ── Mode A: Survey questions ──────────────────────────────────────
        from PySide6.QtWidgets import QTextEdit as _QTE
        self._survey_panel = QWidget()
        self._survey_panel.setStyleSheet('background: transparent;')
        sp_layout = QVBoxLayout(self._survey_panel)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet('background: transparent;')
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(8)
        inner_layout.setContentsMargins(0, 0, 10, 4)

        self._questions = []
        for icon, key, question, answer_labels in SURVEY_QUESTIONS:
            card = QFrame()
            card.setObjectName('card')
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 14, 18, 14)
            q = _SurveyQuestion(icon, key, question, self._name(), answer_labels, card)
            self._questions.append(q)
            cl.addWidget(q)
            inner_layout.addWidget(card)

        scroll.setWidget(inner)
        sp_layout.addWidget(scroll)
        layout.addWidget(self._survey_panel, stretch=1)

        # ── Mode B: Free-text description ─────────────────────────────────
        self._describe_panel = QWidget()
        self._describe_panel.setStyleSheet('background: transparent;')
        self._describe_panel.setVisible(False)
        dp_layout = QVBoxLayout(self._describe_panel)
        dp_layout.setContentsMargins(0, 0, 0, 0)
        dp_layout.setSpacing(12)

        desc_hint = QLabel(
            "Describe the episodes in your own words — what happens, how long they last, how often they occur.\n"
            "AI will interpret your description and automatically set all detection weights."
        )
        desc_hint.setFont(QFont('', 13))
        desc_hint.setStyleSheet(f'background: transparent; color: {MUTED};')
        desc_hint.setWordWrap(True)
        dp_layout.addWidget(desc_hint)

        self._describe_input = _QTE()
        self._describe_input.setPlaceholderText(
            "e.g. She suddenly stops what she's doing and stares blankly for about 10 seconds. "
            "Her eyes sometimes flutter. Afterwards she seems confused for a minute. "
            "Happens 2-3 times a week, usually in the morning..."
        )
        self._describe_input.setStyleSheet(
            f'background: #ffffff; color: {TEXT};'
            f'border: 1px solid rgba(177,173,161,0.45); border-radius: 12px;'
            f'padding: 14px; font-size: 14px;'
        )
        dp_layout.addWidget(self._describe_input, stretch=1)
        layout.addWidget(self._describe_panel, stretch=1)

        # ── Loading + buttons ─────────────────────────────────────────────
        layout.addSpacing(10)

        self._survey_loading = QLabel('')
        self._survey_loading.setFont(QFont('', 12))
        self._survey_loading.setStyleSheet(f'background: transparent; color: {ACCENT};')
        self._survey_loading.setAlignment(Qt.AlignCenter)
        self._survey_loading.setVisible(False)
        layout.addWidget(self._survey_loading)
        layout.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        back_btn = QPushButton('← Back')
        back_btn.setObjectName('ghost')
        back_btn.setFixedHeight(46)
        back_btn.setFixedWidth(100)
        # In patient mode there is no welcome screen to go back to
        back_btn.clicked.connect(self.close if self._patient else self._show_welcome)
        btn_row.addWidget(back_btn)

        self._survey_next_btn = QPushButton('Continue  →')
        self._survey_next_btn.setObjectName('primary')
        self._survey_next_btn.setFixedHeight(46)
        self._survey_next_btn.setFixedWidth(180)
        self._survey_next_btn.clicked.connect(self._survey_next)
        btn_row.addWidget(self._survey_next_btn)

        layout.addLayout(btn_row)
        self._survey_mode = 'questions'
        self._fade_in(root)

    def _toggle_survey_mode(self):
        if self._survey_mode == 'questions':
            self._survey_mode = 'describe'
            self._survey_panel.setVisible(False)
            self._describe_panel.setVisible(True)
            self._mode_btn.setText('📋  Answer questions instead')
            self._survey_next_btn.setText('Analyse with AI  →')
        else:
            self._survey_mode = 'questions'
            self._survey_panel.setVisible(True)
            self._describe_panel.setVisible(False)
            self._mode_btn.setText('✍  Just describe it instead')
            self._survey_next_btn.setText('Continue  →')

    def _survey_next(self):
        self._survey_next_btn.setEnabled(False)
        self._survey_loading.setStyleSheet(f'background: transparent; color: {ACCENT}; font-size: 12px;')
        self._survey_loading.setVisible(True)
        self._dot_state = 0
        self._dot_timer.start(400)

        if self._survey_mode == 'describe':
            # Free-text mode: send description to symptom AI prompt
            text = self._describe_input.toPlainText().strip()
            if not text:
                self._survey_loading.setText('Please describe the episodes first')
                self._survey_loading.setStyleSheet(f'background: transparent; color: {DANGER}; font-size: 12px;')
                self._dot_timer.stop()
                self._survey_next_btn.setEnabled(True)
                return
            if self.client is not None:
                self._ai_worker = _AIWorker(lambda: self.client.get_response(text))
                self._ai_worker.finished.connect(self._on_describe_ai)
                self._ai_worker.start()
            else:
                self._dot_timer.stop()
                self._show_contact()
            return

        # Survey mode
        answers = {q.key: q.value for q in self._questions}
        unanswered = sum(1 for v in answers.values() if v == 0)

        if unanswered > 5:
            self._dot_timer.stop()
            self._survey_loading.setText(
                f'Please answer at least {len(SURVEY_QUESTIONS) - 5} questions'
            )
            self._survey_loading.setStyleSheet(f'background: transparent; color: {DANGER}; font-size: 12px;')
            self._survey_next_btn.setEnabled(True)
            return

        for key in answers:
            if answers[key] == 0:
                answers[key] = 3

        if self.client is not None:
            self._ai_worker = _AIWorker(lambda: self.client.process_survey(answers))
            self._ai_worker.finished.connect(lambda r: self._on_survey_ai(r, answers))
            self._ai_worker.start()
        else:
            self._dot_timer.stop()
            self._apply_survey_fallback(answers)
            self._show_contact()

    def _on_describe_ai(self, response: str):
        self._dot_timer.stop()
        if response:
            try:
                import re as _re
                cleaned = _re.sub(r'```json|```', '', response).strip()
                data = json.loads(cleaned)
                for k in DEFAULT_WEIGHTS:
                    if k in data:
                        self._weights[k] = round(max(0.05, min(0.80, float(data[k]))), 3)
                print(f'📊 Weights from description: {self._weights}')
            except Exception:
                pass  # use defaults if parse fails
        self._show_contact()

    def _animate_loading(self):
        dots = [
            '🤖  Personalising monitoring',
            '🤖  Personalising monitoring.',
            '🤖  Personalising monitoring..',
            '🤖  Personalising monitoring...',
        ]
        self._dot_state = (self._dot_state + 1) % 4
        if hasattr(self, '_survey_loading'):
            self._survey_loading.setText(dots[self._dot_state])

    def _on_survey_ai(self, response: str, answers: dict):
        self._dot_timer.stop()
        if response:
            try:
                cleaned = re.sub(r'```json|```', '', response).strip()
                data = json.loads(cleaned)
                for k in DEFAULT_WEIGHTS:
                    if k in data:
                        self._weights[k] = round(max(0.05, min(0.80, float(data[k]))), 3)
            except Exception as e:
                print(f'Survey parse error: {e}')
                self._apply_survey_fallback(answers)
        else:
            self._apply_survey_fallback(answers)
        self._show_contact()

    def _apply_survey_fallback(self, answers: dict):
        mapping = {
            'unresponsive': [('w_freeze', 0.10), ('w_blink_nc', 0.06)],
            'staring':      [('w_freeze', 0.14), ('w_blink_nc', 0.08)],
            'postictal':    [('w_freeze', 0.06), ('w_bpm_nc',   0.05)],
            'aura':         [('w_bpm',    0.06), ('w_color',    0.05)],
            'stiffening':   [('w_shake',  0.08), ('w_twitch',   0.06)],
            'clonic':       [('w_shake',  0.12), ('w_twitch',   0.10)],
            'myoclonic':    [('w_twitch', 0.14), ('w_shake',    0.08)],
            'atonic':       [('w_shake',  0.06), ('w_twitch',   0.06)],
            'automatisms':  [('w_freeze', 0.08), ('w_blink_nc', 0.06)],
            'onesided':     [('w_asym',   0.14)],
            'eyes':         [('w_blink',  0.10), ('w_blink_nc', 0.07)],
            'color':        [('w_color',  0.12), ('w_bpm',      0.07), ('w_bpm_nc', 0.05)],
            'heartrate':    [('w_bpm',    0.12), ('w_bpm_nc',   0.08)],
        }
        w = DEFAULT_WEIGHTS.copy()
        for q_key, pairs in mapping.items():
            score = answers.get(q_key, 3)
            for wk, factor in pairs:
                w[wk] = round(min(0.80, w[wk] + (score - 1) * factor), 3)
        self._weights = w

    # ── Screen 2: Emergency Contact ───────────────────────────────────────────

    def _show_contact(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(72, 36, 72, 44)
        layout.setSpacing(0)

        layout.addWidget(_StepBar(2))
        layout.addStretch(1)

        # Icon — plain label
        bell_lbl = QLabel('📲')
        bell_lbl.setFont(QFont('', 56))
        bell_lbl.setAlignment(Qt.AlignCenter)
        bell_lbl.setStyleSheet('background: transparent;')
        bell_lbl.setFixedHeight(72)
        layout.addWidget(bell_lbl)
        layout.addSpacing(14)

        title = QLabel('Who should we alert?')
        title.setFont(QFont('', 28, QFont.Bold))
        title.setStyleSheet(f'background: transparent; color: {TEXT};')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = QLabel("If EpiGuard detects a seizure, we'll send them a text immediately.")
        sub.setFont(QFont('', 13))
        sub.setStyleSheet(f'background: transparent; color: {MUTED};')
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addStretch(2)

        phone_lbl = self._section_label('EMERGENCY PHONE NUMBER')
        layout.addWidget(phone_lbl)
        layout.addSpacing(8)

        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText('+1 234 567 8900')
        self._phone_input.setFixedHeight(54)
        if self.profile.get('emergency_contact'):
            self._phone_input.setText(self.profile['emergency_contact'])
        layout.addWidget(self._phone_input)
        layout.addSpacing(8)

        hint = QLabel('Include country code  ·  e.g. +1 for US, +44 for UK, +421 for SK')
        hint.setFont(QFont('', 12))
        hint.setStyleSheet(f'color: {MUTED};')
        layout.addWidget(hint)

        if self.twilio_client is not None:
            layout.addSpacing(12)
            sms_row = QHBoxLayout()
            self._sms_btn = QPushButton('Send test message')
            self._sms_btn.setObjectName('sms_test')
            self._sms_btn.setFixedHeight(36)
            self._sms_btn.setFixedWidth(160)
            self._sms_btn.clicked.connect(self._send_test_sms)
            sms_row.addWidget(self._sms_btn)
            self._sms_status = QLabel('')
            self._sms_status.setFont(QFont('', 12))
            self._sms_status.setStyleSheet(f'color: {SUCCESS};')
            sms_row.addWidget(self._sms_status)
            sms_row.addStretch()
            layout.addLayout(sms_row)

        layout.addStretch(3)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        back_btn = QPushButton('← Back')
        back_btn.setObjectName('ghost')
        back_btn.setFixedSize(100, 48)
        back_btn.clicked.connect(self._show_survey)
        btn_row.addWidget(back_btn)

        skip_btn = QPushButton('Skip')
        skip_btn.setObjectName('ghost')
        skip_btn.setFixedSize(90, 48)
        skip_btn.clicked.connect(lambda: self._contact_save_and_proceed(''))
        btn_row.addWidget(skip_btn)

        next_btn = QPushButton('Save & Continue  →')
        next_btn.setObjectName('primary')
        next_btn.setFixedSize(200, 48)
        next_btn.clicked.connect(self._contact_next)
        btn_row.addWidget(next_btn)

        layout.addLayout(btn_row)
        self._fade_in(root)

    def _send_test_sms(self):
        phone = self._phone_input.text().strip()
        if not phone:
            self._sms_status.setText('Enter a number first')
            self._sms_status.setStyleSheet(f'color: {DANGER}; font-size: 12px;')
            return
        try:
            self.twilio_client.send_message_to(
                f'👋 EpiGuard test — alerts for {self._name()} are working!',
                to=phone
            )
            self._sms_status.setText('✓  Sent successfully')
        except Exception as e:
            self._sms_status.setText(f'Failed — check number')
            self._sms_status.setStyleSheet(f'color: {DANGER}; font-size: 12px;')

    def _contact_next(self):
        self._contact_save_and_proceed(self._phone_input.text().strip())

    def _contact_save_and_proceed(self, phone: str):
        self.profile['emergency_contact'] = phone
        self._show_done()

    # ── Screen 3: All Set ─────────────────────────────────────────────────────

    def _show_done(self):
        self._clear()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(72, 36, 72, 44)
        layout.setSpacing(0)

        layout.addWidget(_StepBar(3))
        layout.addStretch(1)

        # Success checkmark — plain label, no frame, avoids clipping artifact
        check_lbl = QLabel('✓')
        check_lbl.setFont(QFont('', 56, QFont.Bold))
        check_lbl.setStyleSheet(f'background: transparent; color: {SUCCESS};')
        check_lbl.setAlignment(Qt.AlignCenter)
        check_lbl.setFixedHeight(72)
        layout.addWidget(check_lbl)
        layout.addSpacing(14)

        title = QLabel(f'{self._name()} is now protected')
        title.setFont(QFont('', 28, QFont.Bold))
        title.setStyleSheet(f'background: transparent; color: {TEXT};')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(4)

        sub = QLabel('EpiGuard will monitor these signals during each session')
        sub.setFont(QFont('', 13))
        sub.setStyleSheet(f'background: transparent; color: {MUTED};')
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        layout.addStretch(1)

        # Weight bars
        card = QFrame()
        card.setObjectName('card')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 18, 24, 18)
        cl.setSpacing(13)

        sorted_weights = sorted(
            [(k, v) for k, v in self._weights.items() if k in WEIGHT_PLAIN],
            key=lambda x: x[1], reverse=True
        )[:5]

        for wk, wv in sorted_weights:
            label, icon = WEIGHT_PLAIN[wk]
            row = QHBoxLayout()
            row.setSpacing(12)

            name_lbl = QLabel(f'{icon}  {label}')
            name_lbl.setFont(QFont('', 13))
            name_lbl.setStyleSheet(f'color: {TEXT};')
            name_lbl.setFixedWidth(180)
            row.addWidget(name_lbl)

            bar_bg = QFrame()
            bar_bg.setFixedHeight(6)
            bar_bg.setStyleSheet(f'background: rgba(255,255,255,0.07); border-radius: 3px;')
            fill = QFrame(bar_bg)
            fill_w = max(20, int((wv / 0.80) * 200))
            fill.setGeometry(0, 0, fill_w, 6)
            color = SUCCESS if wv < 0.35 else ('#f59e0b' if wv < 0.60 else '#f87171')
            fill.setStyleSheet(f'background: {color}; border-radius: 3px;')
            row.addWidget(bar_bg, stretch=1)

            level_text = 'Low' if wv < 0.30 else ('Medium' if wv < 0.55 else 'High')
            lvl = QLabel(level_text)
            lvl.setFont(QFont('', 11))
            lvl.setFixedWidth(46)
            lvl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lvl.setStyleSheet(f'color: {color}; font-weight: 600;')
            row.addWidget(lvl)

            cl.addLayout(row)

        rest = len(self._weights) - 5
        if rest > 0:
            more_lbl = QLabel(f'+ {rest} more signals at baseline sensitivity')
            more_lbl.setFont(QFont('', 11))
            more_lbl.setStyleSheet(f'color: {MUTED};')
            more_lbl.setAlignment(Qt.AlignCenter)
            cl.addWidget(more_lbl)

        layout.addWidget(card)
        layout.addSpacing(14)

        # Contact summary
        phone = self.profile.get('emergency_contact', '')
        contact_row = QHBoxLayout()
        contact_row.addStretch()
        contact_dot = QLabel('●' if phone else '○')
        contact_dot.setStyleSheet(f'color: {SUCCESS if phone else MUTED}; font-size: 10px;')
        contact_row.addWidget(contact_dot)
        contact_row.addSpacing(6)
        contact_lbl = QLabel(
            f'Alerts go to {phone}' if phone
            else 'No emergency contact set'
        )
        contact_lbl.setFont(QFont('', 12))
        contact_lbl.setStyleSheet(f'color: {SUCCESS if phone else MUTED};')
        contact_row.addWidget(contact_lbl)
        contact_row.addStretch()
        layout.addLayout(contact_row)

        layout.addStretch(2)

        btn_label = 'Save & return' if self._patient else 'Start Monitoring  →'
        start_btn = QPushButton(btn_label)
        start_btn.setObjectName('start')
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.clicked.connect(self._finish)
        layout.addLayout(self._centered_btn(start_btn, width=260, height=54))

        self._fade_in(root)

    def _finish(self):
        now = datetime.now().isoformat()
        if self._patient is not None:
            from core import account_store as _as
            self._patient.update({
                'name': self.profile.get('patient_name', self._patient.get('name', '')),
                'age': self.profile.get('patient_age', self._patient.get('age', '')),
                'emergency_contact': self.profile.get('emergency_contact', ''),
                'setup_complete': True,
                'last_calibration': now,
                'weights': self._weights,
            })
            if not self._patient.get('created_at'):
                self._patient['created_at'] = now
            _as.save_patient(self._patient)
        else:
            self.profile['setup_complete'] = True
            self.profile['created_at'] = now
            self.profile['last_calibration'] = now
            save_profile(self.profile)
            save_weights(self._weights)
        print(f'✅ Setup complete. Weights: {self._weights}')
        self.close()


def run_wizard(client=None, twilio_client=None, patient=None) -> dict | None:
    app = QApplication.instance() or QApplication(sys.argv)
    wizard = SetupWizard(client=client, twilio_client=twilio_client, patient=patient)
    wizard.show()
    app.exec()
    return wizard.profile if wizard.profile.get('setup_complete') else None
