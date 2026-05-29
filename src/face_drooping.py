import cv2
import mediapipe as mp
import numpy as np
import math
import time
from collections import deque


class FaceMeshViewer:
    LEFT_MOUTH_CORNER = 61
    RIGHT_MOUTH_CORNER = 291

    LEFT_EYE_OUTER = 33
    RIGHT_EYE_OUTER = 263

    def __init__(self, twitch_window=5.0):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.mouth_delta_history = []
        self.HISTORY_LEN = 10
        self.DROOP_THRESHOLD = 0.01  # ~1 % vysky tvare
        self.droop_side_candidate = None 
        self.droop_start_time = None
        self.DROOP_DURATION = 7.0
        self.TWITCH_MIN_DURATION = 0.15
        self.TWITCH_MAX_DURATION = 1.0
        self.TWITCH_DISPLAY_TIME = 1.0

        self.last_twitch_time = None
        self.last_twitch_side = None
        self.last_twitch_duration = 0.0

        self.twitch_history = deque()
        self.twitch_window = twitch_window

    def _add_to_history(self, value, buffer, max_len=None):
        if max_len is None:
            max_len = self.HISTORY_LEN
        buffer.append(value)
        if len(buffer) > max_len:
            buffer.pop(0)
        return float(np.mean(buffer))

    def _get_landmark_xy(self, landmark, frame_shape):
        h, w, _ = frame_shape
        return int(landmark.x * w), int(landmark.y * h)

    def _rotate_point_norm(self, x, y, cx, cy, angle_rad):
        x0 = x - cx
        y0 = y - cy

        cos_a = math.cos(-angle_rad)
        sin_a = math.sin(-angle_rad)

        xr = x0 * cos_a - y0 * sin_a
        yr = x0 * sin_a + y0 * cos_a

        return xr + cx, yr + cy

    def process_frame(self, frame, face_landmarks):
        new_frame = frame.copy()
        """
        Hlavná funkcia:
        - vstup: frame (BGR), face_landmarks (NormalizedLandmarkList alebo None)
        - výstup: frame_droop, isDroop (bool), count (počet twitchov v okne)
        """
        status = "ŽIADNA TVÁR"
        color = (0, 255, 255)
        now = time.time()
        is_droop = False

        if face_landmarks is not None:
            self.mp_drawing.draw_landmarks(
                image=new_frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_drawing_styles
                    .get_default_face_mesh_tesselation_style()
            )

            self.mp_drawing.draw_landmarks(
                image=new_frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_drawing_styles
                    .get_default_face_mesh_contours_style()
            )

            lm = face_landmarks.landmark

            left_eye = lm[self.LEFT_EYE_OUTER]
            right_eye = lm[self.RIGHT_EYE_OUTER]

            eye_angle = math.atan2(
                right_eye.y - left_eye.y,
                right_eye.x - left_eye.x
            )

            cx = (left_eye.x + right_eye.x) / 2.0
            cy = (left_eye.y + right_eye.y) / 2.0

            left_mouth = lm[self.LEFT_MOUTH_CORNER]
            right_mouth = lm[self.RIGHT_MOUTH_CORNER]

            lx_rot, ly_rot = self._rotate_point_norm(
                left_mouth.x, left_mouth.y, cx, cy, eye_angle
            )
            rx_rot, ry_rot = self._rotate_point_norm(
                right_mouth.x, right_mouth.y, cx, cy, eye_angle
            )

            delta_y = ly_rot - ry_rot
            smooth_delta = self._add_to_history(delta_y, self.mouth_delta_history)

            side_candidate = None
            if smooth_delta > self.DROOP_THRESHOLD:
                side_candidate = "LEFT"
            elif smooth_delta < -self.DROOP_THRESHOLD:
                side_candidate = "RIGHT"

            # LOGIKA DROOP vs TWITCH
            if side_candidate is None:
                if self.droop_side_candidate is not None and self.droop_start_time is not None:
                    duration = now - self.droop_start_time

                    # twitch len ak trval v tomto intervale
                    if (self.TWITCH_MIN_DURATION
                            <= duration
                            <= self.TWITCH_MAX_DURATION):
                        self.last_twitch_time = now
                        self.last_twitch_side = self.droop_side_candidate
                        self.last_twitch_duration = duration

                        self.twitch_history.append(now)

                    # ak > TWITCH_MAX_DURATION a < DROOP_DURATION → ignorujeme (nič)

                self.droop_side_candidate = None
                self.droop_start_time = None

                if self.last_twitch_time is not None and (now - self.last_twitch_time) <= self.TWITCH_DISPLAY_TIME:
                    side_text = "ĽAVÁ STRANA" if self.last_twitch_side == "LEFT" else "PRAVÁ STRANA"
                    status = f"TWITCH: {side_text} ({self.last_twitch_duration:.2f}s)"
                    color = (0, 255, 255)
                else:
                    status = "SYMETRIA OK"
                    color = (0, 255, 0)
                    is_droop = False

            else:
                # bežiaca asymetria
                if self.droop_side_candidate != side_candidate:
                    self.droop_side_candidate = side_candidate
                    self.droop_start_time = now

                elapsed = 0.0
                if self.droop_start_time is not None:
                    elapsed = now - self.droop_start_time

                side_text = "ĽAVÁ STRANA" if side_candidate == "LEFT" else "PRAVÁ STRANA"

                if elapsed >= self.DROOP_DURATION:
                    status = f"DROOP: {side_text} (≥ {self.DROOP_DURATION:.0f}s)"
                    color = (0, 0, 255)
                    is_droop = True
                else:
                    # len info, že beží asymetria, ale finálne rozhodnutie padne až keď skončí
                    status = f"SLEDUJEM MOŽNÝ DROOP: {side_text} ({elapsed:.1f}/{self.DROOP_DURATION:.0f}s)"
                    color = (0, 255, 255)
                    is_droop = False

            h, w, _ = new_frame.shape
            lx, ly = self._get_landmark_xy(left_mouth, new_frame.shape)
            rx, ry = self._get_landmark_xy(right_mouth, new_frame.shape)
            cv2.circle(new_frame, (lx, ly), 3, (255, 0, 0), -1)
            cv2.circle(new_frame, (rx, ry), 3, (255, 0, 0), -1)
            cv2.line(new_frame, (lx, ly), (rx, ry), (255, 0, 0), 1)

            cv2.putText(
                new_frame,
                f"{status}   delta={smooth_delta:+.3f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA
            )

        while self.twitch_history and (now - self.twitch_history[0]) > self.twitch_window:
            self.twitch_history.popleft()

        count = len(self.twitch_history)

        # Calculate droop duration for normalization
        droop_duration = 0.0
        if self.droop_start_time is not None:
            droop_duration = now - self.droop_start_time

        # Normalize droop score to 0-1 scale
        # If duration >= DROOP_DURATION, set to 1.0, otherwise proportional
        if droop_duration >= self.DROOP_DURATION:
            droop_score = 1.0
        else:
            # Proportional score below threshold (0-0.8 range)
            droop_score = min(0.8, droop_duration / self.DROOP_DURATION)

        droop_data = {
            'is_droop': is_droop,
            'droop_duration': droop_duration,
            'droop_side': self.droop_side_candidate,
            'droop_score': droop_score,
            'twitch_count': count
        }

        new_frame = self.rerender_frame(new_frame=new_frame, droop_data=droop_data)

        # new_frame_droop, droop_data
        return new_frame, droop_data

    def rerender_frame(self, new_frame, droop_data):
        h, w = new_frame.shape[:2]

        cv2.rectangle(new_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Droop detection"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(new_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        sub_text = f"Is droop: {droop_data['is_droop']} | Face twitch count: {droop_data['twitch_count']}"
        sub_text_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        sub_text_x = (w - sub_text_size[0]) // 2
        cv2.putText(new_frame, sub_text, (sub_text_x, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        return new_frame