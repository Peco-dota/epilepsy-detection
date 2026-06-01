"""
Small blocking dialog shown before audio monitoring starts.
Records ambient noise for ~5 seconds and sets adaptive thresholds.
"""
import threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from ui.theme import BG, CARD, TEXT, MUTED, ACCENT, ACCENT2, BORDER

_DURATION = 5  # calibration seconds

STYLE = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT};
    font-family: 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QProgressBar {{
    background: rgba(177,173,161,0.2); border-radius: 5px;
    border: none; max-height: 8px; min-height: 8px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QPushButton {{
    background: transparent; color: {MUTED};
    border: 1px solid {BORDER}; border-radius: 8px;
    font-size: 12px; padding: 6px 18px;
}}
QPushButton:hover {{ color: {TEXT}; border-color: rgba(177,173,161,0.7); }}
"""


class AudioCalibrationWindow(QMainWindow):
    def __init__(self, audio_monitor):
        super().__init__()
        self._monitor = audio_monitor
        self._done    = False
        self._elapsed = 0.0

        self.setWindowTitle("EpiGuard — Microphone Setup")
        self.setFixedSize(420, 260)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setStyleSheet(STYLE)

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 420) // 2, (screen.height() - 260) // 2)

        self._build()
        self._start_calibration()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(40, 36, 40, 32)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        # Accent stripe at top
        stripe = QWidget(); stripe.setFixedHeight(3)
        stripe.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT},stop:1 {ACCENT2});"
        )
        # Can't add to VBox after setCentralWidget — use absolute pos trick:
        stripe.setParent(root)
        stripe.setGeometry(0, 0, 420, 3)

        icon = QLabel("🎤")
        icon.setFont(QFont('', 38))
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        layout.addSpacing(12)

        title = QLabel("Microphone Calibration")
        title.setFont(QFont('', 17, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(6)

        self._sub = QLabel("Please stay quiet for a few seconds…")
        self._sub.setFont(QFont('', 12))
        self._sub.setAlignment(Qt.AlignCenter)
        self._sub.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self._sub)
        layout.addSpacing(24)

        self._bar = QProgressBar()
        self._bar.setRange(0, _DURATION * 10)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)
        layout.addSpacing(6)

        self._timer_lbl = QLabel(f"{_DURATION}s remaining")
        self._timer_lbl.setFont(QFont('', 11))
        self._timer_lbl.setAlignment(Qt.AlignCenter)
        self._timer_lbl.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self._timer_lbl)
        layout.addSpacing(20)

        self._skip_btn = QPushButton("Skip calibration")
        self._skip_btn.setFocusPolicy(Qt.NoFocus)
        self._skip_btn.setCursor(Qt.PointingHandCursor)
        self._skip_btn.clicked.connect(self._skip)
        layout.addWidget(self._skip_btn, alignment=Qt.AlignCenter)

    def _start_calibration(self):
        # Update progress bar every 100 ms
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(100)

        # Run calibration in a background thread so the UI stays responsive
        def _run():
            self._monitor.calibrate(
                duration=_DURATION,
                on_progress=None,  # we track elapsed via our own timer
            )
            self._done = True

        self._cal_thread = threading.Thread(target=_run, daemon=True)
        self._cal_thread.start()

    def _tick(self):
        self._elapsed += 0.1
        ticks = min(int(self._elapsed * 10), _DURATION * 10)
        self._bar.setValue(ticks)
        remaining = max(0, _DURATION - int(self._elapsed))
        self._timer_lbl.setText(f"{remaining}s remaining" if remaining else "Done!")

        if self._done or self._elapsed >= _DURATION + 0.5:
            self._tick_timer.stop()
            self._finish()

    def _skip(self):
        self._tick_timer.stop()
        self._finish()

    def _finish(self):
        self._sub.setText("✓  Calibration complete — starting monitoring")
        self._skip_btn.hide()
        QTimer.singleShot(600, self.close)


def run_audio_calibration(audio_monitor) -> dict:
    """
    Show the calibration window and block until it closes.
    Returns the calibration stats dict from audio_monitor.calibration.
    """
    app = QApplication.instance() or QApplication([])
    win = AudioCalibrationWindow(audio_monitor)
    win.show()
    app.exec()
    return audio_monitor.calibration
