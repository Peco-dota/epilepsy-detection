import csv
import time
from datetime import datetime
import os
import statistics

class CSVLogger:
    def __init__(self, output_dir="logs", log_interval=1.0):
        self.log_interval = log_interval
        self.last_log_time = 0
        
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(output_dir, f"session_{timestamp}.csv")
        
        self.headers = [
            "timestamp",
            "frame_index",
            "health_score",
            "heart_rate",
            "color_score",
            "is_calibrated",
            "head_score",
            "energy",
            "direction_flips",
            "droop_score",
            "droop_duration",
            "eye_score",
            "eye_deviation",
            "eye_movement_speed",
            "blink_score",
            "blink_count",
            "blink_rate",
            "twitch_score",
            "twitch_count",
            "freeze_score",
            "freeze_duration",
            "is_frozen",
            "audio_rms",
            "audio_groan_count",
            "audio_warning",
            "audio_triggered",
            "audio_has_triggered",
            "pre_ictal_score",
            "pre_ictal_stage"
        ]
        
        self.file = open(self.filepath, mode='w', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=self.headers)
        self.writer.writeheader()
        self.file.flush()

    def should_log(self):
        current_time = time.time()
        if current_time - self.last_log_time >= self.log_interval:
            self.last_log_time = current_time
            return True
        return False

    def log_row(self, data):
        row = {header: data.get(header, "") for header in self.headers}
        row["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        if self.file:
            self.file.close()
            self.file = None

    def get_filepath(self):
        return self.filepath

    def generate_summary(self):
        if not os.path.exists(self.filepath):
            return None

        data = {header: [] for header in self.headers if header not in ['timestamp', 'frame_index', 'is_calibrated', 'is_frozen']}
        
        with open(self.filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        if not rows:
            return None

        for row in rows:
            is_calibrated = row.get('is_calibrated', '').lower() == 'true'
            for key in data.keys():
                try:
                    val = float(row.get(key, 0) or 0)
                    # skip heart_rate and health_score rows from uncalibrated frames
                    if key in ('heart_rate', 'health_score') and not is_calibrated:
                        continue
                    # skip zero heart_rate readings (uncalibrated or missing)
                    if key == 'heart_rate' and val == 0:
                        continue
                    data[key].append(val)
                except (ValueError, TypeError):
                    pass

        summary = {
            'session_duration_seconds': len(rows),
            'total_records': len(rows),
            'metrics': {}
        }

        for key, values in data.items():
            if values:
                summary['metrics'][key] = {
                    'avg': round(statistics.mean(values), 3),
                    'max': round(max(values), 3),
                    'min': round(min(values), 3),
                }
                if len(values) > 1:
                    summary['metrics'][key]['std'] = round(statistics.stdev(values), 3)

        freeze_count = sum(1 for row in rows if row.get('is_frozen', '').lower() == 'true')
        summary['freeze_episodes'] = freeze_count
        
        high_events = {
            'high_blink_moments': sum(1 for row in rows if float(row.get('blink_score', 0) or 0) > 0.7),
            'high_twitch_moments': sum(1 for row in rows if float(row.get('twitch_score', 0) or 0) > 0.5),
            'high_shake_moments': sum(1 for row in rows if float(row.get('head_score', 0) or 0) > 0.7),
            'high_droop_moments': sum(1 for row in rows if float(row.get('droop_score', 0) or 0) > 0.5),
            'high_eye_deviation_moments': sum(1 for row in rows if float(row.get('eye_score', 0) or 0) > 0.5),
        }
        summary['high_events'] = high_events

        return summary

    def get_summary_for_llm(self):
        summary = self.generate_summary()
        if not summary:
            return "No data to analyze."

        duration = summary['session_duration_seconds']
        total = summary['total_records']

        def pct(count):
            return f"{round(count / total * 100)}%" if total > 0 else "N/A"

        score_keys = [
            'head_score', 'droop_score', 'eye_score', 'blink_score', 'twitch_score', 'freeze_score',
            'audio_rms', 'audio_groan_count', 'audio_warning', 'audio_triggered', 'audio_has_triggered'
        ]
        scores_text = ""
        for key in score_keys:
            if key in summary['metrics']:
                m = summary['metrics'][key]
                scores_text += f"- {key}: avg={m['avg']} max={m['max']}\n"

        hr = summary['metrics'].get('heart_rate', {})
        hr_text = (
            f"avg={hr.get('avg', 'N/A')} BPM, max={hr.get('max', 'N/A')} BPM"
            if hr else "not available (session too short to calibrate)"
        )

        he = summary['high_events']
        text = f"""EPILEPSY MONITORING SESSION DATA
=====================================
Session duration: {duration} seconds ({total} logged records)

CONTEXT FOR INTERPRETATION:
- Scores are on a 0.0-1.0 scale. Values below 0.3 are generally normal.
- "High moments" counts are out of {total} total records ({duration} seconds).
- Face freeze is triggered whenever the face is still — normal during calm sitting.
- Eye score can be elevated during normal reading or looking around.
- A count of high moments should be read as a percentage of the session, not as isolated alarming events.

SCORES (avg and max over session):
{scores_text}
HEART RATE (calibrated frames only):
- {hr_text}

HIGH-SCORE MOMENTS (% of session):
- High blink (>0.7): {he['high_blink_moments']} records = {pct(he['high_blink_moments'])} of session
- Twitching (>0.5): {he['high_twitch_moments']} records = {pct(he['high_twitch_moments'])} of session
- Head shake (>0.7): {he['high_shake_moments']} records = {pct(he['high_shake_moments'])} of session
- Face asymmetry (>0.5): {he['high_droop_moments']} records = {pct(he['high_droop_moments'])} of session
- Eye movement (>0.5): {he['high_eye_deviation_moments']} records = {pct(he['high_eye_deviation_moments'])} of session
- Face frozen: {summary['freeze_episodes']} records = {pct(summary['freeze_episodes'])} of session
"""
        return text

