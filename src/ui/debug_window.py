"""
Live debug metrics window — floats alongside monitoring when debug overlay is on.
Updated by FaceDetection every frame via update_metrics().
"""
import cv2
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QProgressBar, QGridLayout,
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

    def set(self, value: float, fmt: str | None = None):
        pct = min(int(value * 100), 100)
        self._bar.setValue(pct)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EpiGuard — Live Monitoring")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

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
        self._conv.set(data.get('conv_risk', 0))
        self._nc.set(data.get('nc_risk', 0))
        pi_score = data.get('pi_score', 0)
        self._pi_score.set(pi_score)
        self._pi_stage.setText(f"Stage: {data.get('pi_stage', '—')}")
        self._pi_stage.setStyleSheet(f"color: {_risk_color(pi_score)}; font-weight: 600;")
        self._au_score.set(data.get('audio_score', 0))
        self._au_rms.setText(f"RMS:    {data.get('audio_rms', 0.0):.4f}")
        self._au_groans.setText(f"Groans: {data.get('audio_groans', 0)}")

        # Alert & SMS
        alert_type    = data.get('alert_type')
        alert_pending = data.get('alert_pending', False)
        sms_sent      = data.get('sms_sent', False)
        sms_configured = data.get('sms_configured', False)

        if alert_pending and alert_type:
            self._alert_status.setText(f"⚠  {alert_type.title()} alert active — awaiting feedback")
            self._alert_status.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
        elif alert_type:
            self._alert_status.setText(f"✓  {alert_type.title()} alert — feedback received")
            self._alert_status.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
        else:
            self._alert_status.setText("No alert triggered")
            self._alert_status.setStyleSheet(f"color: {MUTED};")

        if not sms_configured:
            self._sms_status.setText("SMS: not configured")
            self._sms_status.setStyleSheet(f"color: {MUTED};")
        elif sms_sent:
            self._sms_status.setText("SMS: sent ✓")
            self._sms_status.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
        else:
            self._sms_status.setText("SMS: configured — not yet sent")
            self._sms_status.setStyleSheet(f"color: {MUTED};")

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
