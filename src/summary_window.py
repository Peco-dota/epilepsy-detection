import sys
import json
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QTextBrowser, QPushButton, QScrollArea, QFrame, QSplitter,
    QProgressBar, QSlider, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWebEngineWidgets import QWebEngineView

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
    font-size: 13px;
}
QTextEdit:focus { border: 1px solid #89b4fa; }
QPushButton {
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
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
QPushButton#save {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#save:hover { background-color: #94e2d5; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #313244; width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical { background: #585b70; border-radius: 3px; }
QSplitter::handle { background: #45475a; width: 1px; }
QFrame#card {
    background-color: #313244;
    border-radius: 12px;
}
QProgressBar {
    background-color: #45475a;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    border: none;
}
QProgressBar::chunk {
    border-radius: 4px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #45475a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background: #89b4fa;
    border-radius: 2px;
}
QPushButton#apply {
    background-color: #cba6f7;
    color: #1e1e2e;
}
QPushButton#apply:hover { background-color: #b4befe; }
QPushButton#toggle {
    background-color: transparent;
    color: #89b4fa;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#toggle:hover { background-color: #313244; }
"""

# HTML template for the AI analysis pane (renders markdown properly)
AI_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #313244;
    color: #cdd6f4;
    font-family: -apple-system, 'SF Pro Text', 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.7;
    padding: 18px 20px;
  }}
  h1, h2, h3 {{
    color: #89b4fa;
    margin: 14px 0 6px 0;
    font-weight: 600;
  }}
  h1 {{ font-size: 18px; }}
  h2 {{ font-size: 16px; }}
  h3 {{ font-size: 14px; }}
  p {{ margin-bottom: 10px; }}
  ul, ol {{ padding-left: 20px; margin-bottom: 10px; }}
  li {{ margin-bottom: 4px; }}
  strong {{ color: #cba6f7; }}
  em {{ color: #f5c2e7; }}
  code {{
    background: #45475a;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
  }}
  .warning {{ color: #f9e2af; }}
  .ok {{ color: #a6e3a1; }}
  .critical {{ color: #f38ba8; }}
</style>
</head>
<body>{content}</body>
</html>
"""


def markdown_to_html(md):
    """Convert basic markdown to HTML for display."""
    import html as html_module
    text = html_module.escape(md)
    # headers
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # bold / italic / inline code
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # bullet lists
    text = re.sub(r'^\* (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*?</li>(\n|$))+', lambda m: '<ul>' + m.group(0) + '</ul>', text, flags=re.DOTALL)
    # paragraphs (double newline)
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

        # "Session duration: 20 seconds (20 logged records)"
        m = re.match(r'Session duration: (\d+) seconds', line)
        if m:
            duration = int(m.group(1))

        m = re.match(r'.+\((\d+) logged records\)', line)
        if m:
            records = int(m.group(1))

        # new format: "- key: avg=X max=Y"
        m = re.match(r'- (\w+): avg=([\d.]+) max=([\d.]+)', line)
        if m:
            metrics[m.group(1)] = {
                'avg': float(m.group(2)),
                'max': float(m.group(3)),
            }

        # heart rate: "avg=72 BPM, max=96 BPM"
        m = re.search(r'avg=([\d.]+) BPM.*max=([\d.]+) BPM', line)
        if m:
            metrics['heart_rate'] = {'avg': float(m.group(1)), 'max': float(m.group(2))}

        # high-score event lines: "- Label (>X): N records = Y% of session"
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
            from gpt_client import GEMINI_MODEL, _call_with_retry
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
        self.resize(1280, 820)
        self.setStyleSheet(STYLE)
        self._center()
        self._build_ui(summary_text, ai_analysis, filepath)

        # human-readable names for weights — never expose technical keys to the user
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
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #181825; border-bottom: 1px solid #313244;")
        header.setFixedHeight(60)
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(24, 0, 24, 0)
        title = QLabel("⏱  Mid-session Review" if self.is_interim else "📊  Session Review")
        title.setFont(QFont("SF Pro Display", 17, QFont.Bold))
        title.setStyleSheet("color: #89b4fa;")
        h_row.addWidget(title)
        h_row.addStretch()
        if filepath:
            fp = QLabel(f"📁  {filepath}")
            fp.setStyleSheet("color: #6c7086; font-size: 11px;")
            h_row.addWidget(fp)

        h_row.addSpacing(20)
        new_session_btn = QPushButton("▶  Start New Session")
        new_session_btn.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e; border-radius: 8px;"
            "font-size: 13px; font-weight: bold; border: none; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #94e2d5; }"
        )
        new_session_btn.clicked.connect(self._start_new_session)
        h_row.addWidget(new_session_btn)

        close_btn = QPushButton("✕  Close")
        close_btn.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; border-radius: 8px;"
            "font-size: 13px; font-weight: bold; border: none; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        close_btn.clicked.connect(self.close)
        h_row.addWidget(close_btn)

        main_layout.addWidget(header)

        if self.is_interim:
            pause_bar = QWidget()
            pause_bar.setStyleSheet("background-color: #1e3a5f;")
            pause_bar.setFixedHeight(32)
            pb_layout = QHBoxLayout(pause_bar)
            pb_layout.setContentsMargins(24, 0, 24, 0)
            pb_lbl = QLabel("⏸  Monitoring is paused — close this window to resume")
            pb_lbl.setStyleSheet("color: #89b4fa; font-size: 12px;")
            pb_layout.addWidget(pb_lbl)
            pb_layout.addStretch()
            main_layout.addWidget(pause_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter, stretch=1)

        # ── Left panel ────────────────────────────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("background: #1e1e2e;")
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(24, 24, 16, 24)
        left_layout.setSpacing(16)

        report_lbl = QLabel("Session Report")
        report_lbl.setFont(QFont("SF Pro Display", 15, QFont.Bold))
        left_layout.addWidget(report_lbl)

        # AI analysis — rendered as HTML
        if ai_analysis:
            ai_card = self._make_card()
            ai_card_layout = QVBoxLayout(ai_card)
            ai_card_layout.setContentsMargins(16, 14, 16, 14)
            hdr = QLabel("🤖  AI Analysis")
            hdr.setFont(QFont("SF Pro Text", 12, QFont.Bold))
            hdr.setStyleSheet("color: #a6e3a1; margin-bottom: 6px;")
            ai_card_layout.addWidget(hdr)

            web = QWebEngineView()
            web.setMinimumHeight(220)
            html_content = markdown_to_html(ai_analysis)
            web.setHtml(AI_HTML_TEMPLATE.format(content=html_content))
            web.setStyleSheet("background: transparent; border: none;")
            ai_card_layout.addWidget(web)
            left_layout.addWidget(ai_card)

        # Metric cards
        duration, records, metrics, events = parse_stats(summary_text)

        # Session info bar
        if duration is not None:
            info_row = QHBoxLayout()
            info_row.setSpacing(12)
            info_row.addWidget(self._info_chip(f"⏱  {duration}s session"))
            if records:
                info_row.addWidget(self._info_chip(f"📋  {records} records"))
            info_row.addStretch()
            left_layout.addLayout(info_row)

        # Score bars
        score_map = {
            'head_score':   ('🤚  Head shake',    '#f38ba8'),
            'blink_score':  ('👁  Blinking',       '#fab387'),
            'eye_score':    ('👁  Eye movement',   '#f9e2af'),
            'droop_score':  ('↔️  Face asymmetry', '#cba6f7'),
            'freeze_score': ('🧊  Face freeze',    '#89dceb'),
            'twitch_score': ('⚡  Twitching',      '#a6e3a1'),
            'health_score': ('❤️  Health score',   '#f38ba8'),
        }
        scores_card = self._make_card()
        scores_layout = QVBoxLayout(scores_card)
        scores_layout.setContentsMargins(16, 14, 16, 14)
        scores_layout.setSpacing(10)
        hdr2 = QLabel("📈  Detection Scores")
        hdr2.setFont(QFont("SF Pro Text", 12, QFont.Bold))
        hdr2.setStyleSheet("color: #89b4fa; margin-bottom: 4px;")
        scores_layout.addWidget(hdr2)

        has_scores = False
        for key, (label, color) in score_map.items():
            if key in metrics:
                has_scores = True
                avg = metrics[key]['avg']
                mx = metrics[key]['max']
                row = QHBoxLayout()
                lbl = QLabel(label)
                lbl.setFixedWidth(160)
                lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
                row.addWidget(lbl)

                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(int(avg * 100))
                bar.setFixedHeight(8)
                bar.setTextVisible(False)
                bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}"
                )
                row.addWidget(bar, stretch=1)

                val_lbl = QLabel(f"avg {avg:.2f}   max {mx:.2f}")
                val_lbl.setStyleSheet("color: #6c7086; font-size: 11px; min-width: 110px;")
                val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(val_lbl)
                scores_layout.addLayout(row)

        if not has_scores:
            no_data = QLabel("No score data recorded in this session.")
            no_data.setStyleSheet("color: #6c7086; font-size: 12px;")
            scores_layout.addWidget(no_data)

        left_layout.addWidget(scores_card)

        # Heart rate chip
        if 'heart_rate' in metrics:
            hr = metrics['heart_rate']
            hr_card = self._make_card()
            hr_layout = QHBoxLayout(hr_card)
            hr_layout.setContentsMargins(16, 12, 16, 12)
            hr_icon = QLabel("❤️  Heart Rate")
            hr_icon.setFont(QFont("SF Pro Text", 12, QFont.Bold))
            hr_icon.setStyleSheet("color: #f38ba8;")
            hr_layout.addWidget(hr_icon)
            hr_layout.addStretch()
            hr_val = QLabel(f"avg {hr.get('avg', 0):.0f} BPM  ·  max {hr.get('max', 0):.0f} BPM")
            hr_val.setStyleSheet("color: #cdd6f4; font-size: 13px;")
            hr_layout.addWidget(hr_val)
            left_layout.addWidget(hr_card)

        # ── Manual weight sliders (collapsible) ───────────────────────────
        self._sliders_visible = False
        self._weight_sliders = {}

        toggle_btn = QPushButton("⚙️  Edit detection weights manually")
        toggle_btn.setObjectName("toggle")
        toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toggle_btn.clicked.connect(self._toggle_sliders)
        left_layout.addWidget(toggle_btn)

        self._sliders_card = self._make_card()
        self._sliders_card.setVisible(False)
        sliders_layout = QVBoxLayout(self._sliders_card)
        sliders_layout.setContentsMargins(16, 14, 16, 14)
        sliders_layout.setSpacing(12)

        sliders_hint = QLabel(
            "Drag to adjust how sensitive each signal is. Higher = triggers alerts more easily."
        )
        sliders_hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        sliders_hint.setWordWrap(True)
        sliders_layout.addWidget(sliders_hint)

        weight_labels = [
            ('w_shake',    '🤚  Head shake',     'How strongly head tremors trigger convulsive alerts'),
            ('w_blink',    '👁  Blinking',        'Sensitivity to abnormal rapid or absent blinking'),
            ('w_twitch',   '⚡  Twitching',       'How much facial twitches contribute to alerts'),
            ('w_asym',     '↔️  Face asymmetry',  'Sensitivity to one-sided facial drooping'),
            ('w_freeze',   '🧊  Face freeze',     'How long a still face triggers a non-convulsive alert'),
            ('w_bpm',      '❤️  Heart rate',      'Contribution of elevated heart rate to alerts'),
            ('w_color',    '🎨  Face color',      'Sensitivity to skin color changes (pallor/flushing)'),
            ('w_blink_nc', '👁  Blink (non-conv)','Blinking weight for non-convulsive risk score'),
            ('w_bpm_nc',   '❤️  BPM (non-conv)', 'Heart rate weight for non-convulsive risk score'),
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
            lbl.setFont(QFont("SF Pro Text", 12, QFont.Bold))
            lbl.setStyleSheet("color: #cdd6f4;")
            top_row.addWidget(lbl)
            top_row.addStretch()
            val_lbl = QLabel(f"{current_val:.2f}")
            val_lbl.setStyleSheet("color: #89b4fa; font-size: 12px; font-weight: bold; min-width: 36px;")
            val_lbl.setAlignment(Qt.AlignRight)
            top_row.addWidget(val_lbl)
            row_layout.addLayout(top_row)

            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")
            row_layout.addWidget(desc_lbl)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(5, 80)   # maps to 0.05 – 0.80
            slider.setValue(int(current_val * 100))
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(f"{v/100:.2f}"))
            row_layout.addWidget(slider)

            self._weight_sliders[wkey] = slider
            sliders_layout.addWidget(row_widget)

        apply_btn = QPushButton("Save manual weights")
        apply_btn.setMinimumHeight(40)
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #cba6f7; color: #1e1e2e; border-radius: 8px;"
            "font-size: 13px; font-weight: bold; border: none; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #b4befe; }"
        )
        apply_btn.clicked.connect(self._apply_manual_weights)
        sliders_layout.addWidget(apply_btn)

        left_layout.addWidget(self._sliders_card)
        left_layout.addStretch()
        left_scroll.setWidget(left_inner)
        splitter.addWidget(left_scroll)

        # ── Right panel — chat ────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("background-color: #181825;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 24, 24, 24)
        right_layout.setSpacing(12)

        chat_title = QLabel("💬  Adaptive Calibration")
        chat_title.setFont(QFont("SF Pro Display", 15, QFont.Bold))
        right_layout.addWidget(chat_title)

        chat_hint = QLabel("Answer Gemini's questions to improve future detection accuracy.")
        chat_hint.setStyleSheet("color: #6c7086; font-size: 12px;")
        right_layout.addWidget(chat_hint)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_messages_widget = QWidget()
        self.chat_messages_widget.setStyleSheet("background: transparent;")
        self.chat_messages_layout = QVBoxLayout(self.chat_messages_widget)
        self.chat_messages_layout.setSpacing(10)
        self.chat_messages_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_messages_widget)
        right_layout.addWidget(self.chat_scroll, stretch=1)

        # input + send button side by side
        input_container = QWidget()
        input_container.setStyleSheet("background: transparent;")
        input_h = QHBoxLayout(input_container)
        input_h.setContentsMargins(0, 0, 0, 0)
        input_h.setSpacing(8)

        self.chat_input = _EnterTextEdit()
        self.chat_input.setPlaceholderText("Type your answer… (Enter to send, Shift+Enter for new line)")
        self.chat_input.setFixedHeight(60)
        self.chat_input.setStyleSheet(
            "background-color: #313244; border: 1px solid #45475a;"
            "border-radius: 8px; padding: 8px; font-size: 13px; color: #cdd6f4;"
        )
        self.chat_input.enter_pressed.connect(self._on_send)
        input_h.addWidget(self.chat_input, stretch=1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(90, 60)
        self.send_btn.setStyleSheet(
            "QPushButton { background-color: #89b4fa; color: #1e1e2e; border-radius: 8px;"
            "font-size: 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #b4befe; }"
            "QPushButton:disabled { background-color: #45475a; color: #6c7086; }"
        )
        self.send_btn.clicked.connect(self._on_send)
        input_h.addWidget(self.send_btn)
        right_layout.addWidget(input_container)

        self.save_btn = QPushButton("💾  Save Updated Weights")
        self.save_btn.setMinimumHeight(44)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e; border-radius: 8px;"
            "font-size: 13px; font-weight: bold; border: none; padding: 10px; }"
            "QPushButton:hover { background-color: #94e2d5; }"
            "QPushButton:disabled { background-color: #45475a; color: #6c7086; }"
        )
        self.save_btn.setVisible(False)
        self.save_btn.clicked.connect(self._on_save_weights)
        right_layout.addWidget(self.save_btn)

        splitter.addWidget(right)
        splitter.setSizes([560, 560])

    # ── Helpers ───────────────────────────────────────────────────────────

    def _start_new_session(self):
        import subprocess, sys, os
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
        subprocess.Popen([sys.executable, script])
        self.close()

    def _toggle_sliders(self):
        self._sliders_visible = not self._sliders_visible
        self._sliders_card.setVisible(self._sliders_visible)

    def _apply_manual_weights(self):
        new_weights = {k: round(s.value() / 100, 2) for k, s in self._weight_sliders.items()}
        self.current_weights.update(new_weights)
        if self.on_weights_saved:
            self.on_weights_saved(self.current_weights)
        # confirm in chat panel
        self._add_bubble("I've manually updated the detection weights.", "user")
        self._add_bubble(
            "✅ Manual weights saved! I'll use these as the baseline if you continue the conversation.",
            "ai"
        )
        self.chat_history.append({
            "role": "user",
            "content": f"The caregiver manually set these weights: {json.dumps(new_weights)}. "
                       "Acknowledge and ask if they'd like to continue refining through conversation."
        })

    def _make_card(self):
        card = QFrame()
        card.setObjectName("card")
        return card

    def _info_chip(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background: #313244; color: #a6adc8; border-radius: 8px;"
            "padding: 4px 12px; font-size: 12px;"
        )
        return lbl

    def _add_bubble(self, text, role):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        if role == "user":
            bubble = QLabel(text)
            bubble.setWordWrap(True)
            bubble.setFont(QFont("SF Pro Text", 13))
            bubble.setMaximumWidth(360)
            bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bubble.setStyleSheet(
                "background-color: #89b4fa; color: #1e1e2e;"
                "border-radius: 14px; border-bottom-right-radius: 2px;"
                "padding: 10px 14px;"
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
                    color: #cdd6f4;
                    font-family: -apple-system, 'SF Pro Text', 'Segoe UI', sans-serif;
                    font-size: 13px;
                    line-height: 1.65;
                    margin: 0; padding: 0;
                }}
                h1,h2,h3 {{ color: #89b4fa; margin: 8px 0 4px 0; font-size: 14px; }}
                strong {{ color: #cba6f7; }}
                em {{ color: #f5c2e7; }}
                ul,ol {{ padding-left: 18px; margin: 4px 0; }}
                li {{ margin-bottom: 2px; }}
                p {{ margin: 0 0 8px 0; }}
                code {{ background: #45475a; color: #a6e3a1; padding: 1px 5px;
                        border-radius: 4px; font-family: monospace; font-size: 12px; }}
                </style></head>
                <body>{html_content}</body></html>
            """)
            bubble.setReadOnly(True)
            bubble.setFrameShape(QTextBrowser.NoFrame)
            bubble.setMaximumWidth(420)
            bubble.setMinimumWidth(200)
            bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            bubble.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            bubble.setStyleSheet(
                "background-color: #313244; border-radius: 14px;"
                "border-bottom-left-radius: 2px; padding: 10px 14px;"
                "border: none;"
            )
            # size to content — recompute after layout settles
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
                "background-color: #313244; color: #6c7086;"
                "border-radius: 14px; border-bottom-left-radius: 2px;"
                "padding: 10px 16px; font-size: 13px; font-style: italic;"
            )
            self._thinking_bubble.setFixedWidth(120)
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
            # animate dots
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
                # only treat as a weight update if it contains known weight keys
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
                        "✅ Weight update ready — click 'Save Updated Weights' below to apply.",
                        text, flags=re.DOTALL
                    )
            except Exception:
                pass

        self._add_bubble(display_text, "ai")

    def _on_save_weights(self):
        if self.pending_weights and self.on_weights_saved:
            self.current_weights.update(self.pending_weights)
            self.on_weights_saved(self.current_weights)
            # update sliders to reflect new values
            for k, slider in self._weight_sliders.items():
                if k in self.current_weights:
                    slider.blockSignals(True)
                    slider.setValue(int(self.current_weights[k] * 100))
                    slider.blockSignals(False)
            self.save_btn.setText("✅  Weights saved!")
            self.save_btn.setEnabled(False)
            # let the conversation continue
            self.chat_history.append({
                "role": "user",
                "content": "The weights have been saved. Continue helping me calibrate if needed."
            })
            QTimer.singleShot(800, self._re_enable_save)

    def _re_enable_save(self):
        self.save_btn.setText("💾  Save Updated Weights")
        self.save_btn.setEnabled(True)
        self.save_btn.setVisible(False)
        self.pending_weights = None
