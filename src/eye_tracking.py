import numpy as np
import cv2
from collections import deque
from mediapipe_indexes import LEFT_IRIS, RIGHT_IRIS

class EyeTracking:
    def __init__(self, debug):
        self.debug = debug
        self.eye_position_history = deque(maxlen=30)  # Track last 30 frames
        self.CENTER_X = 0.5  # Normalized center position
        self.CENTER_Y = 0.5
        self.DEVIATION_THRESHOLD = 0.15  # Max normal deviation from center

    def get_eye_center(self, frame, landmarks):
        left_iris = self.get_iris_center(landmarks, LEFT_IRIS)
        right_iris = self.get_iris_center(landmarks, RIGHT_IRIS)
        frame_eye = frame.copy()

        result = {
            'left_iris_x': None,
            'left_iris_y': None,
            'right_iris_x': None,
            'right_iris_y': None
        }

        if left_iris is None or right_iris is None:
            return frame_eye, None

        # Calculate average eye position (between both irises)
        avg_eye_pos = (left_iris + right_iris) / 2.0
        self.eye_position_history.append(avg_eye_pos)

        # Calculate eye deviation from center
        deviation_x = abs(avg_eye_pos[0] - self.CENTER_X)
        deviation_y = abs(avg_eye_pos[1] - self.CENTER_Y)
        total_deviation = np.sqrt(deviation_x**2 + deviation_y**2)

        # Calculate eye movement speed (if we have history)
        movement_speed = 0.0
        if len(self.eye_position_history) > 1:
            recent_movements = []
            for i in range(1, min(10, len(self.eye_position_history))):
                dist = np.linalg.norm(
                    self.eye_position_history[-i] - self.eye_position_history[-i-1]
                )
                recent_movements.append(dist)
            movement_speed = np.mean(recent_movements) if recent_movements else 0.0

        # Normalize values to 0-1 scale
        deviation_normalized = min(1.0, total_deviation / self.DEVIATION_THRESHOLD)
        speed_normalized = min(1.0, movement_speed / 0.02)  # 0.02 = fast eye movement threshold

        # Combined eye score (higher = more abnormal)
        eye_score = (deviation_normalized + speed_normalized) / 2.0

        # Convert normalized coordinates to pixel coordinates for visualization
        h, w = frame_eye.shape[:2]
        left_iris_px = (int(left_iris[0] * w), int(left_iris[1] * h))
        right_iris_px = (int(right_iris[0] * w), int(right_iris[1] * h))

        if self.debug:
            cv2.circle(frame_eye, left_iris_px, 10, (0, 0, 255), -1)
            cv2.circle(frame_eye, right_iris_px, 10, (0, 0, 255), -1)

        eye_data = {
            'deviation': total_deviation,
            'movement_speed': movement_speed,
            'deviation_normalized': deviation_normalized,
            'speed_normalized': speed_normalized,
            'eye_score': eye_score
        }

        frame_eye = self.rerender_frame(frame_eye)

        return frame_eye, eye_data

    def get_iris_center(self, landmarks, iris_indicies):
        if (not landmarks or not landmarks.landmark):
            return None

        x = np.mean([landmarks.landmark[i].x for i in iris_indicies])
        y = np.mean([landmarks.landmark[i].y for i in iris_indicies])
    
        return np.array([x, y])
    
    def rerender_frame(self, new_frame):
        h, w = new_frame.shape[:2]

        cv2.rectangle(new_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Eye tracking"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(new_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return new_frame