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
            "is_frozen"
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
            for key in data.keys():
                try:
                    val = float(row.get(key, 0) or 0)
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
            return "Žiadne dáta na analýzu."

        text = f"""DÁTA ZO SLEDOVANIA OSOBY S EPILEPSIOU
=====================================
Dĺžka sledovania: {summary['session_duration_seconds']} sekúnd
Počet záznamov: {summary['total_records']}

PRIEMERNÉ HODNOTY SKÓRE (0-1 škála, vyššie = väčšia abnormalita):
"""
        
        score_keys = ['health_score', 'head_score', 'droop_score', 'eye_score', 'blink_score', 'twitch_score', 'freeze_score']
        for key in score_keys:
            if key in summary['metrics']:
                m = summary['metrics'][key]
                text += f"- {key}: priemer={m['avg']}, max={m['max']}, min={m['min']}\n"

        text += f"""
DETAILY METRÍK:
- Tep srdca (BPM): priemer={summary['metrics'].get('heart_rate', {}).get('avg', 'N/A')}, max={summary['metrics'].get('heart_rate', {}).get('max', 'N/A')}
- Počet žmurknutí: max={summary['metrics'].get('blink_count', {}).get('max', 'N/A')}
- Frekvencia žmurkania: priemer={summary['metrics'].get('blink_rate', {}).get('avg', 'N/A')}/s
- Počet záškubov: max={summary['metrics'].get('twitch_count', {}).get('max', 'N/A')}
- Energia pohybu hlavy: max={summary['metrics'].get('energy', {}).get('max', 'N/A')}

VÝZNAMNÉ UDALOSTI:
- Epizódy zamrznutia tváre: {summary['freeze_episodes']}
- Momenty s vysokým žmurkaním (>0.7): {summary['high_events']['high_blink_moments']}
- Momenty so záškubmi (>0.5): {summary['high_events']['high_twitch_moments']}
- Momenty s trasom hlavy (>0.7): {summary['high_events']['high_shake_moments']}
- Momenty s asymetriou tváre (>0.5): {summary['high_events']['high_droop_moments']}
- Momenty s abnormálnym pohybom očí (>0.5): {summary['high_events']['high_eye_deviation_moments']}
"""
        return text

