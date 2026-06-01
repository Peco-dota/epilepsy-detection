import numpy as np
from collections import deque
import time
import math
import cv2

class TwitchDetector:
    def __init__(self, debug):
        self.debug = debug

        self.NOSE_IDX = 1
        
        self.TRACKED_POINTS = {
            'Head (Pos)':    {'idx': 1, 'type': 'position', 'thresh': 0.015},     # Increased from 0.015
            'R-Cheek':       {'idx': 205, 'type': 'cheek_dist', 'thresh': 0.003}, # Increased from 0.003
            'L-Cheek':       {'idx': 425, 'type': 'cheek_dist', 'thresh': 0.003}, # Increased from 0.003
            'Rotation':      {'top': 10, 'bottom': 152, 'type': 'rotation', 'thresh': 2.0}  # Increased from 1.8
        }

        self.alpha = 0.85
        self.smoothed_values = {}

        self.twitch_window = 5
        self.twitch_count_threshold = 5  # Increased from 3 - need 5 twitches in 5s instead of 3
        self.cooldown_time = 1.5          # Increased from 1.0 - longer cooldown between detections        
        
        self.last_twitch_time = {name: 0 for name in self.TRACKED_POINTS}
        self.twitch_history = deque()

    def calculate_tilt(self, p1, p2, w, h):
        dx = (p1.x - p2.x) * w
        dy = (p1.y - p2.y) * h
        angle_rad = math.atan2(dy, dx)
        return math.degrees(angle_rad)

    def detect(self, frame, face_landmarks):
        h, w = frame.shape[:2]
        frame_twitch = frame.copy()
        
        current_time = time.time()
    
        nose_lm = face_landmarks.landmark[self.NOSE_IDX]
        nose_pos = np.array([nose_lm.x, nose_lm.y])

        for name, data in self.TRACKED_POINTS.items():
            
            if data['type'] == 'rotation':
                p_top = face_landmarks.landmark[data['top']]
                p_btm = face_landmarks.landmark[data['bottom']]
                current_val = self.calculate_tilt(p_top, p_btm, w, h)

                # Visualization
                if self.debug:
                    cv2.line(frame_twitch, (int(p_top.x*w), int(p_top.y*h)), (int(p_btm.x*w), int(p_btm.y*h)), (0, 255, 255), 2)
                
            elif data['type'] == 'position':
                lm = face_landmarks.landmark[data['idx']]
                current_val = np.array([lm.x, lm.y])
                
            elif data['type'] == 'cheek_dist':
                lm = face_landmarks.landmark[data['idx']]
                pos = np.array([lm.x, lm.y])
                current_val = np.linalg.norm(pos - nose_pos)

            if name not in self.smoothed_values:
                self.smoothed_values[name] = current_val
                continue
            
            self.smoothed_values[name] = (self.alpha * current_val) + \
                                            ((1 - self.alpha) * self.smoothed_values[name])

            if data['type'] == 'rotation':
                jitter = abs(current_val - self.smoothed_values[name])
            else:
                jitter = np.linalg.norm(current_val - self.smoothed_values[name])

            if current_time - self.last_twitch_time[name] < self.cooldown_time:
                self.smoothed_values[name] = current_val 
                continue

            # --- 4. Twitch Detection ---
            if jitter > data['thresh']:
                # REGISTER TWITCH
                self.twitch_history.append(current_time)
                self.last_twitch_time[name] = current_time 
                
                self.smoothed_values[name] = current_val 
                
                if self.debug:
                    if data['type'] == 'rotation':
                        cv2.putText(frame_twitch, "ROTATION!", (50, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    elif 'idx' in data:
                        lm = face_landmarks.landmark[data['idx']]
                        cx, cy = int(lm.x*w), int(lm.y*h)
                        cv2.circle(frame_twitch, (cx, cy), 15, (0, 0, 255), 3)

        while self.twitch_history and current_time - self.twitch_history[0] > self.twitch_window:
            self.twitch_history.popleft()

        count = len(self.twitch_history)

        # Normalize twitch score to 0-1 scale
        # If count >= threshold, set to 1.0, otherwise proportional
        if count >= self.twitch_count_threshold:
            twitch_score = 1.0
        else:
            # Proportional score below threshold (0-0.8 range)
            twitch_score = min(0.8, count / self.twitch_count_threshold)

        twitch_data = {
            'twitch_count': count,
            'is_twitching': count >= self.twitch_count_threshold,
            'twitch_score': twitch_score
        }

        frame_twitch = self.rerender_frame(new_frame=frame_twitch, twitch_data=twitch_data)

        return frame_twitch, twitch_data
    
    def rerender_frame(self, new_frame, twitch_data):
        h, w = new_frame.shape[:2]

        cv2.rectangle(new_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Head twitch tracking"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(new_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        sub_text = f"Head twitch count: {twitch_data['twitch_count']} | Is twitching: {twitch_data['is_twitching']}"
        sub_text_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        sub_text_x = (w - sub_text_size[0]) // 2
        cv2.putText(new_frame, sub_text, (sub_text_x, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        return new_frame