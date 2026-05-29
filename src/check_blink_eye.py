import time
from mediapipe_indexes import LEFT_EYE_IDXS, RIGHT_EYE_IDXS
import cv2

# returns True if user blinks at least "blink_count_threshold" times in "blink_time_threshold" seconds

class BlinkDetector:
    def __init__(self, mp_face_mesh, mp_drawing, mp_drawing_styles):
        self.start_time = time.time()
        self.is_right_blinking = False
        self.is_left_blinking = False
        self.time_when_blinked = []
        self.blink_time_threshold = 10  # seconds
        self.blink_count_threshold = 10  # blinks (threshold for abnormal)

        # Normalization constants
        self.NORMAL_BLINK_RATE = 0.17  # blinks/sec (normal: ~10/min)
        self.SEIZURE_BLINK_RATE = 2.0   # blinks/sec (rapid flutter)

        self.mp_face_mesh = mp_face_mesh
        self.mp_drawing = mp_drawing
        self.mp_drawing_styles = mp_drawing_styles

    def set_blink_time_threshold(self, threshold):
        self.blink_time_threshold = threshold

    def set_blink_count_threshold(self, threshold):
        self.blink_count_threshold = threshold

    def check_blink_eye(self, frame, landmarks, face_landmarks):
        left_top = landmarks[LEFT_EYE_IDXS[0]]['y']
        left_bot = landmarks[LEFT_EYE_IDXS[1]]['y']
        left_dist = abs(left_top - left_bot)

        right_top = landmarks[RIGHT_EYE_IDXS[0]]['y']
        right_bot = landmarks[RIGHT_EYE_IDXS[1]]['y']
        right_dist = abs(right_top - right_bot)

        right_eye_closed = right_dist < 0.01
        left_eye_closed = left_dist < 0.01
        both_eyes_closed = right_eye_closed and left_eye_closed

        if both_eyes_closed and not (self.is_right_blinking and self.is_left_blinking):
            self.is_right_blinking = True
            self.is_left_blinking = True
            self.time_when_blinked.append(time.time() - self.start_time)
        elif right_eye_closed and not left_eye_closed and not self.is_right_blinking:
            self.is_right_blinking = True
            self.time_when_blinked.append(time.time() - self.start_time)
        elif left_eye_closed and not right_eye_closed and not self.is_left_blinking:
            self.is_left_blinking = True
            self.time_when_blinked.append(time.time() - self.start_time)
        
        if not right_eye_closed:
            self.is_right_blinking = False
        if not left_eye_closed:
            self.is_left_blinking = False

        current_time = time.time() - self.start_time

        for t in self.time_when_blinked:
            if current_time - self.blink_time_threshold > t:
                self.time_when_blinked.remove(t)

        eye_frame = self.render_eye(frame=frame, face_landmarks=face_landmarks)

        # Calculate blink rate (blinks per second)
        blink_count = len(self.time_when_blinked)
        blink_rate = blink_count / self.blink_time_threshold  # blinks/sec

        # Normalize blink rate to 0-1 scale
        # Below normal rate → 0.0
        # Above seizure rate → 1.0
        if blink_rate <= self.NORMAL_BLINK_RATE:
            blink_score = 0.0
        else:
            blink_score = min(1.0,
                (blink_rate - self.NORMAL_BLINK_RATE) /
                (self.SEIZURE_BLINK_RATE - self.NORMAL_BLINK_RATE)
            )

        # Check if abnormal (boolean for backward compatibility)
        is_abnormal = blink_count >= self.blink_count_threshold

        blink_data = {
            'blink_count': blink_count,
            'blink_rate': blink_rate,
            'blink_score': blink_score,
            'is_abnormal': is_abnormal
        }

        return eye_frame, blink_data
    
    def render_eye(self, frame, face_landmarks):
        eye_frame = frame.copy()
        red_lines = self.mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=3)

        self.mp_drawing.draw_landmarks(
            image=eye_frame,
            landmark_list=face_landmarks,
            connections=self.mp_face_mesh.FACEMESH_LEFT_EYE,
            landmark_drawing_spec=None,
            connection_drawing_spec=red_lines
        )

        self.mp_drawing.draw_landmarks(
            image=eye_frame,
            landmark_list=face_landmarks,
            connections=self.mp_face_mesh.FACEMESH_RIGHT_EYE,
            landmark_drawing_spec=None,
            connection_drawing_spec=red_lines
        )

        h, w = eye_frame.shape[:2]

        cv2.rectangle(eye_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Blink eye tracking"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(eye_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return eye_frame