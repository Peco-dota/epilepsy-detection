import cv2
import numpy as np
from collections import deque
from scipy.fft import fft, fftfreq


class HealthMonitor:
    def __init__(self, calibration_frames=150):
        self.calibration_frames = calibration_frames
        self.skin_color_history = deque(maxlen=calibration_frames)
        self.baseline_rgb = None
        self.is_calibrated = False

        self.green_values = deque(maxlen=150)  
        self.hr_history = deque(maxlen=3)
        self.fps = 30

        self.heart_rate = 0
        self.paleness = 0.0
        self.redness = 0.0
        self.face_detected = False

    def process_frame(self, frame, face_detection_result=None):
        result = {
            'heart_rate': self.heart_rate,
            'paleness': self.paleness,
            'redness': self.redness,
            'face_detected': False,
            'calibrated': self.is_calibrated,
            'calibration_progress': len(self.skin_color_history) / self.calibration_frames * 100
        }

        if face_detection_result is None or not hasattr(face_detection_result, 'detections') or not face_detection_result.detections:
            self.face_detected = False
            return frame, result

        self.face_detected = True
        result['face_detected'] = True

        face_box = face_detection_result.detections[0].location_data.relative_bounding_box
        face_rgb, cheek_rgb = self._extract_face_regions(frame, face_box)

        # Draw red box around face
        h, w = frame.shape[:2]
        x = max(0, int(face_box.xmin * w))
        y = max(0, int(face_box.ymin * h))
        box_width = min(int(face_box.width * w), w - x)
        box_height = min(int(face_box.height * h), h - y)
        cv2.rectangle(frame, (x, y), (x + box_width, y + box_height), (0, 0, 255), 2)

        if face_rgb is None or cheek_rgb is None:
            return result

        current_rgb = self._get_average_rgb(cheek_rgb)

        if not self.is_calibrated:
            self._update_baseline(current_rgb)
            result['calibration_progress'] = len(self.skin_color_history) / self.calibration_frames * 100
        else:
            self.paleness = self._calculate_paleness(current_rgb)
            self.redness = self._calculate_redness(current_rgb)
            result['paleness'] = self.paleness
            result['redness'] = self.redness

        green_avg = np.mean(cheek_rgb[:, :, 1]) 
        self.green_values.append(green_avg)

        if len(self.green_values) >= 90: 
            hr = self._calculate_heart_rate()
            if hr is not None:
                self.hr_history.append(hr)
                if len(self.hr_history) >= 2:
                    self.heart_rate = int(np.median(self.hr_history))
                else:
                    self.heart_rate = int(hr)
                result['heart_rate'] = self.heart_rate

        return frame, result

    def reset_baseline(self):
        self.baseline_rgb = None
        self.is_calibrated = False
        self.skin_color_history.clear()

    def _extract_face_regions(self, frame, face_box):
        h, w = frame.shape[:2]

        x = max(0, int(face_box.xmin * w))
        y = max(0, int(face_box.ymin * h))
        width = min(int(face_box.width * w), w - x)
        height = min(int(face_box.height * h), h - y)

        face_region = frame[y:y+height, x:x+width]

        cheek_y = int(height * 0.2)
        cheek_h = int(height * 0.4)
        cheek_region = face_region[cheek_y:cheek_y+cheek_h, :]

        if face_region.size == 0 or cheek_region.size == 0:
            return None, None

        return face_region, cheek_region

    def _get_average_rgb(self, region):
        rgb_region = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
        return np.mean(rgb_region, axis=(0, 1))

    def _update_baseline(self, rgb_color):
        self.skin_color_history.append(rgb_color)

        if len(self.skin_color_history) >= self.calibration_frames:
            color_array = np.array(self.skin_color_history)
            self.baseline_rgb = np.mean(color_array, axis=0)
            self.is_calibrated = True

    def _calculate_paleness(self, current_rgb):
        if self.baseline_rgb is None:
            return 0.0

        baseline_brightness = np.sum(self.baseline_rgb)
        current_brightness = np.sum(current_rgb)

        change = ((current_brightness - baseline_brightness) / baseline_brightness) * 100
        return max(0, change)

    def _calculate_redness(self, current_rgb):
        if self.baseline_rgb is None:
            return 0.0

        baseline_red = self.baseline_rgb[0]
        current_red = current_rgb[0]

        red_change = ((current_red - baseline_red) / baseline_red) * 100

        baseline_red_ratio = baseline_red / (self.baseline_rgb[1] + self.baseline_rgb[2] + 1)
        current_red_ratio = current_red / (current_rgb[1] + current_rgb[2] + 1)
        ratio_change = ((current_red_ratio - baseline_red_ratio) / baseline_red_ratio) * 100

        redness = (red_change + ratio_change) / 2
        return max(0, redness)

    def _calculate_heart_rate(self):
        if len(self.green_values) < 90:
            return None

        signal = np.array(self.green_values)
        signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-6)
        signal = signal * np.hamming(len(signal))

        fft_data = fft(signal)
        fft_freqs = fftfreq(len(signal), 1.0 / self.fps)

        positive_freqs = fft_freqs[:len(fft_freqs)//2]
        positive_fft = np.abs(fft_data[:len(fft_data)//2])

        valid_range = (positive_freqs >= 0.833) & (positive_freqs <= 2.5)
        valid_freqs = positive_freqs[valid_range]
        valid_fft = positive_fft[valid_range]

        if len(valid_fft) == 0:
            return None
        
        top_indices = np.argsort(valid_fft)[-3:]
        top_freqs = valid_freqs[top_indices]
        top_powers = valid_fft[top_indices]

        normal_mask = (top_freqs >= 1.0) & (top_freqs <= 2.0)
        if np.any(normal_mask):
            peak_freq = top_freqs[normal_mask][np.argmax(top_powers[normal_mask])]
        else:
            peak_freq = top_freqs[np.argmax(top_powers)]

        return peak_freq * 60

    def process(self, frame, face_landmarks=None):
        new_frame = frame.copy()

        if face_landmarks is None:
            # Fallback to old method if no landmarks provided
            new_frame, result = self.process_frame(frame=new_frame)
        else:
            # Use landmarks to extract face region
            new_frame, result = self.process_with_landmarks(frame=new_frame, face_landmarks=face_landmarks)

        self.rerender_frame(new_frame=new_frame)

        return new_frame, result

    def process_with_landmarks(self, frame, face_landmarks):
        """Process frame using face mesh landmarks"""
        result = {
            'heart_rate': self.heart_rate,
            'paleness': self.paleness,
            'redness': self.redness,
            'face_detected': False,
            'calibrated': self.is_calibrated,
            'calibration_progress': len(self.skin_color_history) / self.calibration_frames * 100
        }

        if face_landmarks is None:
            self.face_detected = False
            return frame, result

        self.face_detected = True
        result['face_detected'] = True

        # Extract face bounding box from landmarks
        h, w = frame.shape[:2]

        # Get min/max x,y from all landmarks
        x_coords = [lm.x for lm in face_landmarks.landmark]
        y_coords = [lm.y for lm in face_landmarks.landmark]

        xmin = max(0, int(min(x_coords) * w))
        ymin = max(0, int(min(y_coords) * h))
        xmax = min(w, int(max(x_coords) * w))
        ymax = min(h, int(max(y_coords) * h))

        width = xmax - xmin
        height = ymax - ymin

        if width <= 0 or height <= 0:
            return frame, result

        # Extract face and cheek regions
        face_region = frame[ymin:ymax, xmin:xmax]

        # Cheek region (middle portion of face)
        cheek_y = int(height * 0.2)
        cheek_h = int(height * 0.4)
        cheek_region = face_region[cheek_y:cheek_y+cheek_h, :]

        if face_region.size == 0 or cheek_region.size == 0:
            return frame, result

        # Draw bounding box
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 0, 255), 2)

        current_rgb = self._get_average_rgb(cheek_region)

        if not self.is_calibrated:
            self._update_baseline(current_rgb)
            result['calibration_progress'] = len(self.skin_color_history) / self.calibration_frames * 100
        else:
            self.paleness = self._calculate_paleness(current_rgb)
            self.redness = self._calculate_redness(current_rgb)
            result['paleness'] = self.paleness
            result['redness'] = self.redness

        green_avg = np.mean(cheek_region[:, :, 1])
        self.green_values.append(green_avg)

        if len(self.green_values) >= 90:
            hr = self._calculate_heart_rate()
            if hr is not None:
                self.hr_history.append(hr)
                if len(self.hr_history) >= 2:
                    self.heart_rate = int(np.median(self.hr_history))
                else:
                    self.heart_rate = int(hr)
                result['heart_rate'] = self.heart_rate

        return frame, result

    def get_normalized_health_data(self):
        """Returns normalized health data for seizure detection"""
        # Normalize BPM (heart rate)
        # Normal: 60-100 BPM, Seizure: 100-180+ BPM
        if self.heart_rate > 100:
            bpm_score = min(1.0, (self.heart_rate - 100) / 80.0)
        else:
            bpm_score = 0.0

        # Normalize color change (paleness or redness)
        # Either extreme paleness or extreme redness indicates distress
        color_change = max(self.paleness, self.redness)
        color_score = min(1.0, color_change / 20.0)  # 20% change = max score

        # Combined health score
        health_score = (bpm_score + color_score) / 2.0

        return {
            'heart_rate': self.heart_rate,
            'paleness': self.paleness,
            'redness': self.redness,
            'bpm_score': bpm_score,
            'color_score': color_score,
            'health_score': health_score,
            'is_calibrated': self.is_calibrated
        }
    
    def rerender_frame(self, new_frame):
        result = self.get_normalized_health_data()
        h, w = new_frame.shape[:2]

        if not result['is_calibrated']:
            cv2.rectangle(new_frame, (0, 0), (w, h), (0, 0, 0), -1)
            calibrating_text = "CALIBRATING..."
            text_size = cv2.getTextSize(calibrating_text, cv2.FONT_HERSHEY_SIMPLEX, 2, 3)[0]
            text_x = (w - text_size[0]) // 2
            text_y = (h + text_size[1]) // 2
            cv2.putText(new_frame, calibrating_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 255), 3)
            return

        cv2.rectangle(new_frame, (0, 0), (w, 100), (0, 0, 0), -1)

        frame_name_text = "Health functions (BPM)"
        text_size = cv2.getTextSize(frame_name_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        cv2.putText(new_frame, frame_name_text, (text_x, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        sub_text = f"Hearth rate: {result['heart_rate']} | Redness: {result['redness']}"
        sub_text_size = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        sub_text_x = (w - sub_text_size[0]) // 2
        cv2.putText(new_frame, sub_text, (sub_text_x, 85), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)