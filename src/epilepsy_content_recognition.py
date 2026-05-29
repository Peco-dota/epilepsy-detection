import cv2
import numpy as np
from collections import deque
import time
import mss
import threading
import subprocess
import os
import sys
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import Quartz
from Quartz import CGWindowListCopyWindowInfo, CGWindowListCreateImage, CGRectNull
from Quartz import kCGWindowListOptionOnScreenOnly, kCGWindowListExcludeDesktopElements
from Quartz import kCGNullWindowID, kCGWindowImageDefault
import objc
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps


class EpilepsyContentDetector:
    def __init__(self, fps=30, flash_hz_limit=2.0, luminance_threshold=0.015, red_threshold=0.02, blue_threshold=0.02, flash_area_threshold=0.1, exposure_window_seconds=5):
        self.fps = fps
        self.flash_hz_limit = flash_hz_limit
        self.luminance_threshold = luminance_threshold
        self.red_threshold = red_threshold
        self.blue_threshold = blue_threshold
        self.flash_area_threshold = flash_area_threshold
        self.luminance_history = deque(maxlen=fps * 2)
        self.red_history = deque(maxlen=fps * 2)
        self.blue_history = deque(maxlen=fps * 2)
        self.timestamps = deque(maxlen=fps * 2)
        self.area_history = deque(maxlen=fps * 2)
        self.prev_gray = None
        self.transition_cooldown_until = 0.0
        self.cooldown_seconds = max(1.0, exposure_window_seconds * 0.2)
        self.min_flash_hz = 2.0
        self.max_flash_hz = 60.0
        self.min_contrast_delta = 0.1
        self.min_flash_area_ratio = flash_area_threshold
        self.min_red_flash_ratio = 0.05
        
    def calculate_luminance(self, frame):
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        return np.mean(gray) / 255.0
    
    def calculate_color_ratio(self, frame, ranges):
        if len(frame.shape) != 3:
            return 0.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            mask |= cv2.inRange(hsv, lower, upper)
        total_pixels = frame.shape[0] * frame.shape[1]
        if total_pixels == 0:
            return 0.0
        return float(np.sum(mask > 0)) / total_pixels
    
    def calculate_red_flash(self, frame):
        ranges = [
            (np.array([0, 140, 120]), np.array([10, 255, 255])),
            (np.array([160, 140, 120]), np.array([180, 255, 255])),
        ]
        return self.calculate_color_ratio(frame, ranges)
    
    def calculate_blue_flash(self, frame):
        ranges = [
            (np.array([90, 100, 120]), np.array([130, 255, 255])),
        ]
        return self.calculate_color_ratio(frame, ranges)
    
    def calculate_flash_mask(self, frame, threshold):
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        if self.prev_gray is None:
            self.prev_gray = gray
            return 0.0, None
        diff = cv2.absdiff(gray, self.prev_gray).astype(np.float32) / 255.0
        self.prev_gray = gray
        mask = diff > threshold
        area_ratio = float(np.sum(mask)) / mask.size
        box = None
        if area_ratio > 0.0:
            ys, xs = np.where(mask)
            if ys.size and xs.size:
                h, w = mask.shape
                x0 = float(np.min(xs)) / w
                x1 = float(np.max(xs) + 1) / w
                y0 = float(np.min(ys)) / h
                y1 = float(np.max(ys) + 1) / h
                box = (x0, y0, x1, y1)
        return area_ratio, box
    
    def count_flash_transitions(self, values, threshold):
        if len(values) < 3:
            return 0
        mean_val = np.mean(values)
        high_threshold = mean_val + threshold
        low_threshold = mean_val - threshold
        state = 'neutral'
        full_cycles = 0
        for val in values:
            if state == 'neutral':
                if val > high_threshold:
                    state = 'high'
                elif val < low_threshold:
                    state = 'low'
            elif state == 'high':
                if val < low_threshold:
                    state = 'low'
                    full_cycles += 1
            elif state == 'low':
                if val > high_threshold:
                    state = 'high'
                    full_cycles += 1
        return full_cycles
    
    def detect_scene_cut(self, values, threshold):
        if len(values) < 8:
            return False
        diffs = np.abs(np.diff(values))
        max_idx = int(np.argmax(diffs))
        max_diff = diffs[max_idx]
        if max_diff < threshold:
            return False
        pre = values[:max_idx + 1]
        post = values[max_idx + 1:]
        if len(pre) < 2 or len(post) < 2:
            return False
        pre_std = np.std(pre)
        post_std = np.std(post)
        post_diffs = np.abs(np.diff(post)) if len(post) > 1 else np.array([0.0])
        calm_after = np.mean(post_diffs) < threshold * 0.5
        return pre_std < threshold and post_std < threshold and calm_after
    
    def compute_flash_rate(self, transitions, time_window):
        if time_window <= 0:
            return 0.0
        return float(transitions) / time_window / 2.0
    
    def is_harding_flash(self, flash_rate, luminance_delta, area_ratio):
        if area_ratio < 1e-6:
            return False
        return (
            flash_rate >= self.min_flash_hz and
            flash_rate <= self.max_flash_hz and
            luminance_delta >= self.min_contrast_delta and
            area_ratio >= self.min_flash_area_ratio
        )
    
    def is_harding_red_flash(self, flash_rate, red_range, area_ratio):
        if area_ratio < 1e-6:
            return False
        return (
            flash_rate >= self.min_flash_hz and
            flash_rate <= self.max_flash_hz and
            red_range >= self.min_red_flash_ratio and
            area_ratio >= self.min_flash_area_ratio
        )
    
    def is_rapid_change(self, luminance_list):
        if len(luminance_list) < 10:
            return False
        diffs = np.abs(np.diff(luminance_list))
        large_changes = np.sum(diffs > 0.05)
        return large_changes >= 5
    
    def detect_transition_event(self, flash_transitions, luminance_range, max_spike, area_ratio):
        return (
            flash_transitions <= 1 and
            max_spike > 0.35 and
            area_ratio > 0.25 and
            luminance_range > 0.25
        )
    
    def analyze_frame(self, frame):
        current_time = time.time()
        current_luminance = self.calculate_luminance(frame)
        current_red = self.calculate_red_flash(frame)
        current_blue = self.calculate_blue_flash(frame)
        flash_area, flash_box = self.calculate_flash_mask(frame, self.luminance_threshold * 4)
        self.luminance_history.append(current_luminance)
        self.red_history.append(current_red)
        self.blue_history.append(current_blue)
        self.timestamps.append(current_time)
        self.area_history.append(flash_area)
        
        result = {
            'is_dangerous': False,
            'risk_level': 0.0,
            'flash_rate': 0.0,
            'red_flash_detected': False,
            'pattern_detected': False,
            'warnings': [],
            'luminance': current_luminance,
            'red_ratio': current_red,
            'flash_area': flash_area,
            'blue_ratio': current_blue,
            'max_luminance_delta': 0.0,
            'red_spike_rate': 0.0,
            'blue_spike_rate': 0.0,
            'risk_box': None,
        }
        
        if len(self.luminance_history) < self.fps // 2:
            return result
        
        time_window = self.timestamps[-1] - self.timestamps[0]
        if time_window < 0.3:
            return result
        
        luminance_list = list(self.luminance_history)
        flash_transitions = self.count_flash_transitions(luminance_list, self.luminance_threshold)
        flash_rate = self.compute_flash_rate(flash_transitions, time_window)
        result['flash_rate'] = flash_rate
        
        diffs = np.abs(np.diff(luminance_list))
        max_spike = float(np.max(diffs)) if len(diffs) else 0.0
        result['max_luminance_delta'] = max_spike
        luminance_range = np.max(luminance_list) - np.min(luminance_list)
        recent_area = max(self.area_history) if self.area_history else flash_area
        
        violations = []
        if self.is_harding_flash(flash_rate, max_spike, recent_area):
            violations.append(f"Harding flash {flash_rate:.1f} Hz")
        
        red_list = list(self.red_history)
        red_range = np.max(red_list) - np.min(red_list) if len(red_list) > 0 else 0.0
        if self.is_harding_red_flash(flash_rate, red_range, recent_area):
            result['red_flash_detected'] = True
            result['red_spike_rate'] = flash_rate
            violations.append("Harding red flash")
        
        if self.is_rapid_change(luminance_list):
            violations.append("Rapid luminance change")
        
        result['warnings'] = violations
        result['risk_level'] = min(1.0, 0.8 * len(violations))
        result['is_dangerous'] = bool(violations)
        if violations:
            result['risk_box'] = flash_box
        
        return result
    
    def reset(self):
        self.luminance_history.clear()
        self.red_history.clear()
        self.blue_history.clear()
        self.timestamps.clear()
        self.area_history.clear()
        self.prev_gray = None
        self.transition_cooldown_until = 0.0

NOTIF_STYLE = """
QDialog {
    background-color: #1a1a2e;
}
QLabel { color: white; }
QPushButton {
    background-color: #4ecdc4;
    color: #1a1a2e;
    border-radius: 8px;
    padding: 8px 24px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover { background-color: #94e2d5; }
"""


class EpilepsyProtector:
    def __init__(self, app, fps=30):
        self.app = app
        self.fps = fps
        screen = app.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()
        self.lock = threading.Lock()
        self.visible = False
        self.blocked_apps = set()
        self.notification_dialog = None

    def get_frontmost_app(self):
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        for win in window_list:
            owner = win.get('kCGWindowOwnerName', '')
            layer = win.get('kCGWindowLayer', 0)
            if owner and owner not in ['Python', 'python', 'Finder', 'Dock',
                                        'SystemUIServer', 'Control Center', 'Notification Center']:
                if layer == 0:
                    return {
                        'name': owner,
                        'window_name': win.get('kCGWindowName', ''),
                        'pid': win.get('kCGWindowOwnerPID'),
                        'bounds': win.get('kCGWindowBounds', {})
                    }
        return None

    def hide_app(self, app_info):
        if not app_info:
            return False
        try:
            script = f'tell application "System Events" to set visible of process "{app_info["name"]}" to false'
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            self.blocked_apps.add(app_info['name'])
            return True
        except Exception:
            return False

    def show_notification(self, app_info, warnings):
        if self.notification_dialog:
            self.notification_dialog.close()

        dlg = QDialog()
        dlg.setWindowTitle("Epilepsy Protection")
        dlg.setStyleSheet(NOTIF_STYLE)
        dlg.setFixedSize(480, 240)
        dlg.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)

        t = QLabel("⚠️  EPILEPSY PROTECTION")
        t.setFont(QFont("SF Pro Display", 18, QFont.Bold))
        t.setStyleSheet("color: #ff6b6b;")
        t.setAlignment(Qt.AlignCenter)
        layout.addWidget(t)

        app_name = app_info['name'] if app_info else 'Unknown application'
        hidden_lbl = QLabel(f"Application hidden:  {app_name}")
        hidden_lbl.setFont(QFont("SF Pro Text", 13))
        hidden_lbl.setStyleSheet("color: #4ecdc4;")
        hidden_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(hidden_lbl)

        reason_lbl = QLabel(f"Reason: {', '.join(warnings)}")
        reason_lbl.setFont(QFont("SF Pro Text", 12))
        reason_lbl.setStyleSheet("color: #feca57;")
        reason_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(reason_lbl)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.close)
        layout.addWidget(ok_btn, alignment=Qt.AlignCenter)

        # centre on screen
        dlg.move((self.screen_width - dlg.width()) // 2,
                  (self.screen_height - dlg.height()) // 2)

        self.notification_dialog = dlg
        QTimer.singleShot(10000, dlg.close)
        dlg.show()

    def update(self, is_dangerous, warnings=None):
        with self.lock:
            if is_dangerous and not self.visible:
                app_info = self.get_frontmost_app()
                if app_info and app_info['name'] not in self.blocked_apps:
                    if self.hide_app(app_info):
                        self.show_notification(app_info, warnings or ['Dangerous flashing'])
                        self.visible = True
            elif not is_dangerous:
                self.visible = False
                self.blocked_apps.clear()

    def destroy(self):
        if self.notification_dialog:
            self.notification_dialog.close()


class ScreenMonitor:
    def __init__(self, fps=30, monitor_number=0, verbose=False):
        self.fps = fps
        self.monitor_number = monitor_number
        self.verbose = verbose
        self.detector = EpilepsyContentDetector(fps=fps)
        self.app = QApplication.instance() or QApplication(sys.argv)
        try:
            from AppKit import NSApp, NSApplicationActivationPolicyAccessory
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass
        self.protector = EpilepsyProtector(self.app, fps=fps)
        self.is_running = True
        self.monitor_rect = None

    def capture_screen_quartz(self):
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID
        )
        
        overlay_id = self.protector.get_window_id()
        window_ids = []
        for win in window_list:
            win_id = win.get('kCGWindowNumber')
            owner = win.get('kCGWindowOwnerName', '')
            if win_id != overlay_id and owner not in ['Python', 'python', 'Cursor']:
                window_ids.append(win_id)
        
        if not window_ids:
            return self.capture_screen_mss()
        
        image = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
            kCGWindowImageDefault
        )
        
        if image is None:
            return self.capture_screen_mss()
        
        width = Quartz.CGImageGetWidth(image)
        height = Quartz.CGImageGetHeight(image)
        bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
        
        pixel_data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
        
        frame = np.frombuffer(pixel_data, dtype=np.uint8)
        frame = frame.reshape((height, bytes_per_row // 4, 4))
        frame = frame[:, :width, :]
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        frame_small = cv2.resize(frame, (320, 180))
        return frame_small
    
    def capture_screen_mss(self):
        with mss.mss() as sct:
            monitors = sct.monitors
            if self.monitor_number < len(monitors):
                monitor = monitors[self.monitor_number]
            else:
                monitor = monitors[0]
            self.monitor_rect = monitor
            screenshot = sct.grab(monitor)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            frame_small = cv2.resize(frame, (320, 180))
            return frame_small
    
    def capture_screen(self):
        try:
            return self.capture_screen_quartz()
        except Exception as e:
            print(f"Quartz capture failed: {e}, falling back to mss")
            return self.capture_screen_mss()

    def monitor_loop(self):
        interval = 1.0 / self.fps
        while self.is_running:
            start_time = time.time()
            try:
                frame = self.capture_screen()
                result = self.detector.analyze_frame(frame)
                is_danger = result['is_dangerous']
                warnings = result['warnings']
                
                if self.verbose:
                    print(f"DANGER: {is_danger} | flash_rate: {result['flash_rate']:.2f} Hz | warnings: {warnings}")
                
                self.protector.update(is_danger, warnings)
                        
            except Exception as e:
                if self.verbose:
                    print(f"Error: {e}")
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    def run(self):
        print("🛡️ Epilepsy protection running in background...")
        print("   Press Ctrl+C to stop")
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        try:
            self.app.exec()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            self.is_running = False
            self.protector.destroy()


def main():
    import sys
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    monitor = ScreenMonitor(fps=30, monitor_number=0, verbose=verbose)
    monitor.run()


if __name__ == "__main__":
    main()
