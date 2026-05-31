import cv2
import mediapipe as mp
import numpy as np
import subprocess
import sys
import os
import json
import threading
import select

from face_freeze import FaceFreeze
from eye_tracking import EyeTracking
from check_blink_eye import BlinkDetector
from twitch_detector import TwitchDetector
from shake_detection import SeizureDetector
from face_drooping import FaceMeshViewer
from health_monitor_module import HealthMonitor
from csv_logger import CSVLogger
from gpt_client import AIClient
from summary_window import SummaryWindow
from pre_ictal_detector import PreIctalDetector
from audio_monitor import AudioMonitor

WEIGHTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'weights.json')

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
    def __init__(self, debug=False, solo_video=True, ai_client=None, sms_client=None):
        self.frame_index = 0
        self.frame_reset = 150
        self.debug = debug
        self.solo_video = solo_video
        self.black_frame = None
        self.epilepsy_process = None
        self.ai_client = ai_client
        self.sms_client = sms_client
        
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
        self.audio_monitor = None
        
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

        self.audio_rms = 0.0
        self.audio_groan_count = 0
        self.audio_warning = 0.0
        self.audio_max_rms = 0.0
        self.audio_triggered = False
        self.audio_has_triggered = False

        self.weights = load_weights()
        print(f"📊 Loaded weights: {self.weights}")

        self.pre_ictal = PreIctalDetector()
        self.context_multipliers = {}  # set externally from menu result

        # feedback state
        self.pending_feedback = False     # waiting for Y/N after an alert
        self.alert_scores_snapshot = {}  # scores at the moment alert fired
        self.feedback_events = []        # list of {scores, correct} for end-of-session LLM recalibration

    def _open_builtin_camera(self):
        platform = sys.platform

        if platform == "darwin":
            # Try to find the built-in FaceTime/webcam by name, skipping Continuity Camera
            preferred_keywords = ['facetime', 'built-in', 'integrated', 'internal']
            skip_keywords = ['iphone', 'ipad', 'continuity', 'droid']

            for index in range(6):
                cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
                if not cap.isOpened():
                    continue
                # cv2 doesn't expose camera name directly on macOS, so use AVFoundation via subprocess
                try:
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
            return cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

        if platform.startswith("win"):
            # Windows: DirectShow tends to be the most reliable
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            return cv2.VideoCapture(0)

        # Linux / WSL: try V4L2, then default
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if cap.isOpened():
            return cap
        return cv2.VideoCapture(0)

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

    def start(self):
        if not self.debug:
            self._start_epilepsy_protection()

        self.keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self.keyboard_thread.start()
        print("="*60)
        print("📹 Monitoring started. Press 'q' to quit.")
        print("="*60)

        try:
            self._run_loop()
        finally:
            if self.audio_monitor:
                self.audio_monitor.stop()
            self.csv_logger.close()
            self._print_session_summary()
            self.cap.release()
            cv2.destroyAllWindows()
            if not self.debug:
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

            if self.audio_monitor:
                audio_scores = self.audio_monitor.get_scores()
                self.audio_rms = audio_scores.get('audio_rms', 0.0)
                self.audio_groan_count = audio_scores.get('audio_groan_count', 0)
                self.audio_warning = audio_scores.get('audio_warning', 0.0)
                self.audio_max_rms = audio_scores.get('audio_max_rms', 0.0)
                self.audio_triggered = audio_scores.get('audio_triggered', False)
                self.audio_has_triggered = audio_scores.get('audio_has_triggered', False)

                log_data['audio_rms'] = self.audio_rms
                log_data['audio_groan_count'] = self.audio_groan_count
                log_data['audio_warning'] = self.audio_warning

            w = self.weights
            if self.shake >= 0.95:
                convulsive_risk = 1.0
            else:
                convulsive_risk = w['w_bpm']*self.bpm + self.shake*w['w_shake'] + self.blink*w['w_blink'] + self.color*w['w_color']

            x_non_convulsive = self.asym*w['w_asym'] + self.freeze*w['w_freeze'] + self.blink*w['w_blink_nc'] + self.bpm*w['w_bpm_nc'] + self.color*w['w_color'] + self.twitch*w['w_twitch']

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

            if self.frame_index % 150 == 0:
                if self.face_freeze_modul:
                    self.face_freeze_modul.check_if_ok()

            if self.csv_logger.should_log():
                self.csv_logger.log_row(log_data)

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
                    if self.audio_monitor:
                        cv2.putText(frame, f"RMS:{self.audio_rms:.3f} Groans:{self.audio_groan_count} Warn:{self.audio_warning:.0f} Trigger:{self.audio_triggered} MAX:{self.audio_max_rms:.3f}", (10, 265),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

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

                    cv2.imshow('Epilepsy debug', frame)
                else:
                    # guard against None frames when face was lost mid-frame
                    blank = generate_black_frame(frame)
                    def _safe(f): return f if f is not None else blank
                    top = cv2.hconcat([_safe(frame_freeze), _safe(frame_eye), _safe(frame_blinked)])
                    mid = cv2.hconcat([_safe(frame_twitch), _safe(frame_shake), _safe(drooping_frame)])
                    bottom = cv2.hconcat([_safe(frame_health), generate_black_frame(frame=frame, data=log_data), blank])
                    # only show if all rows have the same width
                    if top.shape[1] == mid.shape[1] == bottom.shape[1]:
                        mosaic = cv2.vconcat([top, mid, bottom])
                        cv2.imshow("All Views debug", mosaic)

            self.frame_index += 1
            if self.frame_index > self.frame_reset:
                self.frame_index = 1

            if self.debug:
                key = cv2.waitKey(5) & 0xFF
                if key == ord('q'):
                    break
                elif self.pending_feedback:
                    if key == ord('y') or key == ord('Y'):
                        self._apply_feedback(correct=True)
                    elif key == ord('n') or key == ord('N'):
                        self._apply_feedback(correct=False)
            else:
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

        save_weights(self.weights)

        self.feedback_events.append({'scores': dict(scores), 'correct': correct})
        self.pending_feedback = False
        self.alert_scores_snapshot = {}
        self.sms_sent = False  # allow future alerts

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
                        save_weights(self.weights)
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

    def _on_weights_saved(self, new_weights):
        self.weights.update(new_weights)
        save_weights(self.weights)
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

    def audio_module_init(self):
        try:
            self.audio_monitor = AudioMonitor()
            self.audio_monitor.start()
        except Exception as e:
            print(f"Audio monitor disabled: {e}")

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