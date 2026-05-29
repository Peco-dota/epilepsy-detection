import time
import cv2

class FaceFreeze:
    def __init__(self, mp_face_mesh, mp_drawing, mp_drawing_styles, check_interval=10):
        self.prev_landmarks = []
        self.change_counter = 0
        self.is_ok = True
        self.check_interval = check_interval

        # Time tracking for freeze duration
        self.freeze_start_time = None
        self.is_currently_frozen = False
        self.FREEZE_DURATION_THRESHOLD = 15.0  # 15 seconds

        self.mp_face_mesh = mp_face_mesh
        self.mp_drawing = mp_drawing
        self.mp_drawing_styles = mp_drawing_styles

    def prev_to_curr_changed(self, current_landmarks):
        changed_counter = 0

        for index, landmark in enumerate(current_landmarks):

            if abs(self.prev_landmarks[index]['x'] - landmark['x']) > 0.005:
                changed_counter += 1
            elif abs(self.prev_landmarks[index]['y'] - landmark['y']) > 0.005:
                changed_counter += 1
            elif abs(self.prev_landmarks[index]['z'] - landmark['z']) > 0.005:  
                changed_counter += 1

        return (changed_counter / len(current_landmarks)) > 0.3 
    def moved(self, frame, landmarks, face_landmarks):
        freeze_frame = frame.copy()
        freeze_frame = self.render_face(freeze_frame, face_landmarks)

        if len(self.prev_landmarks) == 0:
            self.prev_landmarks = landmarks
            return freeze_frame

        changed = self.prev_to_curr_changed(landmarks)

        if changed:
            self.change_counter += 1
            self.prev_landmarks = landmarks
            self.freeze_start_time = None
            self.is_currently_frozen = False
        else:
            self.is_currently_frozen = True
            if self.freeze_start_time is None:
                self.freeze_start_time = time.time()

        return freeze_frame

    def check_if_ok(self):
        current_time = time.time()

        if self.change_counter / self.check_interval > 0.2:
            self.is_ok = True
            self.is_currently_frozen = False
            self.freeze_start_time = None  
        else:
            self.is_ok = False
            self.is_currently_frozen = True

            if self.freeze_start_time is None:
                self.freeze_start_time = current_time

        self.counter = 0
        self.change_counter = 0

        return self.is_ok
        
    def get_ok(self):
        return self.is_ok

    def get_freeze_data(self):
        """Returns normalized freeze data for seizure detection"""
        current_time = time.time()

        # Calculate freeze duration
        freeze_duration = 0.0
        if self.freeze_start_time is not None:
            freeze_duration = current_time - self.freeze_start_time

        # Normalize freeze score to 0-1 scale
        # Start scoring after 5 seconds of being frozen
        FREEZE_START_THRESHOLD = 5.0  # Start scoring after 5 seconds

        if freeze_duration < FREEZE_START_THRESHOLD:
            # Not frozen long enough yet
            freeze_score = 0.0
        elif freeze_duration >= self.FREEZE_DURATION_THRESHOLD:
            # Frozen for 15+ seconds = max score
            freeze_score = 1.0
        else:
            # Frozen for 5-15 seconds = proportional score (0.0 to 0.8)
            # Map 5s → 0.0, 15s → 0.8
            freeze_score = min(0.8, (freeze_duration - FREEZE_START_THRESHOLD) / (self.FREEZE_DURATION_THRESHOLD - FREEZE_START_THRESHOLD) * 0.8)

        return {
            'is_frozen': self.is_currently_frozen,
            'freeze_duration': freeze_duration,
            'freeze_score': freeze_score,
            'is_ok': self.is_ok
        }

    def render_face(self, frame, face_landmarks):
        red_lines = self.mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2)

        self.mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=red_lines
            )
        
        h, w = frame.shape[:2]
        data = self.get_freeze_data()

        cv2.rectangle(frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Head twitch tracking"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        sub_text = f"Is frozen: {data['is_frozen']} | Freeze duration: {data['freeze_duration']}"
        sub_text_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        sub_text_x = (w - sub_text_size[0]) // 2
        cv2.putText(frame, sub_text, (sub_text_x, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return frame