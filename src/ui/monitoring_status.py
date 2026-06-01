from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

class MonitoringStatusWindow(QWidget):
    def __init__(self, patient_name="", on_stop=None):
        super().__init__()
        self.on_stop = on_stop
        self.setWindowTitle("EpiGuard Status")
        self.setFixedSize(260, 140)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("background-color: #f4f3ee; border: 2px solid rgba(193,95,60,0.5); border-radius: 12px;")
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(f"Monitoring {patient_name}...")
        self.label.setFont(QFont('', 14, QFont.Bold))
        self.label.setStyleSheet("color: #1c1917; border: none; background: transparent;")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        
        self.spinner_label = QLabel("⠋ Live")
        self.spinner_label.setFont(QFont('', 15))
        self.spinner_label.setStyleSheet("color: #c15f3c; border: none; background: transparent;")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner_label)
        
        self.stop_btn = QPushButton("Stop Monitoring")
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #c15f3c; color: white; border: none; border-radius: 6px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #ad5434; }
        """)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self._stop_clicked)
        layout.addWidget(self.stop_btn)
        
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.idx = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_spinner)
        self.timer.start(100)
        
    def _update_spinner(self):
        self.idx = (self.idx + 1) % len(self.frames)
        self.spinner_label.setText(f"{self.frames[self.idx]} Live")

    def _stop_clicked(self):
        self.stop_btn.setText("Stopping...")
        self.stop_btn.setEnabled(False)
        if self.on_stop:
            self.on_stop()
