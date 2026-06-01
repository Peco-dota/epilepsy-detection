import cv2
import mediapipe as mp
import numpy as np
import subprocess
import sys
import os
import json
import time
from PySide6.QtWidgets import QApplication
import threading
import select

from detectors.face_freeze import FaceFreeze
from detectors.eye_tracking import EyeTracking
from detectors.check_blink_eye import BlinkDetector
from detectors.twitch_detector import TwitchDetector
from detectors.shake_detection import SeizureDetector
from detectors.face_drooping import FaceMeshViewer
from core.health_monitor_module import HealthMonitor
from utils.csv_logger import CSVLogger
from services.gpt_client import AIClient
from ui.summary_window import SummaryWindow
from detectors.pre_ictal_detector import PreIctalDetector

WEIGHTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'config', 'weights.json')

DEFAULT_WEIGHTS = {
    'w_bpm':      0.10,
    'w_color':    0.10,
    'w_shake':    0.30,
    'w_twitch':   0.35,
    'w_blink':    0.30,
    'w_freeze':   0.40,
    'w_asym':     0.55,
    'w_blink_nc': 0.30,
    'w_bpm_nc':   0.10,
    'w_audio':    0.25,
}

WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.80
LEARN_RATE_UP   = 1.15  # multiply on correct alert
LEARN_RATE_DOWN = 0.85  # multiply on false positive


def load_weights():
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, 'r') as f:
                saved = json.load(f)
            weights = DEFAULT_WEIGHTS.copy()
            weights.update({k: v for k, v in saved.items() if k in weights})
            return weights
        except Exception:
            pass
    return DEFAULT_WEIGHTS.copy()


def save_weights(weights):
    try:
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(weights, f, indent=2)
    except Exception as e:
        print(f"Could not save weights: {e}")

class FaceDetection:
    def __init__(self, debug=False, solo_video=True, ai_client=None, sms_client=None,
                 patient_id=None, debug_overlay=False, screen_protection=True):
        self.frame_index = 0
        self.frame_reset = 150
        self.debug = debug
        self.solo_video = solo_video
        self.debug_overlay = debug_overlay
        self.screen_protection = screen_protection
        self.black_frame = None
        self.epilepsy_process = None
        self.ai_client = ai_client
        self.sms_client = sms_client
        self.patient_id = patient_id
        
        self.cap = self._open_builtin_camera()
        if not self.cap.isOpened():
            raise RuntimeError("Could not open built-in webcam. Check that it is not in use by another app.")

        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.face_freeze_modul = None
        self.eye_tracking_module = None
        self.blinker_module = None
        self.twitch_detector_module = None
        self.face_drooping_model = None
        self.health_monitor_module = None
        self.shake_detection_module = None
        
        self.csv_logger = CSVLogger(output_dir="logs", log_interval=1.0)
        self.should_quit = False
        self.keyboard_thread = None

        self.bpm = 0.0
        self.twitch = 0.0
        self.blink = 0.0
        self.color = 0.0
        self.freeze = 0.0
        self.asym = 0.0
        self.eye = 0.0
        self.shake = 0.0
        self.sms_sent = False

        if patient_id:
            from core import account_store as _as
            self.weights = _as.get_weights(patient_id)
        else:
            self.weights = load_weights()
        print(f"📊 Loaded weights: {self.weights}")

        self.pre_ictal = PreIctalDetector()
        self.context_multipliers = {}  # set externally from menu result

        # feedback state
        self.pending_feedback = False
        self.alert_scores_snapshot = {}
        self.feedback_events = []

        # session meta
        self.patient_name = ''
        self._session_start = time.time()
        self._review_requested = False   # set by global hotkey thread
        self._auto_review_shown = False

        self._setup_global_hotkey()

    def _open_builtin_camera(self):
        # Try to find the built-in FaceTime/webcam by name, skipping iPhone Continuity Camera
        preferred_keywords = ['facetime', 'built-in', 'integrated', 'internal']
        skip_keywords = ['iphone', 'ipad', 'continuity', 'droid']

        for index in range(6):
            if sys.platform == "darwin":
                cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
            else:
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) # for Windows
            if not cap.isOpened():
                continue
            # cv2 doesn't expose camera name directly on macOS, so use AVFoundation via subprocess
            try:
                import subprocess
                result = subprocess.run(
                    ['system_profiler', 'SPCameraDataType'],
                    capture_output=True, text=True, timeout=3
                )
                lines = result.stdout.lower().split('\n')
                # find camera names in order
                camera_names = [l.strip().rstrip(':') for l in lines if l.strip().endswith(':') and 'camera' in l.lower()]
                name = camera_names[index] if index < len(camera_names) else ''
                if any(k in name for k in skip_keywords):
                    cap.release()
                    continue
                if any(k in name for k in preferred_keywords) or name == '':
                    print(f"Using camera index {index}: '{name or 'unknown'}'")
                    return cap
            except Exception:
                # can't determine name — just use first available
                print(f"Using camera index {index}")
                return cap
            cap.release()

        # fallback: just use index 0
        if sys.platform == "darwin":
            return cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(0, cv2.CAP_DSHOW)

    def _setup_global_hotkey(self):
        try:
            from pynput import keyboard as _kb
            def _on_hotkey():
                self._review_requested = True
            listener = _kb.GlobalHotKeys({'<cmd>+<shift>+r': _on_hotkey})
            listener.start()
            self._hotkey_listener = listener
            print("⌨️  Global hotkey: Cmd+Shift+R → open review mid-session")
        except Exception as e:
            print(f"⚠️  Global hotkey unavailable: {e}")
            print("   Grant Accessibility permissions in System Preferences → Security & Privacy if needed")

    def _show_interim_review(self):
        print("\n📊 Opening mid-session review (monitoring paused)...")
        self.csv_logger.file.flush()
        summary_text = self.csv_logger.get_summary_for_llm()

        ai_analysis = None
        if self.ai_client:
            print("🤖 Generating interim analysis...")
            ai_analysis = self.ai_client.analyze_session(summary_text)

        from ui.summary_window import SummaryWindow
        sw = SummaryWindow()
        sw.show_summary(
            summary_text=summary_text,
            ai_analysis=ai_analysis or '⏱ Interim session — full analysis available when you end monitoring.',
            filepath=self.csv_logger.get_filepath(),
            ai_client=self.ai_client,
            current_weights=self.weights,
            on_weights_saved=self._on_weights_saved,
            is_interim=True,
        )
        print("📊 Monitoring resumed.")

    def apply_context_multipliers(self, multipliers):
        """
        Scale pre-ictal detection thresholds by context multipliers.
        A multiplier > 1.0 means the signal triggers more easily (lower threshold).
        e.g. sleep-deprived patient → multiply=1.4 → threshold divided by 1.4
        """
        if not multipliers:
            return
        self.context_multipliers = multipliers
        for signal, mult in multipliers.items():
            if signal in self.pre_ictal.trackers:
                original = self.pre_ictal.trackers[signal].threshold
                # higher multiplier = lower threshold = more sensitive
                new_threshold = max(0.05, original / mult)
                self.pre_ictal.trackers[signal].threshold = round(new_threshold, 3)
        print(f"🔧 Context thresholds applied: "
              + ", ".join(f"{s}:{self.pre_ictal.trackers[s].threshold:.2f}"
                          for s in multipliers if s in self.pre_ictal.trackers))

    def _keyboard_listener(self):
        import termios
        import tty
        
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            while not self.should_quit:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1)
                    if char == 'q' or char == 'Q':
                        self.should_quit = True
                        print("\n\n⏹️  Stopping application...")
                        break
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def _draw_debug_overlay(self, frame, conv_risk, nc_risk, pi, audio_score, log_data):
        """Draw a semi-transparent metrics panel on the right side of the frame."""
        import numpy as np
        h, w = frame.shape[:2]
        panel_w = 310
        x0 = w - panel_w - 8
        y0 = 8

        # rows: (label, value, colour)
        def _risk_col(v):
            return (0, 200, 80) if v < 0.3 else ((0, 200, 220) if v < 0.6 else (60, 60, 255))

        rows = [
            ("── DETECTION SCORES ──", "", (180, 180, 180)),
            ("  Shake",    f"{self.shake:.3f}",  _risk_col(self.shake)),
            ("  Blink",    f"{self.blink:.3f}",  _risk_col(self.blink)),
            ("  Eye",      f"{self.eye:.3f}",    _risk_col(self.eye)),
            ("  Freeze",   f"{self.freeze:.3f}", _risk_col(self.freeze)),
            ("  Asymmetry",f"{self.asym:.3f}",   _risk_col(self.asym)),
            ("  Twitch",   f"{self.twitch:.3f}", _risk_col(self.twitch)),
            ("  Color",    f"{self.color:.3f}",  _risk_col(self.color)),
            ("  BPM score",f"{self.bpm:.3f}",    _risk_col(self.bpm)),
            ("── AUDIO ──", "", (180, 180, 180)),
            ("  Score",    f"{audio_score:.3f}",                         _risk_col(audio_score)),
            ("  RMS",      f"{log_data.get('audio_rms', 0.0):.4f}",     (160, 160, 160)),
            ("  Groans",   f"{log_data.get('audio_groan_count', 0)}",    (160, 160, 160)),
            ("── RISK ──", "", (180, 180, 180)),
            ("  Convulsive",    f"{conv_risk:.3f}", _risk_col(conv_risk)),
            ("  Non-conv",      f"{nc_risk:.3f}",   _risk_col(nc_risk)),
            ("── PRE-ICTAL ──", "", (180, 180, 180)),
            ("  Score", f"{pi['pre_ictal_score']:.3f}", _risk_col(pi['pre_ictal_score'])),
            ("  Stage", pi.get('stage_label', '?'),    (200, 200, 200)),
            ("── WEIGHTS ──", "", (180, 180, 180)),
        ]
        for k, v in self.weights.items():
            rows.append((f"  {k}", f"{v:.2f}", (160, 160, 160)))

        line_h = 18
        pad = 8
        panel_h = len(rows) * line_h + pad * 2

        # semi-transparent dark background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x0 - pad, y0), (x0 + panel_w, y0 + panel_h), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)

        font = cv2.FONT_HERSHEY_SIMPLEX
        for i, (label, value, colour) in enumerate(rows):
            y = y0 + pad + i * line_h + line_h - 4
            cv2.putText(frame, label, (x0, y), font, 0.38, colour, 1, cv2.LINE_AA)
            if value:
                (vw, _), _ = cv2.getTextSize(value, font, 0.38, 1)
                cv2.putText(frame, value, (x0 + panel_w - vw - 4, y), font, 0.38, colour, 1, cv2.LINE_AA)

    def audio_module_init(self):
        try:
            import sys as _sys, os as _os
            _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            from audio_monitor import AudioMonitor
            from ui.audio_calibration import run_audio_calibration
            self.audio_monitor = AudioMonitor()
            # Calibrate ambient noise before starting — sets adaptive thresholds
            run_audio_calibration(self.audio_monitor)
            self.audio_monitor.start()
            print("🎤 Audio monitoring started")
        except Exception as e:
            self.audio_monitor = None
            print(f"⚠️  Audio monitoring unavailable: {e}")

    def stop_monitoring(self):
        self.should_quit = True

    def start(self):
        try:
            from ui.monitoring_status import MonitoringStatusWindow
            self.status_window = MonitoringStatusWindow(
                self.patient_name,
                on_stop=self.stop_monitoring,
                on_feedback=self._apply_feedback,
            )
            self.status_window.show()
        except Exception as e:
            print("Could not launch status window", e)
            self.status_window = None
        self._pi_warning_shown = False

        self.dashboard = None
        if self.debug_overlay:
            try:
                from ui.debug_window import MonitoringDashboard
                self.dashboard = MonitoringDashboard()
                self.dashboard.show()
            except Exception as e:
                print("Could not launch monitoring dashboard", e)
                self.dashboard = None

        if not self.debug and self.screen_protection:
            self._start_epilepsy_protection()

        self.keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self.keyboard_thread.start()
        print("="*60)
        print("📹 Monitoring started. Press 'q' to quit.")
        print("="*60)

        try:
            self._run_loop()
        finally:
            if hasattr(self, 'status_window') and self.status_window:
                self.status_window.close()
            if hasattr(self, 'dashboard') and self.dashboard:
                self.dashboard.close()
            if hasattr(self, 'audio_monitor') and self.audio_monitor:
                self.audio_monitor.stop()
            self.csv_logger.close()
            self._print_session_summary()
            self.cap.release()
            cv2.destroyAllWindows()
            if not self.debug and self.screen_protection:
                self._stop_epilepsy_protection()

    def _run_loop(self):
        calibration_frames = 150
        no_face_frames = 0

        consecutive_failures = 0

        while self.cap.isOpened() and not self.should_quit:
            drooping_frame = self.black_frame

            success, frame = self.cap.read()

            if not success:
                consecutive_failures += 1
                if consecutive_failures >= 10:
                    print("⚠️  Camera disconnected or unavailable — stopping.")
                    break
                continue

            consecutive_failures = 0

            to_screen_frame = frame.copy()

            if self.black_frame is None:
                self.black_frame = generate_black_frame(frame)

            landmarks, face_landmarks = self.get_face_landmarks(frame=frame)

            if len(landmarks) == 0 or not face_landmarks:
                no_face_frames += 1
                if self.debug:
                    status_frame = frame.copy()
                    cv2.putText(status_frame, "No face detected — adjust position", (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
                    cv2.imshow('Epilepsy debug', status_frame)
                    app = QApplication.instance()
                    if app: app.processEvents()
                    if cv2.waitKey(5) & 0xFF == ord('q'):
                        break
                continue

            no_face_frames = 0

            log_data = {'frame_index': self.frame_index}

            health_data = None
            if self.health_monitor_module:
                frame_health, result = self.health_monitor_module.process(frame, face_landmarks=face_landmarks)
                health_data = self.health_monitor_module.get_normalized_health_data()

                if not health_data.get('is_calibrated', False):
                    progress = min(self.frame_index, calibration_frames)
                    pct = int(progress / calibration_frames * 100)
                    cv2.putText(frame_health, f"Calibrating health monitor... {pct}%", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

                if self.solo_video:
                    frame = frame_health
                self.bpm = health_data.get('health_score', 0)
                self.color = health_data.get('color_score', 0)
                log_data['health_score'] = health_data.get('health_score', 0)
                log_data['heart_rate'] = health_data.get('heart_rate', 0)
                log_data['color_score'] = health_data.get('color_score', 0)
                log_data['is_calibrated'] = health_data.get('is_calibrated', False)

            if self.shake_detection_module:
                frame_shake, shake_data = self.shake_detection_module.detect(frame,
                face_landmarks=face_landmarks)
                self.shake = shake_data['head_score']
                if self.shake >= 0.95:
                    print(f"Violent shaking detected! Head Score: {self.shake:.2f}")
                if self.solo_video:
                    frame = frame_shake
                log_data['head_score'] = shake_data.get('head_score', 0)
                log_data['energy'] = shake_data.get('energy', 0)
                log_data['direction_flips'] = shake_data.get('direction_flips', 0)

            droop_data = None
            if self.face_drooping_model:
                drooping_frame, droop_data = self.face_drooping_model.process_frame(frame=frame, face_landmarks=face_landmarks)
                self.asym = droop_data['droop_score']
                if self.solo_video:
                    frame = drooping_frame
                log_data['droop_score'] = droop_data.get('droop_score', 0)
                log_data['droop_duration'] = droop_data.get('droop_duration', 0)

            eye_data = None
            if self.eye_tracking_module:
                frame_eye, eye_data = self.eye_tracking_module.get_eye_center(frame, face_landmarks)
                self.eye = eye_data['eye_score']
                if self.solo_video:
                    frame = frame_eye
                log_data['eye_score'] = eye_data.get('eye_score', 0)
                log_data['eye_deviation'] = eye_data.get('deviation', 0)
                log_data['eye_movement_speed'] = eye_data.get('movement_speed', 0)

            blink_data = None
            if self.blinker_module:
                frame_blinked, blink_data = self.blinker_module.check_blink_eye(frame, landmarks=landmarks, face_landmarks=face_landmarks)
                self.blink = blink_data['blink_score']
                if self.solo_video:
                    frame = frame_blinked
                log_data['blink_score'] = blink_data.get('blink_score', 0)
                log_data['blink_count'] = blink_data.get('blink_count', 0)
                log_data['blink_rate'] = blink_data.get('blink_rate', 0)

            if self.twitch_detector_module:
                frame_twitch, twitch_data = self.twitch_detector_module.detect(frame=frame, face_landmarks=face_landmarks)
                self.twitch = twitch_data['twitch_score']
                if self.solo_video:
                    frame = frame_twitch
                log_data['twitch_score'] = twitch_data.get('twitch_score', 0)
                log_data['twitch_count'] = twitch_data.get('twitch_count', 0)

            if self.face_freeze_modul:
                frame_freeze = self.face_freeze_modul.moved(frame, landmarks=landmarks, face_landmarks=face_landmarks)
                if self.solo_video:
                    frame = frame_freeze

            freeze_data = None
            if self.face_freeze_modul:
                freeze_data = self.face_freeze_modul.get_freeze_data()
                self.freeze = freeze_data.get('freeze_score', 0)
                log_data['freeze_score'] = freeze_data.get('freeze_score', 0)
                log_data['freeze_duration'] = freeze_data.get('freeze_duration', 0)
                log_data['is_frozen'] = freeze_data.get('is_frozen', False)
                freeze_status = "FROZEN" if freeze_data['is_frozen'] else "MOVING"

            # Audio score (0–1): normalised groan count within the warning window
            audio_score = 0.0
            if hasattr(self, 'audio_monitor') and self.audio_monitor:
                a = self.audio_monitor.get_scores()
                audio_score = min(a['audio_groan_count'] / 4.0, 1.0)
                log_data['audio_rms']         = round(a['audio_rms'], 4)
                log_data['audio_groan_count'] = a['audio_groan_count']

            w = self.weights
            if self.shake >= 0.95:
                convulsive_risk = 1.0
            else:
                convulsive_risk = (w['w_bpm']*self.bpm + self.shake*w['w_shake']
                                   + self.blink*w['w_blink'] + self.color*w['w_color']
                                   + audio_score*w.get('w_audio', 0.25))

            x_non_convulsive = (self.asym*w['w_asym'] + self.freeze*w['w_freeze']
                                + self.blink*w['w_blink_nc'] + self.bpm*w['w_bpm_nc']
                                + self.color*w['w_color'] + self.twitch*w['w_twitch']
                                + audio_score*w.get('w_audio', 0.25))

            # ── Pre-ictal temporal analysis ───────────────────────────────
            pi = self.pre_ictal.update(
                shake=self.shake, blink=self.blink, eye=self.eye,
                freeze=self.freeze, asym=self.asym, twitch=self.twitch,
                bpm=self.bpm, color=self.color,
            )
            log_data['pre_ictal_score'] = pi['pre_ictal_score']
            log_data['pre_ictal_stage'] = pi['stage']

            if (convulsive_risk >= 1.0 or x_non_convulsive >= 1.0) and not self.sms_sent and not self.pending_feedback:
                alert_type = "convulsive" if convulsive_risk >= 1.0 else "non-convulsive"
                if self.sms_client:
                    self.sms_client.send_message(f"⚠️ High {alert_type} seizure risk detected!")
                    self.sms_sent = True
                print(f"⚠️  High {alert_type} seizure risk! Convulsive: {convulsive_risk:.3f} | Non-convulsive: {x_non_convulsive:.3f}")
                self.pending_feedback = True
                self.alert_scores_snapshot = {
                    'shake': self.shake, 'blink': self.blink, 'bpm': self.bpm,
                    'color': self.color, 'asym': self.asym, 'freeze': self.freeze,
                    'twitch': self.twitch, 'eye': self.eye,
                }
                if self.status_window:
                    self.status_window.show_alert(alert_type, self.sms_sent)

            if self.status_window:
                if pi['warning'] and not self._pi_warning_shown:
                    self.status_window.show_pre_ictal_warning(pi.get('stage_label', '—'))
                    self._pi_warning_shown = True
                elif not pi['warning'] and self._pi_warning_shown:
                    self.status_window.clear_pre_ictal_warning()
                    self._pi_warning_shown = False

            if self.frame_index % 150 == 0:
                if self.face_freeze_modul:
                    self.face_freeze_modul.check_if_ok()

            if self.csv_logger.should_log():
                self.csv_logger.log_row(log_data)

            if self.debug_overlay:
                if self.dashboard:
                    self.dashboard.update_metrics({
                        'shake': self.shake,
                        'blink': self.blink,
                        'eye': self.eye,
                        'freeze': self.freeze,
                        'asym': self.asym,
                        'twitch': self.twitch,
                        'color': self.color,
                        'bpm': self.bpm,
                        'conv_risk': convulsive_risk,
                        'nc_risk': x_non_convulsive,
                        'pi_score': pi['pre_ictal_score'],
                        'pi_stage': pi.get('stage_label', '—'),
                        'audio_score': audio_score,
                        'audio_rms': log_data.get('audio_rms', 0.0),
                        'audio_groans': log_data.get('audio_groan_count', 0),
                        'weights': self.weights,
                        'sms_configured': self.sms_client is not None,
                        'sms_sent': self.sms_sent,
                        'alert_pending': self.pending_feedback,
                        'alert_type': ('convulsive' if convulsive_risk >= 1.0 else
                                       'non-convulsive' if x_non_convulsive >= 1.0 else None),
                    })
                    _locs = locals()
                    self.dashboard.update_frames({
                        'freeze':   _locs.get('frame_freeze'),
                        'eye':      _locs.get('frame_eye'),
                        'blink':    _locs.get('frame_blinked'),
                        'twitch':   _locs.get('frame_twitch'),
                        'shake':    _locs.get('frame_shake'),
                        'drooping': _locs.get('drooping_frame'),
                        'health':   _locs.get('frame_health'),
                    })
            if self.debug:
                if self.solo_video:
                    # Show freeze state prominently
                    if freeze_data is not None:
                        freeze_status = "FROZEN" if freeze_data['is_frozen'] else "MOVING"
                        freeze_color = (0, 0, 255) if freeze_data['is_frozen'] else (0, 255, 0)  # Red if frozen, green if moving
                        cv2.putText(frame, f"State: {freeze_status}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, freeze_color, 3)

                    if blink_data is not None:
                        cv2.putText(frame, f"Blink Score: {blink_data['blink_score']:.2f} (Count:{blink_data['blink_count']} Rate:{blink_data['blink_rate']:.2f}/s)", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if twitch_data is not None:
                        cv2.putText(frame, f"Twitch Score: {twitch_data['twitch_score']:.2f} (Count:{twitch_data['twitch_count']} in 5s)", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if shake_data is not None:
                        cv2.putText(frame, f"Head Score: {shake_data['head_score']:.2f} (E:{shake_data['energy']:.2f} F:{shake_data['direction_flips']})", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if eye_data is not None:
                        cv2.putText(frame, f"Eye Score: {eye_data['eye_score']:.2f} (Dev:{eye_data['deviation']:.3f} Spd:{eye_data['movement_speed']:.3f})", (10, 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if droop_data is not None:
                        cv2.putText(frame, f"Droop Score: {droop_data['droop_score']:.2f} (Duration:{droop_data['droop_duration']:.1f}s)", (10, 180),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if freeze_data is not None:
                        cv2.putText(frame, f"Freeze Score: {freeze_data['freeze_score']:.2f} (Duration:{freeze_data['freeze_duration']:.1f}s Frozen:{freeze_data['is_frozen']})", (10, 210),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if health_data is not None and health_data['is_calibrated']:
                        cv2.putText(frame, f"Health Score: {health_data['health_score']:.2f} (BPM:{health_data['heart_rate']} Color:{health_data['color_score']:.2f})", (10, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                    # Display seizure risks prominently
                    # Color coding: Green (0-0.3), Yellow (0.3-0.6), Red (0.6-1.0)
                    conv_color = (0, 255, 0) if convulsive_risk < 0.3 else ((0, 255, 255) if convulsive_risk < 0.6 else (0, 0, 255))
                    non_conv_color = (0, 255, 0) if x_non_convulsive < 0.3 else ((0, 255, 255) if x_non_convulsive < 0.6 else (0, 0, 255))

                    cv2.putText(frame, f"CONVULSIVE RISK: {convulsive_risk:.3f}", (10, 280),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, conv_color, 2)
                    cv2.putText(frame, f"NON-CONVULSIVE RISK: {x_non_convulsive:.3f}", (10, 310),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, non_conv_color, 2)

                    # Pre-ictal temporal score
                    pi_score = pi['pre_ictal_score']
                    pi_label = pi['stage_label']
                    pi_color = (
                        (0, 255, 0)     if pi_score < 0.3 else
                        (0, 200, 255)   if pi_score < 0.55 else
                        (0, 100, 255)
                    )
                    cv2.putText(frame, f"PRE-ICTAL [{pi_label}]: {pi_score:.3f}", (10, 345),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, pi_color, 2)

                    # show elevated + rising signals when in non-baseline stage
                    if pi['stage'] > 0:
                        elev = ', '.join(pi['elevated_signals']) or '-'
                        rising = ', '.join(pi['rising_signals']) or '-'
                        cv2.putText(frame, f"  elevated: {elev}", (10, 372),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
                        cv2.putText(frame, f"  rising:   {rising}", (10, 390),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

                    # pre-ictal warning banner
                    if pi['warning']:
                        h, fw = frame.shape[:2]
                        overlay = frame.copy()
                        cv2.rectangle(overlay, (0, 0), (fw, 36), (0, 80, 200), -1)
                        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
                        cv2.putText(frame, f"⚠  PRE-ICTAL WARNING — {pi_label} stage detected",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

                    if self.pending_feedback:
                        overlay = frame.copy()
                        h, fw = frame.shape[:2]
                        cv2.rectangle(overlay, (0, h-110), (fw, h), (30, 30, 30), -1)
                        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
                        cv2.putText(frame, "⚠ ALERT — Was this a real seizure?", (10, h-75),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
                        cv2.putText(frame, "Press Y = yes (correct)   N = no (false alarm)", (10, h-45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

                    # session duration + review hint in bottom-right
                    elapsed_min = int((time.time() - self._session_start) / 60)
                    h_fr, w_fr = frame.shape[:2]
                    duration_text = f"Session: {elapsed_min}m  |  R = review"
                    (tw, _), _ = cv2.getTextSize(duration_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    cv2.putText(frame, duration_text, (w_fr - tw - 10, h_fr - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1)

                    # 2-hour auto-review nudge
                    if elapsed_min >= 120 and not self._auto_review_shown:
                        overlay = frame.copy()
                        cv2.rectangle(overlay, (0, h_fr - 50), (w_fr, h_fr), (20, 20, 60), -1)
                        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
                        cv2.putText(frame, f"⏱  {elapsed_min}min session — press R to open review & recalibrate",
                            (10, h_fr - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 180, 255), 1)

                    cv2.imshow('Epilepsy debug', frame)
                else:
                    # guard against None frames when face was lost mid-frame
                    blank = generate_black_frame(frame)
                    def _safe(f): return f if f is not None else blank
                    top = cv2.hconcat([_safe(frame_freeze), _safe(frame_eye), _safe(frame_blinked)])
                    mid = cv2.hconcat([_safe(frame_twitch), _safe(frame_shake), _safe(drooping_frame)])
                    bottom = cv2.hconcat([_safe(frame_health), generate_black_frame(frame=frame, data=log_data), blank])
                    if top.shape[1] == mid.shape[1] == bottom.shape[1]:
                        mosaic = cv2.vconcat([top, mid, bottom])
                        cv2.imshow("All Views debug", mosaic)

            self.frame_index += 1
            if self.frame_index > self.frame_reset:
                self.frame_index = 1

            # Pump Qt events every frame so status/debug windows stay responsive
            _app = QApplication.instance()
            if _app:
                _app.processEvents()

            if self.debug:

                key = cv2.waitKey(5) & 0xFF
                if key == ord('q'):
                    break
                elif key in (ord('r'), ord('R')) or self._review_requested:
                    self._review_requested = False
                    self._auto_review_shown = True
                    self._show_interim_review()
                elif key == ord('s') and self.sms_client:
                    self.sms_client.send_message("⚠️ Test alert: simulated seizure risk (debug hotkey).")
                elif self.pending_feedback:
                    if key == ord('y') or key == ord('Y'):
                        self._apply_feedback(correct=True)
                    elif key == ord('n') or key == ord('N'):
                        self._apply_feedback(correct=False)
            else:
                if self._review_requested:
                    self._review_requested = False
                    self._auto_review_shown = True
                    self._show_interim_review()
                app = QApplication.instance()
                if app: app.processEvents()
                cv2.waitKey(1)

    def _apply_feedback(self, correct):
        scores = self.alert_scores_snapshot
        factor = LEARN_RATE_UP if correct else LEARN_RATE_DOWN
        label = "✅ Correct" if correct else "❌ False positive"
        print(f"\n{label} — adjusting weights...")

        # signals that contributed meaningfully to this alert
        signal_to_weight = {
            'shake': 'w_shake', 'blink': 'w_blink', 'bpm': 'w_bpm',
            'color': 'w_color', 'asym': 'w_asym', 'freeze': 'w_freeze',
            'twitch': 'w_twitch',
        }
        for signal, wkey in signal_to_weight.items():
            if scores.get(signal, 0) > 0.3:
                old = self.weights[wkey]
                self.weights[wkey] = round(
                    max(WEIGHT_MIN, min(WEIGHT_MAX, old * factor)), 3
                )
                if self.weights[wkey] != old:
                    print(f"  {wkey}: {old:.3f} → {self.weights[wkey]:.3f}")

        self._save_weights()

        self.feedback_events.append({'scores': dict(scores), 'correct': correct})
        self.pending_feedback = False
        self.alert_scores_snapshot = {}
        self.sms_sent = False  # allow future alerts
        self._pi_warning_shown = False  # allow pre-ictal warning to re-trigger

    def _print_session_summary(self):
        print("\n" + "="*60)
        print("🔄 GENERATING SESSION SUMMARY...")
        print("="*60)

        summary_text = self.csv_logger.get_summary_for_llm()

        ai_analysis = None
        if self.ai_client:
            print("🤖 Running AI analysis...")
            ai_analysis = self.ai_client.analyze_session(summary_text)
            if not ai_analysis:
                ai_analysis = "⚠️ Failed to get AI analysis."

            if self.feedback_events:
                print(f"🧠 Recalibrating weights using {len(self.feedback_events)} feedback event(s)...")
                raw = self.ai_client.recalibrate_weights(self.weights, self.feedback_events)
                if raw:
                    try:
                        import json, re
                        cleaned = re.sub(r"```json|```", "", raw).strip()
                        new_weights = json.loads(cleaned)
                        for k, v in new_weights.items():
                            if k in self.weights:
                                self.weights[k] = round(max(WEIGHT_MIN, min(WEIGHT_MAX, float(v))), 3)
                        self._save_weights()
                        print(f"✅ Weights updated by Gemini for next session: {self.weights}")
                    except Exception as e:
                        print(f"Could not parse recalibration response: {e}")

        filepath = self.csv_logger.get_filepath()

        print("✓ Analysis complete, opening summary window...")
        summary_window = SummaryWindow()
        summary_window.show_summary(
            summary_text=summary_text,
            ai_analysis=ai_analysis,
            filepath=filepath,
            ai_client=self.ai_client,
            current_weights=self.weights,
            on_weights_saved=self._on_weights_saved,
        )

    def _save_weights(self):
        if self.patient_id:
            from core import account_store as _as
            _as.save_weights(self.patient_id, self.weights)
        else:
            save_weights(self.weights)

    def _on_weights_saved(self, new_weights):
        self.weights.update(new_weights)
        self._save_weights()
        print(f"✅ Weights saved from review session: {self.weights}")

    def _start_epilepsy_protection(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        epilepsy_script = os.path.join(script_dir, 'epilepsy_content_recognition.py')
        self.epilepsy_process = subprocess.Popen(
            [sys.executable, epilepsy_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def _stop_epilepsy_protection(self):
        if self.epilepsy_process:
            self.epilepsy_process.terminate()
            self.epilepsy_process = None

    def get_face_landmarks(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = self.face_mesh.process(rgb_frame)
        if not results.multi_face_landmarks:
            return [], []

        return [{ "x": lm.x, "y": lm.y, "z": lm.z} for lm in results.multi_face_landmarks[0].landmark], results.multi_face_landmarks[0]

    def face_freeze_module_init(self):
        self.face_freeze_modul = FaceFreeze(mp_face_mesh=self.mp_face_mesh, mp_drawing=self.mp_drawing, mp_drawing_styles=self.mp_drawing_styles)

    def eye_tracking_module_init(self):
        self.eye_tracking_module = EyeTracking(debug=self.debug)

    def blinking_module_init(self):
        self.blinker_module = BlinkDetector(mp_face_mesh=self.mp_face_mesh, mp_drawing=self.mp_drawing, mp_drawing_styles=self.mp_drawing_styles)

    def twitch_detector_module_init(self):
        self.twitch_detector_module = TwitchDetector(debug=self.debug)

    def shake_detection_module_init(self):
        self.shake_detection_module = SeizureDetector()
    
    def face_drooping_model_init(self):
        self.face_drooping_model = FaceMeshViewer()
    
    def health_monitor_module_init(self):
        self.health_monitor_module = HealthMonitor()

def generate_black_frame(frame, data = None):
    h, w = frame.shape[:2]

    black = np.zeros_like(frame)
    cv2.putText(
        black, "", (50, 100),
        cv2.FONT_HERSHEY_SIMPLEX, 2,
        (0, 255, 255), 3
    )

    if data is not None:
        y_offset = 100
        line_height = 40

        for key, value in data.items():
            cv2.putText(
                black, f"{key}: {value}", (50, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (255, 255, 255), 2
            )
            y_offset += line_height

    return black