import sys
import json
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QTextBrowser, QPushButton, QScrollArea, QFrame, QSplitter,
    QProgressBar, QSlider, QSizePolicy, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor
from PySide6.QtWebEngineWidgets import QWebEngineView

from ui.theme import BG, TEXT, MUTED, ACCENT, ACCENT2, CARD, BORDER

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif;
}}
QLabel {{ color: {TEXT}; background: transparent; }}
QTextEdit {{
    background-color: {CARD};
    color: {TEXT};
    border: 1.5px solid rgba(177,173,161,0.45);
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
}}
QTextEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 13px;
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
    background-color: rgba(177,173,161,0.18);
    color: {TEXT};
    border: 1px solid rgba(177,173,161,0.45);
}}
QPushButton#secondary:hover {{ background-color: rgba(177,173,161,0.3); }}
QPushButton#save {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #15803d,stop:1 #16a34a);
    color: #ffffff;
}}
QPushButton#save:hover {{ background: #166534; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 5px; border-radius: 3px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(177,173,161,0.6); border-radius: 3px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QSplitter::handle {{ background: rgba(177,173,161,0.25); width: 1px; }}
QFrame#card {{
    background-color: {CARD};
    border-radius: 16px;
    border: 1px solid rgba(177,173,161,0.45);
}}
QProgressBar {{
    background-color: rgba(177,173,161,0.18);
    border-radius: 5px;
    border: none;
    max-height: 10px;
    min-height: 10px;
}}
QProgressBar::chunk {{ border-radius: 5px; }}
QSlider::groove:horizontal {{
    height: 4px; background: rgba(177,173,161,0.4); border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QPushButton#toggle {{
    background-color: transparent;
    color: {ACCENT};
    border: 1.5px solid rgba(193,95,60,0.35);
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#toggle:hover {{ background-color: rgba(193,95,60,0.06); }}
"""

AI_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: transparent; margin: 0; padding: 0; }}
  .content-wrap {{
    background: #ffffff;
    border-radius: 12px;
    color: #1c1917;
    font-family: 'SF Pro Text', 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.75;
    padding: 20px 22px;
  }}
  h1, h2, h3 {{
    color: #c15f3c;
    margin: 16px 0 6px 0;
    font-weight: 700;
    letter-spacing: -0.2px;
  }}
  h1 {{ font-size: 18px; }}
  h2 {{ font-size: 15px; }}
  h3 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #8a847a; }}
  p {{ margin-bottom: 10px; }}
  ul, ol {{ padding-left: 20px; margin-bottom: 10px; }}
  li {{ margin-bottom: 5px; }}
  strong {{ color: #a16207; }}
  em {{ color: #78350f; }}
  code {{
    background: rgba(177,173,161,0.15);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', 'Courier New', monospace;
    font-size: 12px;
    color: #b91c1c;
  }}
  .warning {{ color: #b45309; }}
  .ok {{ color: #15803d; font-weight: 600; }}
  .critical {{ color: #b91c1c; font-weight: 600; }}
  hr {{ border: none; border-top: 1px solid rgba(177,173,161,0.3); margin: 14px 0; }}
</style>
</head>
<body><div class="content-wrap">{content}</div></body>
</html>
"""


def markdown_to_html(md):
    """Convert basic markdown to HTML for display."""
    import html as html_module
    text = html_module.escape(md)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'^\* (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*?</li>(\n|$))+', lambda m: '<ul>' + m.group(0) + '</ul>', text, flags=re.DOTALL)
    parts = re.split(r'\n{2,}', text)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith(('<h', '<ul', '<ol', '<li')):
            result.append(part)
        else:
            result.append(f'<p>{part.replace(chr(10), "<br>")}</p>')
    return '\n'.join(result)


def parse_stats(summary_text):
    """Parse the summary text into structured metric dicts."""
    metrics = {}
    events = {}
    duration = None
    records = None

    for line in summary_text.split('\n'):
        line = line.strip()

        m = re.match(r'Session duration: (\d+) seconds', line)
        if m:
            duration = int(m.group(1))

        m = re.match(r'.+\((\d+) logged records\)', line)
        if m:
            records = int(m.group(1))

        m = re.match(r'- (\w+): avg=([\d.]+) max=([\d.]+)', line)
        if m:
            metrics[m.group(1)] = {'avg': float(m.group(2)), 'max': float(m.group(3))}

        m = re.search(r'avg=([\d.]+) BPM.*max=([\d.]+) BPM', line)
        if m:
            metrics['heart_rate'] = {'avg': float(m.group(1)), 'max': float(m.group(2))}

        m = re.match(r'- (.+?)(?:\s*\(>[^)]+\))?: (\d+) records = ([\d.]+)% of session', line)
        if m:
            events[m.group(1).strip()] = {'count': int(m.group(2)), 'pct': float(m.group(3))}

    return duration, records, metrics, events


class _EnterTextEdit(QTextEdit):
    """QTextEdit that emits enter_pressed on Enter (Shift+Enter inserts newline)."""
    enter_pressed = Signal()

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt as _Qt
        if event.key() in (_Qt.Key_Return, _Qt.Key_Enter) and not (event.modifiers() & _Qt.ShiftModifier):
            self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


class ChatWorker(QThread):
    finished = Signal(str)

    def __init__(self, client, messages):
        super().__init__()
        self.client = client
        self.messages = messages

    def run(self):
        try:
            from services.gpt_client import GEMINI_MODEL, _call_with_retry
            result = _call_with_retry(lambda: self.client.client.chat.completions.create(
                model=GEMINI_MODEL,
                messages=self.messages
            ).choices[0].message.content)
            self.finished.emit(result or "")
        except Exception as e:
            self.finished.emit(f"Sorry, I couldn't connect right now. ({e})")


class SummaryWindow:
    def show_summary(self, summary_text, ai_analysis=None, filepath=None,
                     ai_client=None, current_weights=None, on_weights_saved=None,
                     is_interim=False):
        app = QApplication.instance() or QApplication(sys.argv)
        window = SessionReviewWindow(
            summary_text=summary_text,
            ai_analysis=ai_analysis,
            filepath=filepath,
            ai_client=ai_client,
            current_weights=current_weights or {},
            on_weights_saved=on_weights_saved,
            is_interim=is_interim,
        )
        window.show()
        app.exec()


class SessionReviewWindow(QMainWindow):
    def __init__(self, summary_text, ai_analysis, filepath,
                 ai_client, current_weights, on_weights_saved, is_interim=False):
        super().__init__()
        self.ai_client = ai_client
        self.current_weights = dict(current_weights)
        self.on_weights_saved = on_weights_saved
        self.summary_text = summary_text
        self.chat_history = []
        self.pending_weights = None
        self.is_interim = is_interim

        self.setWindowTitle("EpiGuard — Mid-session Review" if is_interim else "EpiGuard — Session Review")
        self.resize(1300, 840)
        self.setStyleSheet(STYLE)
        self._center()
        self._build_ui(summary_text, ai_analysis, filepath)

        # fade-in
        effect = QGraphicsOpacityEffect(self.centralWidget())
        self.centralWidget().setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b'opacity', self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuart)
        anim.start()

        weight_descriptions = {
            "w_shake":    "sensitivity to head shaking/tremors",
            "w_blink":    "sensitivity to abnormal blinking",
            "w_twitch":   "sensitivity to facial twitching",
            "w_asym":     "sensitivity to facial asymmetry/drooping",
            "w_freeze":   "sensitivity to face freezing/absence episodes",
            "w_bpm":      "importance of heart rate changes",
            "w_color":    "sensitivity to face color changes",
            "w_blink_nc": "blinking sensitivity for non-convulsive alerts",
            "w_bpm_nc":   "heart rate importance for non-convulsive alerts",
        }
        readable_weights = {
            weight_descriptions.get(k, k): round(v, 2)
            for k, v in current_weights.items()
        }

        self.chat_history.append({"role": "system", "content": (
            "You are EpiGuard's friendly assistant helping a parent or caregiver review their child's "
            "seizure monitoring session. You are talking to a non-technical person — a parent, caregiver, "
            "or the person being monitored. NEVER use technical variable names like w_shake, w_blink, etc. "
            "Instead use plain descriptions like 'head shaking sensitivity' or 'blinking detection'. "
            "The AI analysis has already assessed this session — do NOT contradict or re-assess it. "
            "Your job is only to ask 1-2 short follow-up questions to understand if the detections matched "
            "what the caregiver actually observed, then adjust the monitoring sensitivity accordingly. "
            "When proposing changes, explain them in plain English like 'I'll make the system less sensitive "
            "to head movements since those were normal for this person'. "
            "When you have enough info to update settings, output a single ```json``` block with ALL nine keys "
            "(w_bpm, w_color, w_shake, w_twitch, w_blink, w_freeze, w_asym, w_blink_nc, w_bpm_nc) and their "
            "new numeric values — then explain the changes in plain language. "
            "Do NOT output a json block just to show current values. Keep responses short and warm."
        )})
        self.chat_history.append({"role": "user", "content": (
            f"Session data:\n{summary_text}\n\n"
            f"Current monitoring sensitivities: {json.dumps(readable_weights)}\n\n"
            f"AI session assessment (already complete — do not repeat or contradict this):\n"
            f"{ai_analysis or 'Not available'}"
        )})

        if self.ai_client:
            QTimer.singleShot(500, self._send_initial_greeting)

    def _center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self, summary_text, ai_analysis, filepath):
        # Parse stats early so we can show duration/records in the header
        duration, records, metrics, events = parse_stats(summary_text)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Terracotta accent stripe
        accent_line = QWidget()
        accent_line.setFixedHeight(3)
        accent_line.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT2});"
        )
        main_layout.addWidget(accent_line)

        # Header
        header = QWidget()
        header.setStyleSheet(f"background-color: {BG}; border-bottom: 1px solid rgba(177,173,161,0.35);")
        header.setFixedHeight(68)
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(28, 0, 28, 0)
        h_row.setSpacing(12)

        # Logo badge
        logo = QLabel("EG")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont('', 12, QFont.Bold))
        logo.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {ACCENT},stop:1 {ACCENT2});"
            "color: #ffffff; border-radius: 10px;"
        )
        h_row.addWidget(logo)

        # Title
        title = QLabel("Mid-session Review" if self.is_interim else "Session Review")
        title.setFont(QFont('', 17, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        h_row.addWidget(title)
        h_row.addSpacing(8)

        # Status badge
        badge_text = "Paused" if self.is_interim else "Complete"
        badge = QLabel(f"● {badge_text}")
        badge.setFont(QFont('', 11, QFont.Bold))
        badge.setFocusPolicy(Qt.NoFocus)
        badge.setStyleSheet(
            f"background: rgba(193,95,60,0.13); color: {ACCENT};"
            "border-radius: 8px; padding: 4px 10px; border: none;"
        )
        h_row.addWidget(badge)

        # Session meta: duration + records as muted text in header
        if duration is not None:
            mins = duration // 60
            secs = duration % 60
            dur_text = f"{mins}m {secs}s" if mins else f"{secs}s"
            meta_parts = [dur_text]
            if records:
                meta_parts.append(f"{records} records")
            meta_lbl = QLabel("  ·  " + "  ·  ".join(meta_parts))
            meta_lbl.setFont(QFont('', 12))
            meta_lbl.setStyleSheet(f"color: {MUTED};")
            h_row.addWidget(meta_lbl)

        h_row.addStretch()

        if filepath:
            fp = QLabel(filepath.split('/')[-1] if '/' in filepath else filepath)
            fp.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            h_row.addWidget(fp)
            h_row.addSpacing(16)

        new_session_btn = QPushButton("▶  New Session")
        new_session_btn.setFixedHeight(38)
        new_session_btn.setFocusPolicy(Qt.NoFocus)
        new_session_btn.setCursor(Qt.PointingHandCursor)
        new_session_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT2}); color: #ffffff; border: none;"
            "border-radius: 10px; font-size: 13px; font-weight: bold; padding: 0 18px; }"
            f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #ad5434,stop:1 #c46444); }"
        )
        new_session_btn.clicked.connect(self._start_new_session)
        h_row.addWidget(new_session_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(38)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT}; border: 1px solid rgba(177,173,161,0.55);"
            "border-radius: 10px; font-size: 13px; font-weight: 600; padding: 0 18px; }"
            "QPushButton:hover { background: rgba(177,173,161,0.2); }"
        )
        close_btn.clicked.connect(self.close)
        h_row.addWidget(close_btn)

        main_layout.addWidget(header)

        if self.is_interim:
            pause_bar = QWidget()
            pause_bar.setStyleSheet(
                "background-color: rgba(193,95,60,0.07);"
                "border-bottom: 1px solid rgba(193,95,60,0.15);"
            )
            pause_bar.setFixedHeight(34)
            pb_layout = QHBoxLayout(pause_bar)
            pb_layout.setContentsMargins(28, 0, 28, 0)
            pb_lbl = QLabel("⏸  Monitoring is paused — close this window to resume")
            pb_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: 600;")
            pb_layout.addWidget(pb_lbl)
            pb_layout.addStretch()
            main_layout.addWidget(pause_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter, stretch=1)

        # ── Left panel ────────────────────────────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("background: transparent;")
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(28, 28, 18, 28)
        left_layout.setSpacing(16)

        # AI analysis card
        if ai_analysis:
            ai_card = self._make_card()
            ai_card_layout = QVBoxLayout(ai_card)
            ai_card_layout.setContentsMargins(20, 18, 20, 18)
            ai_card_layout.setSpacing(10)

            ai_hdr_row = QHBoxLayout()
            ai_dot = QLabel()
            ai_dot.setFixedSize(10, 10)
            ai_dot.setStyleSheet("background: #15803d; border-radius: 5px;")
            ai_hdr_row.addWidget(ai_dot)
            ai_hdr_row.addSpacing(8)
            ai_hdr_lbl = QLabel("AI Analysis")
            ai_hdr_lbl.setFont(QFont('', 13, QFont.Bold))
            ai_hdr_lbl.setStyleSheet("color: #15803d;")
            ai_hdr_row.addWidget(ai_hdr_lbl)
            ai_hdr_row.addStretch()
            ai_card_layout.addLayout(ai_hdr_row)

            web = QWebEngineView()
            web.setMinimumHeight(200)
            html_content = markdown_to_html(ai_analysis)
            web.setHtml(AI_HTML_TEMPLATE.format(content=html_content))
            web.setStyleSheet("background: transparent; border: none;")
            web.page().setBackgroundColor(QColor(0, 0, 0, 0))
            ai_card_layout.addWidget(web)
            left_layout.addWidget(ai_card)

        # Detection scores section
        left_layout.addWidget(self._section_label("Detection Scores"))
        left_layout.addSpacing(4)

        score_map = [
            ('head_score',   'Head shake',      '#b91c1c'),
            ('blink_score',  'Blinking',         '#d97706'),
            ('eye_score',    'Eye movement',     '#ca8a04'),
            ('droop_score',  'Face asymmetry',   '#7e22ce'),
            ('freeze_score', 'Face freeze',      '#0369a1'),
            ('twitch_score', 'Twitching',        '#15803d'),
            ('health_score', 'Health score',     '#b91c1c'),
        ]

        scores_card = self._make_card()
        scores_layout = QVBoxLayout(scores_card)
        scores_layout.setContentsMargins(20, 18, 20, 18)
        scores_layout.setSpacing(14)

        has_scores = False
        for key, label, color in score_map:
            if key not in metrics:
                continue
            has_scores = True
            avg = metrics[key]['avg']
            mx  = metrics[key]['max']

            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_v = QVBoxLayout(row_widget)
            row_v.setContentsMargins(0, 0, 0, 0)
            row_v.setSpacing(5)

            lbl_row = QHBoxLayout()
            lbl_row.setSpacing(0)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
            lbl_row.addWidget(dot)
            lbl_row.addSpacing(8)
            name_lbl = QLabel(label)
            name_lbl.setFont(QFont('', 12))
            name_lbl.setStyleSheet(f"color: {TEXT};")
            lbl_row.addWidget(name_lbl)
            lbl_row.addStretch()
            avg_pct = int(avg * 100)
            val_lbl = QLabel(f"{avg_pct}%  max {mx:.2f}")
            val_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px; font-weight: 500;")
            lbl_row.addWidget(val_lbl)
            row_v.addLayout(lbl_row)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(avg_pct)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar {{ background: rgba(177,173,161,0.18); border-radius: 5px; border: none; }}"
                f"QProgressBar::chunk {{ background-color: {color}; border-radius: 5px; }}"
            )
            row_v.addWidget(bar)
            scores_layout.addWidget(row_widget)

        if not has_scores:
            no_data = QLabel("No score data recorded in this session.")
            no_data.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
            scores_layout.addWidget(no_data)

        left_layout.addWidget(scores_card)

        # Heart rate card
        if 'heart_rate' in metrics:
            hr = metrics['heart_rate']
            hr_card = self._make_card()
            hr_layout = QHBoxLayout(hr_card)
            hr_layout.setContentsMargins(20, 16, 20, 16)

            hr_left = QVBoxLayout()
            hr_left.setSpacing(2)
            hr_title = QLabel("Heart Rate")
            hr_title.setFont(QFont('', 12, QFont.Bold))
            hr_title.setStyleSheet("color: #b91c1c;")
            hr_left.addWidget(hr_title)
            hr_sub = QLabel("rPPG measurement")
            hr_sub.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            hr_left.addWidget(hr_sub)
            hr_layout.addLayout(hr_left)
            hr_layout.addStretch()

            hr_right = QVBoxLayout()
            hr_right.setAlignment(Qt.AlignRight)
            hr_right.setSpacing(2)
            avg_lbl = QLabel(f"{hr.get('avg', 0):.0f} BPM avg")
            avg_lbl.setFont(QFont('', 15, QFont.Bold))
            avg_lbl.setStyleSheet("color: #b91c1c;")
            avg_lbl.setAlignment(Qt.AlignRight)
            hr_right.addWidget(avg_lbl)
            max_lbl = QLabel(f"peak {hr.get('max', 0):.0f} BPM")
            max_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            max_lbl.setAlignment(Qt.AlignRight)
            hr_right.addWidget(max_lbl)
            hr_layout.addLayout(hr_right)
            left_layout.addWidget(hr_card)

        # Manual weight sliders (collapsible)
        self._sliders_visible = False
        self._weight_sliders = {}

        toggle_btn = QPushButton("Edit detection weights manually")
        toggle_btn.setObjectName("toggle")
        toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toggle_btn.setCursor(Qt.PointingHandCursor)
        toggle_btn.clicked.connect(self._toggle_sliders)
        left_layout.addWidget(toggle_btn)

        self._sliders_card = self._make_card()
        self._sliders_card.setVisible(False)
        sliders_layout = QVBoxLayout(self._sliders_card)
        sliders_layout.setContentsMargins(20, 18, 20, 18)
        sliders_layout.setSpacing(14)

        sliders_hint = QLabel(
            "Drag to adjust how sensitive each signal is. Higher = triggers alerts more easily."
        )
        sliders_hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        sliders_hint.setWordWrap(True)
        sliders_layout.addWidget(sliders_hint)

        weight_labels = [
            ('w_shake',    'Head shake',        'How strongly head tremors trigger convulsive alerts'),
            ('w_blink',    'Blinking',           'Sensitivity to abnormal rapid or absent blinking'),
            ('w_twitch',   'Twitching',          'How much facial twitches contribute to alerts'),
            ('w_asym',     'Face asymmetry',     'Sensitivity to one-sided facial drooping'),
            ('w_freeze',   'Face freeze',        'How long a still face triggers a non-convulsive alert'),
            ('w_bpm',      'Heart rate',         'Contribution of elevated heart rate to alerts'),
            ('w_color',    'Face color',         'Sensitivity to skin color changes (pallor/flushing)'),
            ('w_blink_nc', 'Blink (non-conv)',   'Blinking weight for non-convulsive risk score'),
            ('w_bpm_nc',   'BPM (non-conv)',     'Heart rate weight for non-convulsive risk score'),
        ]

        for wkey, label, description in weight_labels:
            current_val = self.current_weights.get(wkey, 0.3)
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)

            top_row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont('', 12, QFont.Bold))
            lbl.setStyleSheet(f"color: {TEXT};")
            top_row.addWidget(lbl)
            top_row.addStretch()
            val_lbl = QLabel(f"{current_val:.2f}")
            val_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: bold; min-width: 36px;")
            val_lbl.setAlignment(Qt.AlignRight)
            top_row.addWidget(val_lbl)
            row_layout.addLayout(top_row)

            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            row_layout.addWidget(desc_lbl)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(5, 80)
            slider.setValue(int(current_val * 100))
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(f"{v/100:.2f}"))
            row_layout.addWidget(slider)

            self._weight_sliders[wkey] = slider
            sliders_layout.addWidget(row_widget)

        apply_btn = QPushButton("Save weights")
        apply_btn.setObjectName("primary")
        apply_btn.setMinimumHeight(42)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_manual_weights)
        sliders_layout.addWidget(apply_btn)

        left_layout.addWidget(self._sliders_card)
        left_layout.addStretch()
        left_scroll.setWidget(left_inner)
        splitter.addWidget(left_scroll)

        # ── Right panel — chat ────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background-color: {BG};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 28, 28, 28)
        right_layout.setSpacing(14)

        right_layout.addWidget(self._section_label("Adaptive Calibration"))

        chat_hint = QLabel("Answer the questions below to improve future detection accuracy.")
        chat_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        right_layout.addWidget(chat_hint)
        right_layout.addSpacing(2)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("background: transparent;")
        self.chat_messages_widget = QWidget()
        self.chat_messages_widget.setStyleSheet("background: transparent;")
        self.chat_messages_layout = QVBoxLayout(self.chat_messages_widget)
        self.chat_messages_layout.setSpacing(10)
        self.chat_messages_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_messages_widget)
        right_layout.addWidget(self.chat_scroll, stretch=1)

        # Input row
        input_container = QWidget()
        input_container.setStyleSheet("background: transparent;")
        input_h = QHBoxLayout(input_container)
        input_h.setContentsMargins(0, 0, 0, 0)
        input_h.setSpacing(8)

        self.chat_input = _EnterTextEdit()
        self.chat_input.setPlaceholderText("Type your answer… (Enter to send, Shift+Enter for new line)")
        self.chat_input.setFixedHeight(60)
        self.chat_input.setStyleSheet(
            f"background-color: {CARD}; border: 1.5px solid rgba(177,173,161,0.45);"
            "border-radius: 12px; padding: 8px 12px; font-size: 13px;"
        )
        self.chat_input.enter_pressed.connect(self._on_send)
        input_h.addWidget(self.chat_input, stretch=1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(80, 60)
        self.send_btn.setObjectName("primary")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        input_h.addWidget(self.send_btn)
        right_layout.addWidget(input_container)

        self.save_btn = QPushButton("Save Updated Weights")
        self.save_btn.setObjectName("save")
        self.save_btn.setMinimumHeight(44)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setVisible(False)
        self.save_btn.clicked.connect(self._on_save_weights)
        right_layout.addWidget(self.save_btn)

        splitter.addWidget(right)
        splitter.setSizes([580, 580])

    # ── Helpers ───────────────────────────────────────────────────────────

    def _section_label(self, text):
        # Widget composition avoids Qt's CSS border-left text-clipping bug
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)
        bar = QWidget()
        bar.setFixedSize(3, 14)
        bar.setStyleSheet(f"background: {ACCENT}; border-radius: 1px;")
        row.addWidget(bar, alignment=Qt.AlignVCenter)
        lbl = QLabel(text.upper())
        lbl.setFont(QFont('', 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {MUTED}; letter-spacing: 0.8px; background: transparent;")
        row.addWidget(lbl)
        row.addStretch()
        return w

    def _make_card(self):
        card = QFrame()
        card.setObjectName("card")
        return card

    def _info_chip(self, icon_type, text):
        lbl = QLabel(text)
        lbl.setFont(QFont('', 12))
        lbl.setStyleSheet(
            f"background: {CARD}; color: {TEXT};"
            "border-radius: 20px; padding: 5px 14px;"
            f"border: 1px solid rgba(177,173,161,0.4);"
        )
        return lbl

    def _add_bubble(self, text, role):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        if role == "user":
            bubble = QLabel(text)
            bubble.setWordWrap(True)
            bubble.setFont(QFont('', 13))
            bubble.setMaximumWidth(360)
            bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bubble.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});"
                "color: #ffffff; border-radius: 16px; border-bottom-right-radius: 3px;"
                "padding: 10px 16px;"
            )
            row.addStretch()
            row.addWidget(bubble)
        else:
            html_content = markdown_to_html(text)
            bubble = QTextBrowser()
            bubble.setHtml(f"""
                <html><head><style>
                body {{
                    background: transparent;
                    color: #1c1917;
                    font-family: 'SF Pro Text', 'Segoe UI', sans-serif;
                    font-size: 13px;
                    line-height: 1.65;
                    margin: 0; padding: 0;
                }}
                h1,h2,h3 {{ color: #c15f3c; margin: 8px 0 4px 0; font-size: 14px; }}
                strong {{ color: #7e22ce; }}
                ul,ol {{ padding-left: 18px; margin: 4px 0; }}
                li {{ margin-bottom: 2px; }}
                p {{ margin: 0 0 8px 0; }}
                code {{ background: #f4f3ee; border: 1px solid rgba(177,173,161,0.3);
                        color: #b91c1c; padding: 1px 5px; border-radius: 4px;
                        font-family: monospace; font-size: 12px; }}
                </style></head>
                <body>{html_content}</body></html>
            """)
            bubble.setReadOnly(True)
            bubble.setFrameShape(QTextBrowser.NoFrame)
            bubble.setMaximumWidth(440)
            bubble.setMinimumWidth(200)
            bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            bubble.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            bubble.setStyleSheet(
                f"background-color: {CARD}; border-radius: 16px; border-bottom-left-radius: 3px;"
                "padding: 10px 14px; border: 1px solid rgba(177,173,161,0.25);"
            )
            def _resize_bubble(b=bubble):
                b.document().setTextWidth(b.viewport().width())
                h = int(b.document().size().height()) + 28
                b.setFixedHeight(h)
            QTimer.singleShot(50, _resize_bubble)
            row.addWidget(bubble)
            row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        count = self.chat_messages_layout.count()
        self.chat_messages_layout.insertWidget(count - 1, container)
        QTimer.singleShot(60, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def _set_thinking(self, thinking):
        self.send_btn.setEnabled(not thinking)
        self.send_btn.setText("..." if thinking else "Send")
        if thinking:
            self._thinking_bubble = QLabel("Thinking...")
            self._thinking_bubble.setStyleSheet(
                f"background-color: {CARD}; border: 1px solid rgba(177,173,161,0.3);"
                "color: #8a847a; border-radius: 16px; border-bottom-left-radius: 3px;"
                "padding: 10px 16px; font-size: 13px; font-style: italic;"
            )
            self._thinking_bubble.setFixedWidth(130)
            row = QHBoxLayout()
            row.addWidget(self._thinking_bubble)
            row.addStretch()
            self._thinking_container = QWidget()
            self._thinking_container.setStyleSheet("background: transparent;")
            self._thinking_container.setLayout(row)
            count = self.chat_messages_layout.count()
            self.chat_messages_layout.insertWidget(count - 1, self._thinking_container)
            QTimer.singleShot(60, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ))
            self._dot_state = 0
            self._dot_timer = QTimer()
            self._dot_timer.timeout.connect(self._animate_dots)
            self._dot_timer.start(400)
        else:
            if hasattr(self, '_dot_timer'):
                self._dot_timer.stop()
            if hasattr(self, '_thinking_container'):
                self._thinking_container.setParent(None)
                self._thinking_container.deleteLater()

    def _animate_dots(self):
        patterns = ["Thinking.", "Thinking..", "Thinking..."]
        self._dot_state = (self._dot_state + 1) % 3
        if hasattr(self, '_thinking_bubble'):
            self._thinking_bubble.setText(patterns[self._dot_state])

    # ── Chat logic ────────────────────────────────────────────────────────

    def _send_initial_greeting(self):
        self._set_thinking(True)
        msgs = self.chat_history + [{"role": "user", "content":
            "Greet the caregiver warmly in one short sentence. Then ask ONE simple question "
            "about what they observed during the session — something that helps you understand "
            "if the detections matched reality. Do not repeat or summarize the AI analysis. "
            "Do not mention any technical names. Keep it under 3 sentences total."}]
        self._worker = ChatWorker(self.ai_client, msgs)
        self._worker.finished.connect(self._on_ai_reply)
        self._worker.start()

    def _on_send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_input.clear()
        self._add_bubble(text, "user")
        self.chat_history.append({"role": "user", "content": text})
        self._set_thinking(True)
        self._worker = ChatWorker(self.ai_client, self.chat_history)
        self._worker.finished.connect(self._on_ai_reply)
        self._worker.start()

    def _on_ai_reply(self, text):
        self.chat_history.append({"role": "assistant", "content": text})
        self._set_thinking(False)

        display_text = text
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                valid = {
                    k: round(max(0.05, min(0.80, float(v))), 3)
                    for k, v in parsed.items()
                    if k in self.current_weights
                }
                if valid:
                    self.pending_weights = valid
                    self.save_btn.setVisible(True)
                    display_text = re.sub(
                        r"```json.*?```",
                        "Weight update ready — click 'Save Updated Weights' below to apply.",
                        text, flags=re.DOTALL
                    )
            except Exception:
                pass

        self._add_bubble(display_text, "ai")

    def _on_save_weights(self):
        if self.pending_weights and self.on_weights_saved:
            self.current_weights.update(self.pending_weights)
            self.on_weights_saved(self.current_weights)
            for k, slider in self._weight_sliders.items():
                if k in self.current_weights:
                    slider.blockSignals(True)
                    slider.setValue(int(self.current_weights[k] * 100))
                    slider.blockSignals(False)
            self.save_btn.setText("Weights saved!")
            self.save_btn.setEnabled(False)
            self.chat_history.append({
                "role": "user",
                "content": "The weights have been saved. Continue helping me calibrate if needed."
            })
            QTimer.singleShot(800, self._re_enable_save)

    def _re_enable_save(self):
        self.save_btn.setText("Save Updated Weights")
        self.save_btn.setEnabled(True)
        self.save_btn.setVisible(False)
        self.pending_weights = None

    def _start_new_session(self):
        import subprocess, os
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'main.py')
        subprocess.Popen([sys.executable, os.path.normpath(script)])
        self.close()

    def _toggle_sliders(self):
        self._sliders_visible = not self._sliders_visible
        self._sliders_card.setVisible(self._sliders_visible)

    def _apply_manual_weights(self):
        new_weights = {k: round(s.value() / 100, 2) for k, s in self._weight_sliders.items()}
        self.current_weights.update(new_weights)
        if self.on_weights_saved:
            self.on_weights_saved(self.current_weights)
        self._add_bubble("I've manually updated the detection weights.", "user")
        self._add_bubble(
            "Weights saved! I'll use these as the baseline if you continue the conversation.",
            "ai"
        )
        self.chat_history.append({
            "role": "user",
            "content": f"The caregiver manually set these weights: {json.dumps(new_weights)}. "
                       "Acknowledge and ask if they'd like to continue refining through conversation."
        })
