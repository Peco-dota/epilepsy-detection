import threading
import time
from collections import deque

import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None


SAMPLE_RATE = 16000
BLOCK_SIZE  = 1024
CHANNELS    = 1

# Module-level defaults — overridden per-instance after calibration
_DEFAULT_THRESHOLD_RMS        = 0.07
_DEFAULT_SILENCE_RMS          = 0.038
_DEFAULT_SILENCE_SECONDS      = 5.0
_DEFAULT_GROAN_PEAK_RMS       = 0.06
_DEFAULT_GROAN_SILENCE_RMS    = 0.005
_DEFAULT_GROAN_DROP_TIMEOUT   = 0.35
_DEFAULT_GROAN_WINDOW_SECONDS = 7.0
_DEFAULT_GROAN_WARNING_LIMIT  = 4


class AudioMonitor:
    def __init__(self, sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE, channels=CHANNELS):
        if sd is None:
            raise RuntimeError("sounddevice is not available")

        self.sample_rate = sample_rate
        self.block_size  = block_size
        self.channels    = channels

        # Calibratable thresholds (start from module defaults, overwritten by calibrate())
        self.threshold_rms        = _DEFAULT_THRESHOLD_RMS
        self.silence_rms          = _DEFAULT_SILENCE_RMS
        self.silence_seconds      = _DEFAULT_SILENCE_SECONDS
        self.groan_peak_rms       = _DEFAULT_GROAN_PEAK_RMS
        self.groan_silence_rms    = _DEFAULT_GROAN_SILENCE_RMS
        self.groan_drop_timeout   = _DEFAULT_GROAN_DROP_TIMEOUT
        self.groan_window_seconds = _DEFAULT_GROAN_WINDOW_SECONDS
        self.groan_warning_limit  = _DEFAULT_GROAN_WARNING_LIMIT

        self._lock  = threading.Lock()
        self._stream = None

        self._was_triggered        = False
        self._trigger_count        = 0
        self._warning_count        = 0
        self._silence_active       = False
        self._drop_time            = None
        self._silence_start_time   = None

        self._groan_peak_time         = None
        self._groan_waiting_for_drop  = False
        self._groan_times             = deque()
        self._groan_warning_active    = False

        self.audio_rms      = 0.0
        self.groan_count    = 0
        self.warning        = 0.0
        self.max_rms_seen   = 0.0
        self.audio_triggered  = False
        self.has_triggered    = False

        # Filled by calibrate()
        self.calibration: dict = {}

    # ── Calibration ───────────────────────────────────────────────────────────

    def calibrate(self, duration: float = 5.0, on_progress=None) -> dict:
        """
        Record ambient noise for `duration` seconds and set detection thresholds
        adaptively relative to the measured baseline.

        on_progress(elapsed, total) is called roughly every 100 ms if provided.
        Returns a dict with calibration stats.
        """
        if sd is None:
            return {}

        samples = []

        def _cb(indata, frames, time_info, status):
            data = indata[:, 0] if indata.ndim > 1 else indata.flatten()
            rms = float(np.sqrt(np.mean(np.square(data)) + 1e-12))
            samples.append(rms)

        stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=self.channels,
            callback=_cb,
        )
        stream.start()
        t0 = time.time()
        while time.time() - t0 < duration:
            elapsed = time.time() - t0
            if on_progress:
                on_progress(elapsed, duration)
            time.sleep(0.08)
        stream.stop()
        stream.close()

        if len(samples) < 5:
            return {}

        arr      = np.array(samples)
        baseline = float(np.median(arr))
        std      = float(np.std(arr))

        # ── Adaptive threshold logic ──────────────────────────────────────────
        # Rule: every threshold is anchored to baseline + N*std so that quiet
        # rooms and noisy rooms both get appropriate sensitivity.
        #
        # Loud trigger — must be well above ambient chatter / breathing
        self.threshold_rms = max(baseline + 5.0 * std, baseline * 3.0, 0.04)

        # Groan peak — above ambient but doesn't need to be as extreme
        self.groan_peak_rms = max(baseline + 3.0 * std, baseline * 2.0, 0.025)

        # Silence after a groan: near-ambient again (person stops vocalising)
        self.groan_silence_rms = max(baseline * 0.7, 0.002)

        # Prolonged silence warning: ambient or quieter for >5s after a sound
        self.silence_rms = max(baseline + 0.5 * std, baseline * 1.2, 0.008)

        stats = {
            'baseline_rms': round(baseline, 5),
            'std':          round(std, 5),
            'n_samples':    len(samples),
            'threshold_rms':     round(self.threshold_rms, 4),
            'groan_peak_rms':    round(self.groan_peak_rms, 4),
            'groan_silence_rms': round(self.groan_silence_rms, 4),
            'silence_rms':       round(self.silence_rms, 4),
        }
        self.calibration = stats
        print(f"🎤 Audio calibrated — baseline {baseline:.4f}  std {std:.4f}")
        print(f"   thresholds → loud:{self.threshold_rms:.3f}  "
              f"groan:{self.groan_peak_rms:.3f}  silence:{self.silence_rms:.3f}")
        return stats

    # ── Stream control ────────────────────────────────────────────────────────

    def start(self):
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=self.channels,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def get_scores(self):
        with self._lock:
            return {
                'audio_rms':         self.audio_rms,
                'audio_groan_count': self.groan_count,
                'audio_warning':     self.warning,
                'audio_max_rms':     self.max_rms_seen,
                'audio_triggered':   self.audio_triggered,
                'audio_has_triggered': self.has_triggered,
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _cleanup_groans(self, current_t):
        while self._groan_times and current_t - self._groan_times[0] > self.groan_window_seconds:
            self._groan_times.popleft()
        self.groan_count = len(self._groan_times)
        if self.groan_count <= self.groan_warning_limit:
            self._groan_warning_active = False

    def _register_groan(self, current_t):
        self._groan_times.append(current_t)
        self._cleanup_groans(current_t)
        if self.groan_count > self.groan_warning_limit and not self._groan_warning_active:
            self._warning_count += 1
            self._groan_warning_active = True

    def _callback(self, indata, frames, time_info, status):
        data = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        current_t = time.time()
        rms = float(np.sqrt(np.mean(np.square(data)) + 1e-12))

        if rms > self.max_rms_seen:
            self.max_rms_seen = rms

        trigger_active = rms >= self.threshold_rms
        self.audio_triggered = trigger_active
        if trigger_active:
            self.has_triggered = True

        if trigger_active:
            self._silence_active     = True
            self._drop_time          = None
            self._silence_start_time = None
            if not self._was_triggered:
                self._trigger_count += 1
        self._was_triggered = trigger_active

        if self._silence_active and not trigger_active:
            if self._drop_time is None:
                if rms < self.silence_rms:
                    self._drop_time = current_t
            else:
                if rms >= self.silence_rms:
                    self._silence_active     = False
                    self._drop_time          = None
                    self._silence_start_time = None
                else:
                    if current_t - self._drop_time < 1.0:
                        self._silence_start_time = None
                    else:
                        if self._silence_start_time is None:
                            self._silence_start_time = current_t
                        elif current_t - self._silence_start_time >= self.silence_seconds:
                            self._warning_count      += 1
                            self._silence_active     = False
                            self._drop_time          = None
                            self._silence_start_time = None

        if not self._groan_waiting_for_drop:
            if rms >= self.groan_peak_rms:
                self._groan_waiting_for_drop = True
                self._groan_peak_time        = current_t
        else:
            if rms <= self.groan_silence_rms:
                if current_t - self._groan_peak_time <= self.groan_drop_timeout:
                    self._register_groan(current_t)
                self._groan_waiting_for_drop = False
                self._groan_peak_time        = None
            elif current_t - self._groan_peak_time > self.groan_drop_timeout:
                if rms >= self.groan_peak_rms:
                    self._groan_peak_time = current_t
                else:
                    self._groan_waiting_for_drop = False
                    self._groan_peak_time        = None

        self._cleanup_groans(current_t)

        with self._lock:
            self.audio_rms       = rms
            self.groan_count     = len(self._groan_times)
            self.warning         = float(self._warning_count)
            self.audio_triggered = trigger_active
