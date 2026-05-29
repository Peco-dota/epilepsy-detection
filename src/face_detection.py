import cv2
import mediapipe as mp
import numpy as np
import subprocess
import sys
import os
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


w_bpm = 0.10     
w_color = 0.10    
w_shake = 0.30
w_twitch = 0.35
w_blink = 0.3

w_freeze = 0.40    
w_asym = 0.55      
w_blink_zero = 0.3 
w_bpm_nc = 0.10    

bpm = 0
twitch = 0
blink = 0
color = 0
freeze = 0
asym = 0
eye = 0
shake = 0

convulsive_risk = 0
non_convulsive_risk = 0

sms_sent = False
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
        
        self.cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

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
                        print("\n\n⏹️  Ukončujem aplikáciu...")
                        break
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def start(self):
        if not self.debug:
            self._start_epilepsy_protection()
            self.keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
            self.keyboard_thread.start()
            print("="*60)
            print("📹 Monitorovanie spustené. Stlačte 'q' pre ukončenie.")
            print("="*60)

        while self.cap.isOpened() and not self.should_quit:
            drooping_frame = self.black_frame

            success, frame = self.cap.read()

            if not success:
                continue
            
            to_screen_frame = frame.copy()

            if self.black_frame is None:
                self.black_frame = generate_black_frame(frame)
            
            landmarks, face_landmarks = self.get_face_landmarks(frame=frame)

            if (len(landmarks) == 0 or not face_landmarks):
                continue

            log_data = {'frame_index': self.frame_index}

            health_data = None
            if self.health_monitor_module:
                frame_health, result = self.health_monitor_module.process(frame, face_landmarks=face_landmarks)
                health_data = self.health_monitor_module.get_normalized_health_data()

                if self.solo_video:
                    frame = frame_health
                log_data['health_score'] = health_data.get('health_score', 0)
                log_data['heart_rate'] = health_data.get('heart_rate', 0)
                log_data['color_score'] = health_data.get('color_score', 0)
                log_data['is_calibrated'] = health_data.get('is_calibrated', False)

            # Shake detection
            if self.shake_detection_module:
                frame_shake, shake_data = self.shake_detection_module.detect(frame, 
                face_landmarks=face_landmarks)
                shake = shake_data['head_score']
                #print(f"Shake Data: {shake:.2f}")
                if shake >= 0.95:
                    print(f"Violent shaking detected! Head Score: {shake:.2f}")
                if self.solo_video:
                    frame = frame_shake
                log_data['head_score'] = shake_data.get('head_score', 0)
                log_data['energy'] = shake_data.get('energy', 0)
                log_data['direction_flips'] = shake_data.get('direction_flips', 0)

            droop_data = None
            if self.face_drooping_model:
                drooping_frame, droop_data = self.face_drooping_model.process_frame(frame=frame, face_landmarks=face_landmarks)
                asym = droop_data['droop_score']
                print("Asym: ", asym)
                if self.solo_video:
                    frame = drooping_frame
                log_data['droop_score'] = droop_data.get('droop_score', 0)
                log_data['droop_duration'] = droop_data.get('droop_duration', 0)

            eye_data = None
            if self.eye_tracking_module:
                frame_eye, eye_data = self.eye_tracking_module.get_eye_center(frame, face_landmarks)
                eye = eye_data['eye_score']
                if self.solo_video:
                    frame = frame_eye
                log_data['eye_score'] = eye_data.get('eye_score', 0)
                log_data['eye_deviation'] = eye_data.get('deviation', 0)
                log_data['eye_movement_speed'] = eye_data.get('movement_speed', 0)

            blink_data = None
            if self.blinker_module:
                frame_blinked, blink_data = self.blinker_module.check_blink_eye(frame, landmarks=landmarks, face_landmarks=face_landmarks)
                blink = blink_data['blink_score']
                if self.solo_video:
                    frame = frame_blinked
                log_data['blink_score'] = blink_data.get('blink_score', 0)
                log_data['blink_count'] = blink_data.get('blink_count', 0)
                log_data['blink_rate'] = blink_data.get('blink_rate', 0)

            # Checking twitch
            if self.twitch_detector_module:
                frame_twitch, twitch_data = self.twitch_detector_module.detect(frame=frame, face_landmarks=face_landmarks)
                twitch = twitch_data['twitch_score']
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
                log_data['freeze_score'] = freeze_data.get('freeze_score', 0)
                log_data['freeze_duration'] = freeze_data.get('freeze_duration', 0)
                log_data['is_frozen'] = freeze_data.get('is_frozen', False)
                freeze_status = "FROZEN" if freeze_data['is_frozen'] else "MOVING"
                

            if shake >= 0.95:
                convulsive_risk = 1.0

            else:
                convulsive_risk = w_bpm*bpm + shake*w_shake + blink*w_blink + color*w_color

            print("convulsive_risk:", convulsive_risk)

            if convulsive_risk >= 1.0:
                if self.sms_client and not sms_sent:
                    self.sms_client.send_message("⚠️ Vysoké riziko konvulzívneho záchvatu detekované!")
                print(f"High convulsive seizure risk detected! Risk Score: {convulsive_risk:.3f}")

            
            x_non_convulsive = asym*w_asym + freeze*w_freeze + blink*w_blink_zero + bpm*w_bpm_nc + color*w_color + twitch*w_twitch

            if x_non_convulsive >= 1.0 and not sms_sent:
                if self.sms_client:
                    self.sms_client.send_message("⚠️ Vysoké riziko nekonvulzívneho záchvatu detekované!")
                print(f"High non-convulsive seizure risk detected! Risk Score: {x_non_convulsive:.3f}")
                
            print("non_convulsive_risk:", x_non_convulsive)

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

                    # Display seizure risks prominently
                    # Color coding: Green (0-0.3), Yellow (0.3-0.6), Red (0.6-1.0)
                    conv_color = (0, 255, 0) if convulsive_risk < 0.3 else ((0, 255, 255) if convulsive_risk < 0.6 else (0, 0, 255))
                    non_conv_color = (0, 255, 0) if non_convulsive_risk < 0.3 else ((0, 255, 255) if non_convulsive_risk < 0.6 else (0, 0, 255))

                    cv2.putText(frame, f"CONVULSIVE RISK: {convulsive_risk:.3f}", (10, 280),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, conv_color, 2)
                    cv2.putText(frame, f"NON-CONVULSIVE RISK: {non_convulsive_risk:.3f}", (10, 310),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, non_conv_color, 2)

                    cv2.imshow('Epilepsy debug', frame)
                else:
                    top = cv2.hconcat([frame_freeze, frame_eye, frame_blinked])
                    mid = cv2.hconcat([frame_twitch, frame_shake, drooping_frame])
                    bottom = cv2.hconcat([frame_health, generate_black_frame(frame=frame, data=log_data), self.black_frame])
                    mosaic = cv2.vconcat([top, mid, bottom])
                    cv2.imshow("All Views debug", mosaic)
                
            if False: # Screenshot because high values (ale bez zachvatu)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"summary/{timestamp}.png"
                cv2.imwrite(filename, to_screen_frame)

            self.frame_index += 1
            if self.frame_index > self.frame_reset:
                self.frame_index = 1

            if self.debug:
                if cv2.waitKey(5) & 0xFF == ord('q'):
                    break
            else:
                cv2.waitKey(1)

        self.csv_logger.close()
        self._print_session_summary()
        self.cap.release()
        if not self.debug: 
            self._stop_epilepsy_protection()

    def _print_session_summary(self):
        print("\n" + "="*60)
        print("🔄 GENERUJEM SÚHRN SESSION...")
        print("="*60)
        
        summary_text = self.csv_logger.get_summary_for_llm()
        
        ai_analysis = None
        if self.ai_client:
            print("🤖 Spúšťam AI analýzu...")
            ai_analysis = self.ai_client.analyze_session(summary_text)
            if not ai_analysis:
                ai_analysis = "⚠️ Nepodarilo sa získať AI analýzu."
        
        filepath = self.csv_logger.get_filepath()
        
        # Zobraz súhrn v grafickom okne
        print("✓ Analýza dokončená, otváram okno so súhrnom...")
        summary_window = SummaryWindow()
        summary_window.show_summary(
            summary_text=summary_text,
            ai_analysis=ai_analysis,
            filepath=filepath
        )

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