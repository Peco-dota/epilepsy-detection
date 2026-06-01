import cv2
import mediapipe as mp
import numpy as np
from collections import deque
import time
import math

class SeizureDetector:
    def __init__(self):
        self.NOSE_IDX = 1
        self.movement_history = deque(maxlen=20)  # Medium window for quick movements
        self.MIN_ENERGY = 0.8      # Moderate threshold - balanced sensitivity
        self.MIN_FLIPS = 5         # Moderate flips - quick back-and-forth motion        

        self.TRACKED_POINTS = {
            'Hlava':    {'idx': 1, 'type': 'position', 'thresh': 0.5},
            'Rotacia':  {'top': 10, 'bottom': 152, 'type': 'rotation', 'thresh': 5.0}
        }
        self.alpha = 0.85 
        self.smoothed_values = {} 
        self.twitch_history = deque()
        self.twitch_window = 15.0
        self.cooldown_time = 0.3
        self.last_twitch_time = {name: 0 for name in self.TRACKED_POINTS}

    def calculate_tilt(self, p1, p2, w, h):
        dx = (p1.x - p2.x) * w
        dy = (p1.y - p2.y) * h
        return math.degrees(math.atan2(dy, dx))

    def detect(self, frame, face_landmarks):
        new_frame = frame.copy()
        h, w = new_frame.shape[:2]
        current_time = time.time()
        
        is_shaking_violently = False
        
        nose_lm = face_landmarks.landmark[self.NOSE_IDX]
        nose_pos = np.array([nose_lm.x, nose_lm.y])

        self.movement_history.append(nose_pos)

        current_energy = 0
        direction_flips = 0

        if len(self.movement_history) > 10:
            for i in range(1, len(self.movement_history)):
                dist = np.linalg.norm(self.movement_history[i] - self.movement_history[i-1])
                current_energy += dist
            
            deltas_x = []
            for i in range(1, len(self.movement_history)):
                dx = self.movement_history[i][0] - self.movement_history[i-1][0]
                # Threshold for quick movements - not too high, not too low
                if abs(dx) > 0.005:
                    deltas_x.append(dx)

            # Count actual direction changes (sign flips) for seizure-like motion
            for i in range(1, len(deltas_x)):
                if deltas_x[i] * deltas_x[i-1] < 0:  # Sign change = direction flip
                    direction_flips += 1

            if current_energy > self.MIN_ENERGY and direction_flips >= self.MIN_FLIPS:
                is_shaking_violently = True

            cv2.putText(new_frame, f"Energia: {current_energy:.2f} (Min: {self.MIN_ENERGY})", (20, h-60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
            cv2.putText(new_frame, f"Kmity: {direction_flips} (Min: {self.MIN_FLIPS})", (20, h-40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

        if not is_shaking_violently:
            for name, data in self.TRACKED_POINTS.items():
                if current_time - self.last_twitch_time[name] < self.cooldown_time:
                    continue 

                if data['type'] == 'rotation':
                    p_top = face_landmarks.landmark[data['top']]
                    p_btm = face_landmarks.landmark[data['bottom']]
                    current_val = self.calculate_tilt(p_top, p_btm, w, h)
                elif data['type'] == 'position':
                    current_val = nose_pos

                if name not in self.smoothed_values:
                    self.smoothed_values[name] = current_val
                    continue

                self.smoothed_values[name] = (self.alpha * current_val) + ((1 - self.alpha) * self.smoothed_values[name])

                if data['type'] == 'rotation':
                    jitter = abs(current_val - self.smoothed_values[name])
                else:
                    jitter = np.linalg.norm(current_val - self.smoothed_values[name])

                if jitter > data['thresh']:
                    self.twitch_history.append(current_time)
                    self.last_twitch_time[name] = current_time
                    self.smoothed_values[name] = current_val 
                    
                    if data['type'] == 'rotation':
                        cv2.putText(new_frame, "CUKNUTIE (ROTACIA)", (50, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    else:
                        cv2.circle(new_frame, (int(nose_pos[0]*w), int(nose_pos[1]*h)), 10, (0, 0, 255), 2)

        while self.twitch_history and current_time - self.twitch_history[0] > self.twitch_window:
            self.twitch_history.popleft()
        
        # Normalize values to 0-1 scale
        # If violently shaking, set to 1.0, otherwise calculate proportional score
        if is_shaking_violently:
            head_score = 1.0
        else:
            # Proportional score below threshold (0-0.8 range)
            energy_normalized = min(0.8, current_energy / self.MIN_ENERGY)
            flips_normalized = min(0.8, direction_flips / self.MIN_FLIPS)
            head_score = (energy_normalized + flips_normalized) / 2.0

        # Return frame and calculated values
        seizure_data = {
            'energy': current_energy,
            'direction_flips': direction_flips,
            'is_shaking_violently': is_shaking_violently,
            'twitch_count': len(self.twitch_history),
            'head_score': head_score
        }

        new_frame = self.rerender_frame(new_frame=new_frame, seizure_data=seizure_data)

        return new_frame, seizure_data
    
    def rerender_frame(self, new_frame, seizure_data):
        h, w = new_frame.shape[:2]

        cv2.rectangle(new_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Shake detection"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(new_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        sub_text = f"Direction flips count: {seizure_data['direction_flips']} | is shaking violently: {seizure_data['is_shaking_violently']}"
        sub_text_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        sub_text_x = (w - sub_text_size[0]) // 2
        cv2.putText(new_frame, sub_text, (sub_text_x, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        return new_frame