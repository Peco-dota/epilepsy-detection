"""
Live debug metrics window — floats alongside monitoring when debug overlay is on.
Updated by FaceDetection every frame via update_metrics().
"""
import cv2
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QProgressBar, QGridLayout, QPushButton,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QImage, QPixmap

from ui.theme import BG, CARD, TEXT, MUTED, ACCENT, BORDER, DANGER, SUCCESS, WARN

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT};
    font-family: 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif; }}
QLabel {{ background: transparent; color: {TEXT}; border: none; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 4px; border-radius: 2px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(177,173,161,0.5); border-radius: 2px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame#card {{ background: {CARD}; border-radius: 12px; border: 1px solid {BORDER}; }}
QProgressBar {{
    background: rgba(177,173,161,0.2); border-radius: 3px; border: none;
    max-height: 6px; min-height: 6px;
}}
QProgressBar::chunk {{ border-radius: 3px; }}
"""

def _risk_color(v: float) -> str:
    if v < 0.3:  return SUCCESS
    if v < 0.65: return WARN
    return DANGER


class _MetricRow(QWidget):
    """Label + progress bar + value for a single score."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._lbl = QLabel(label)
        self._lbl.setFont(QFont('', 11))
        self._lbl.setStyleSheet(f"color: {MUTED}; min-width: 90px;")
        row.addWidget(self._lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        row.addWidget(self._bar, stretch=1)

        self._val = QLabel("0.000")
        self._val.setFont(QFont('', 11, QFont.Bold))
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._val.setFixedWidth(42)
        row.addWidget(self._val)

    def set(self, value: float, fmt: str | None = None, risk_scale: bool = False):
        pct = min(int(value * 100), 100)
        self._bar.setValue(pct)
        if risk_scale:
            # Sharper scale for risk scores: yellow ≥0.5, red ≥0.8 (alert at 1.0)
            color = SUCCESS if value < 0.5 else (WARN if value < 0.8 else DANGER)
        else:
            color = _risk_color(value)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: rgba(177,173,161,0.2); border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        self._val.setText(fmt if fmt else f"{value:.3f}")
        self._val.setStyleSheet(f"color: {color}; font-weight: bold;")


class _Section(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        hdr = QWidget(); hdr.setStyleSheet("background: transparent;")
        hrow = QHBoxLayout(hdr); hrow.setContentsMargins(0,0,0,0); hrow.setSpacing(6)
        bar = QWidget(); bar.setFixedSize(3, 12)
        bar.setStyleSheet(f"background: {ACCENT}; border-radius: 1px;")
        hrow.addWidget(bar, alignment=Qt.AlignVCenter)
        ttl = QLabel(title.upper())
        ttl.setFont(QFont('', 9, QFont.Bold))
        ttl.setStyleSheet(f"color: {MUTED}; letter-spacing: 0.7px;")
        hrow.addWidget(ttl); hrow.addStretch()
        layout.addWidget(hdr)

        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        layout.addLayout(self._body)

    def body(self):
        return self._body


class DebugWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EpiGuard — Live Metrics")
        self.resize(340, 720)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setGeometry(0, 0, 340, 720)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)
        scroll.setWidget(inner)

        # ── Detection Scores ─────────────────────────────────────────────────
        det = _Section("Detection Scores")
        self._shake  = _MetricRow("Head shake")
        self._blink  = _MetricRow("Blinking")
        self._eye    = _MetricRow("Eye movement")
        self._freeze = _MetricRow("Face freeze")
        self._asym   = _MetricRow("Asymmetry")
        self._twitch = _MetricRow("Twitching")
        self._color  = _MetricRow("Face color")
        self._bpm    = _MetricRow("Heart rate")
        for w in (self._shake, self._blink, self._eye, self._freeze,
                  self._asym, self._twitch, self._color, self._bpm):
            det.body().addWidget(w)
        vbox.addWidget(det)

        # ── Risk ─────────────────────────────────────────────────────────────
        risk = _Section("Risk Scores")
        self._conv    = _MetricRow("Convulsive")
        self._nc      = _MetricRow("Non-conv")
        risk.body().addWidget(self._conv)
        risk.body().addWidget(self._nc)
        vbox.addWidget(risk)

        # ── Pre-ictal ────────────────────────────────────────────────────────
        pi_sec = _Section("Pre-ictal")
        self._pi_score = _MetricRow("Score")
        self._pi_stage = QLabel("Stage: —")
        self._pi_stage.setFont(QFont('', 11))
        self._pi_stage.setStyleSheet(f"color: {TEXT};")
        pi_sec.body().addWidget(self._pi_score)
        pi_sec.body().addWidget(self._pi_stage)
        vbox.addWidget(pi_sec)

        # ── Audio ────────────────────────────────────────────────────────────
        au_sec = _Section("Audio")
        self._au_score  = _MetricRow("Score")
        self._au_rms    = QLabel("RMS: —")
        self._au_groans = QLabel("Groans: —")
        for lbl in (self._au_rms, self._au_groans):
            lbl.setFont(QFont('', 11))
            lbl.setStyleSheet(f"color: {MUTED};")
        au_sec.body().addWidget(self._au_score)
        au_sec.body().addWidget(self._au_rms)
        au_sec.body().addWidget(self._au_groans)
        vbox.addWidget(au_sec)

        # ── Weights ──────────────────────────────────────────────────────────
        w_sec = _Section("Active Weights")
        self._weight_labels: dict[str, QLabel] = {}
        weight_names = {
            'w_shake': 'Head shake', 'w_blink': 'Blinking', 'w_twitch': 'Twitching',
            'w_asym': 'Asymmetry', 'w_freeze': 'Freeze', 'w_bpm': 'Heart rate',
            'w_color': 'Color', 'w_blink_nc': 'Blink NC', 'w_bpm_nc': 'BPM NC',
            'w_audio': 'Audio',
        }
        for key, name in weight_names.items():
            row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row_w); rl.setContentsMargins(0,0,0,0)
            nl = QLabel(name); nl.setFont(QFont('', 11))
            nl.setStyleSheet(f"color: {MUTED}; min-width: 90px;")
            vl = QLabel("—"); vl.setFont(QFont('', 11, QFont.Bold))
            vl.setAlignment(Qt.AlignRight); vl.setStyleSheet(f"color: {ACCENT};")
            rl.addWidget(nl); rl.addWidget(vl)
            w_sec.body().addWidget(row_w)
            self._weight_labels[key] = vl
        vbox.addWidget(w_sec)
        vbox.addStretch()

    def update_metrics(self, data: dict):
        """Call this from the detection loop with the current metric values."""
        self._shake.set(data.get('shake', 0))
        self._blink.set(data.get('blink', 0))
        self._eye.set(data.get('eye', 0))
        self._freeze.set(data.get('freeze', 0))
        self._asym.set(data.get('asym', 0))
        self._twitch.set(data.get('twitch', 0))
        self._color.set(data.get('color', 0))
        self._bpm.set(data.get('bpm', 0))

        self._conv.set(data.get('conv_risk', 0))
        self._nc.set(data.get('nc_risk', 0))

        pi_score = data.get('pi_score', 0)
        self._pi_score.set(pi_score)
        self._pi_stage.setText(f"Stage: {data.get('pi_stage', '—')}")
        self._pi_stage.setStyleSheet(
            f"color: {_risk_color(pi_score)}; font-weight: 600;"
        )

        audio_score = data.get('audio_score', 0)
        self._au_score.set(audio_score)
        self._au_rms.setText(f"RMS:    {data.get('audio_rms', 0.0):.4f}")
        self._au_groans.setText(f"Groans: {data.get('audio_groans', 0)}")

        for key, lbl in self._weight_labels.items():
            v = data.get('weights', {}).get(key)
            if v is not None:
                lbl.setText(f"{v:.2f}")


class MonitoringDashboard(QWidget):
    """
    Combined window: annotated detector camera feeds on the left,
    live metric bars on the right.
    """
    _GRID = [
        ('freeze',   'Face Freeze'),
        ('eye',      'Eye Tracking'),
        ('blink',    'Blinking'),
        ('twitch',   'Twitching'),
        ('shake',    'Head Shake'),
        ('drooping', 'Asymmetry'),
        ('health',   'Heart Rate'),
    ]
    _COLS = 3
    _TW, _TH = 260, 195   # thumbnail size per cell

    def __init__(self, patient_name="", on_stop=None, on_feedback=None, parent=None):
        super().__init__(parent)
        self._on_stop     = on_stop
        self._on_feedback = on_feedback
        self._spin_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spin_idx    = 0

        self.setWindowTitle("EpiGuard — Live Monitoring")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background: {CARD}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 10, 16, 10)
        hl.setSpacing(12)

        self._name_lbl = QLabel(f"Monitoring {patient_name}" if patient_name else "Monitoring")
        self._name_lbl.setFont(QFont('', 13, QFont.Bold))
        self._name_lbl.setStyleSheet(f"color: {TEXT}; background: transparent; border: none;")
        hl.addWidget(self._name_lbl)

        self._spinner_lbl = QLabel("⠋  Live")
        self._spinner_lbl.setFont(QFont('', 12))
        self._spinner_lbl.setStyleSheet(f"color: {ACCENT}; background: transparent; border: none;")
        hl.addWidget(self._spinner_lbl)
        hl.addStretch()

        self._stop_btn = QPushButton("Stop Monitoring")
        self._stop_btn.setFont(QFont('', 11, QFont.Bold))
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #fff; border-radius: 6px; padding: 0 14px; border: none; }}"
            f"QPushButton:hover {{ background: #ad5434; }}"
        )
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.clicked.connect(self._handle_stop)
        hl.addWidget(self._stop_btn)
        outer.addWidget(header)

        # ── Alert strip (hidden by default) ───────────────────────────────
        self._alert_strip = QWidget()
        self._alert_strip.setStyleSheet(
            "background: #fef2f2; border-bottom: 1px solid #fca5a5;"
        )
        al = QVBoxLayout(self._alert_strip)
        al.setContentsMargins(16, 8, 16, 8)
        al.setSpacing(4)

        row1 = QHBoxLayout(); row1.setSpacing(10)
        self._alert_title = QLabel("⚠  Seizure Risk Detected")
        self._alert_title.setFont(QFont('', 12, QFont.Bold))
        self._alert_title.setStyleSheet("color: #b91c1c; background: transparent; border: none;")
        self._alert_detail = QLabel("")
        self._alert_detail.setFont(QFont('', 11))
        self._alert_detail.setStyleSheet("color: #7f1d1d; background: transparent; border: none;")
        row1.addWidget(self._alert_title)
        row1.addWidget(self._alert_detail)
        row1.addStretch()
        al.addLayout(row1)

        self._alert_contrib = QLabel("")
        self._alert_contrib.setFont(QFont('', 10))
        self._alert_contrib.setStyleSheet("color: #991b1b; background: transparent; border: none;")
        al.addWidget(self._alert_contrib)

        self._alert_countdown = QLabel("")
        self._alert_countdown.setFont(QFont('', 10, QFont.Bold))
        self._alert_countdown.setStyleSheet("color: #b91c1c; background: transparent; border: none;")
        al.addWidget(self._alert_countdown)

        row2 = QHBoxLayout(); row2.setSpacing(8)
        self._yes_btn = QPushButton("✓  Real seizure")
        self._no_btn  = QPushButton("✗  False alarm")
        self._yes_btn.setFont(QFont('', 11, QFont.Bold))
        self._no_btn.setFont(QFont('', 11, QFont.Bold))
        self._yes_btn.setFixedHeight(30)
        self._no_btn.setFixedHeight(30)
        self._yes_btn.setStyleSheet(
            "QPushButton { background:#16a34a; color:white; border-radius:6px; padding:0 12px; border:none; }"
            "QPushButton:hover { background:#15803d; }"
        )
        self._no_btn.setStyleSheet(
            "QPushButton { background:#6b7280; color:white; border-radius:6px; padding:0 12px; border:none; }"
            "QPushButton:hover { background:#4b5563; }"
        )
        self._yes_btn.setCursor(Qt.PointingHandCursor)
        self._no_btn.setCursor(Qt.PointingHandCursor)
        self._yes_btn.clicked.connect(lambda: self._handle_feedback(True))
        self._no_btn.clicked.connect(lambda: self._handle_feedback(False))
        row2.addWidget(self._yes_btn); row2.addWidget(self._no_btn); row2.addStretch()
        al.addLayout(row2)

        self._alert_strip.hide()
        outer.addWidget(self._alert_strip)

        # ── Pre-ictal strip (hidden by default) ───────────────────────────
        self._pi_strip = QWidget()
        self._pi_strip.setStyleSheet(
            "background: #fffbeb; border-bottom: 1px solid #fcd34d;"
        )
        pl = QHBoxLayout(self._pi_strip)
        pl.setContentsMargins(16, 7, 16, 7)
        self._pi_lbl = QLabel("")
        self._pi_lbl.setFont(QFont('', 11, QFont.Bold))
        self._pi_lbl.setStyleSheet("color: #92400e; background: transparent; border: none;")
        pl.addWidget(self._pi_lbl)
        self._pi_strip.hide()
        outer.addWidget(self._pi_strip)

        # ── Body (camera + metrics) ───────────────────────────────────────
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addWidget(body)

        # spinner timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

        # ── Left: camera feed grid ────────────────────────────────────────
        feeds = QWidget()
        feeds.setStyleSheet(f"background: {BG};")
        cam_grid = QGridLayout(feeds)
        cam_grid.setSpacing(8)
        cam_grid.setContentsMargins(12, 12, 8, 12)

        self._cells: dict[str, QLabel] = {}
        for i, (key, title) in enumerate(self._GRID):
            row, col = divmod(i, self._COLS)
            cell = QFrame()
            cell.setObjectName('card')
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(4, 4, 4, 4)
            cl.setSpacing(3)

            t = QLabel(title.upper())
            t.setFont(QFont('', 8, QFont.Bold))
            t.setStyleSheet(f"color: {MUTED}; letter-spacing: 0.5px;")
            t.setAlignment(Qt.AlignCenter)

            img = QLabel()
            img.setFixedSize(self._TW, self._TH)
            img.setAlignment(Qt.AlignCenter)
            img.setStyleSheet("background: #111; border-radius: 4px; border: none;")

            cl.addWidget(t)
            cl.addWidget(img)
            cam_grid.addWidget(cell, row, col)
            self._cells[key] = img

        root.addWidget(feeds)

        # ── Divider ───────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet(f"color: {BORDER}; background: {BORDER};")
        div.setFixedWidth(1)
        root.addWidget(div)

        # ── Right: scrollable metrics ─────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(320)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)
        scroll.setWidget(inner)

        det = _Section("Detection Scores")
        self._shake  = _MetricRow("Head shake")
        self._blink  = _MetricRow("Blinking")
        self._eye    = _MetricRow("Eye movement")
        self._freeze = _MetricRow("Face freeze")
        self._asym   = _MetricRow("Asymmetry")
        self._twitch = _MetricRow("Twitching")
        self._color  = _MetricRow("Face color")
        self._bpm    = _MetricRow("Heart rate")
        for w in (self._shake, self._blink, self._eye, self._freeze,
                  self._asym, self._twitch, self._color, self._bpm):
            det.body().addWidget(w)
        vbox.addWidget(det)

        risk = _Section("Risk Scores  ·  alert fires at 1.0")
        self._conv = _MetricRow("Convulsive")
        self._nc   = _MetricRow("Non-conv")
        risk.body().addWidget(self._conv)
        risk.body().addWidget(self._nc)
        vbox.addWidget(risk)

        # ── Alert / SMS status ────────────────────────────────────────────
        alert_sec = _Section("Alert & SMS")
        self._alert_status = QLabel("No alert triggered")
        self._alert_status.setFont(QFont('', 11))
        self._alert_status.setStyleSheet(f"color: {MUTED};")
        self._sms_status = QLabel("SMS: —")
        self._sms_status.setFont(QFont('', 11))
        self._sms_status.setStyleSheet(f"color: {MUTED};")
        alert_sec.body().addWidget(self._alert_status)
        alert_sec.body().addWidget(self._sms_status)
        vbox.addWidget(alert_sec)

        pi_sec = _Section("Pre-ictal")
        self._pi_score = _MetricRow("Score")
        self._pi_stage = QLabel("Stage: —")
        self._pi_stage.setFont(QFont('', 11))
        self._pi_stage.setStyleSheet(f"color: {TEXT};")
        pi_sec.body().addWidget(self._pi_score)
        pi_sec.body().addWidget(self._pi_stage)
        vbox.addWidget(pi_sec)

        au_sec = _Section("Audio")
        self._au_score  = _MetricRow("Score")
        self._au_rms    = QLabel("RMS: —")
        self._au_groans = QLabel("Groans: —")
        for lbl in (self._au_rms, self._au_groans):
            lbl.setFont(QFont('', 11))
            lbl.setStyleSheet(f"color: {MUTED};")
        au_sec.body().addWidget(self._au_score)
        au_sec.body().addWidget(self._au_rms)
        au_sec.body().addWidget(self._au_groans)
        vbox.addWidget(au_sec)

        w_sec = _Section("Active Weights")
        self._weight_labels: dict[str, QLabel] = {}
        for key, name in {
            'w_shake': 'Head shake', 'w_blink': 'Blinking', 'w_twitch': 'Twitching',
            'w_asym': 'Asymmetry', 'w_freeze': 'Freeze', 'w_bpm': 'Heart rate',
            'w_color': 'Color', 'w_blink_nc': 'Blink NC', 'w_bpm_nc': 'BPM NC',
            'w_audio': 'Audio',
        }.items():
            rw = QWidget(); rw.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(rw); rl.setContentsMargins(0, 0, 0, 0)
            nl = QLabel(name); nl.setFont(QFont('', 11))
            nl.setStyleSheet(f"color: {MUTED}; min-width: 90px;")
            vl = QLabel("—"); vl.setFont(QFont('', 11, QFont.Bold))
            vl.setAlignment(Qt.AlignRight)
            vl.setStyleSheet(f"color: {ACCENT};")
            rl.addWidget(nl); rl.addWidget(vl)
            w_sec.body().addWidget(rw)
            self._weight_labels[key] = vl
        vbox.addWidget(w_sec)
        vbox.addStretch()

        root.addWidget(scroll)

    def update_metrics(self, data: dict):
        self._shake.set(data.get('shake', 0))
        self._blink.set(data.get('blink', 0))
        self._eye.set(data.get('eye', 0))
        self._freeze.set(data.get('freeze', 0))
        self._asym.set(data.get('asym', 0))
        self._twitch.set(data.get('twitch', 0))
        self._color.set(data.get('color', 0))
        self._bpm.set(data.get('bpm', 0))
        # Risk rows use a sharper scale: yellow ≥0.5, red ≥0.8 (alert fires at 1.0)
        self._conv.set(data.get('conv_risk', 0), risk_scale=True)
        self._nc.set(data.get('nc_risk', 0),     risk_scale=True)
        pi_score = data.get('pi_score', 0)
        self._pi_score.set(pi_score)
        self._pi_stage.setText(f"Stage: {data.get('pi_stage', '—')}")
        self._pi_stage.setStyleSheet(f"color: {_risk_color(pi_score)}; font-weight: 600;")
        self._au_score.set(data.get('audio_score', 0))
        self._au_rms.setText(f"RMS:    {data.get('audio_rms', 0.0):.4f}")
        self._au_groans.setText(f"Groans: {data.get('audio_groans', 0)}")

        for key, lbl in self._weight_labels.items():
            v = data.get('weights', {}).get(key)
            if v is not None:
                lbl.setText(f"{v:.2f}")

    def update_frames(self, frames: dict):
        for key, img_lbl in self._cells.items():
            frame = frames.get(key)
            if frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data.tobytes(), w, h, w * ch, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                self._TW, self._TH, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            img_lbl.setPixmap(pix)

    # ── Alert / pre-ictal public API (mirrors MonitoringStatusWindow) ─────

    def show_alert(self, alert_type: str, sms_sent: bool,
                   contributors: list | None = None):
        self._alert_detail.setText(
            f"{alert_type.title()} · {'SMS sent ✓' if sms_sent else 'Waiting for response...'}"
        )
        if contributors:
            self._alert_contrib.setText(
                "  ·  ".join(f"{lbl} {pct}%" for lbl, pct in contributors)
            )
            self._alert_contrib.show()
        else:
            self._alert_contrib.hide()
        self._alert_countdown.setText("")
        self._alert_strip.show()

    def update_countdown(self, secs: int):
        if not self._alert_strip.isVisible():
            return
        if secs == 0:
            self._alert_detail.setText(
                self._alert_detail.text().split(" · ")[0] + " · SMS sent automatically ✓"
            )
            self._alert_countdown.setText("")
        else:
            self._alert_countdown.setText(f"SMS sends automatically in {secs}s if no response")

    def show_pre_ictal_warning(self, stage_label: str):
        self._pi_lbl.setText(f"⚠  Pre-ictal warning · {stage_label}")
        self._pi_strip.show()

    def clear_pre_ictal_warning(self):
        self._pi_strip.hide()

    # ── Private ───────────────────────────────────────────────────────────

    def _tick(self):
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_frames)
        self._spinner_lbl.setText(f"{self._spin_frames[self._spin_idx]}  Live")

    def _handle_stop(self):
        self._stop_btn.setText("Stopping…")
        self._stop_btn.setEnabled(False)
        if self._on_stop:
            self._on_stop()

    def _handle_feedback(self, correct: bool):
        self._alert_strip.hide()
        if self._on_feedback:
            self._on_feedback(correct)


class DetectorViewsWindow(QWidget):
    """
    Shows each detector's annotated camera frame in a 3-column grid,
    mirroring the OpenCV mosaic from debug mode.
    """

    _GRID = [
        ('freeze',   'Face Freeze'),
        ('eye',      'Eye Tracking'),
        ('blink',    'Blinking'),
        ('twitch',   'Twitching'),
        ('shake',    'Head Shake'),
        ('drooping', 'Asymmetry'),
        ('health',   'Heart Rate'),
    ]
    _COLS = 3
    _THUMB_W, _THUMB_H = 213, 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EpiGuard — Detector Views")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background: {BG};")

        grid = QGridLayout(self)
        grid.setSpacing(8)
        grid.setContentsMargins(10, 10, 10, 10)

        self._cells: dict[str, QLabel] = {}
        for i, (key, title) in enumerate(self._GRID):
            row, col = divmod(i, self._COLS)

            cell = QWidget()
            cell.setStyleSheet(
                f"background: {CARD}; border-radius: 8px; border: 1px solid {BORDER};"
            )
            vl = QVBoxLayout(cell)
            vl.setContentsMargins(4, 4, 4, 4)
            vl.setSpacing(3)

            title_lbl = QLabel(title.upper())
            title_lbl.setFont(QFont('', 8, QFont.Bold))
            title_lbl.setStyleSheet(
                f"color: {MUTED}; letter-spacing: 0.5px; background: transparent; border: none;"
            )
            title_lbl.setAlignment(Qt.AlignCenter)

            img_lbl = QLabel()
            img_lbl.setFixedSize(self._THUMB_W, self._THUMB_H)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("background: #111; border-radius: 4px; border: none;")

            vl.addWidget(title_lbl)
            vl.addWidget(img_lbl)
            grid.addWidget(cell, row, col)
            self._cells[key] = img_lbl

        self.adjustSize()

    def update_frames(self, frames: dict):
        for key, img_lbl in self._cells.items():
            frame = frames.get(key)
            if frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data.tobytes(), w, h, w * ch, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                self._THUMB_W, self._THUMB_H,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            img_lbl.setPixmap(pix)
