import threading
import time
from collections import deque

import numpy as np

try:
	import sounddevice as sd
except Exception:
	sd = None


SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
CHANNELS = 1

THRESHOLD_RMS = 0.07

SILENCE_RMS_THRESHOLD = 0.038
SILENCE_SECONDS = 5.0

GROAN_PEAK_RMS = 0.06
GROAN_SILENCE_RMS = 0.005
GROAN_DROP_TIMEOUT = 0.35

GROAN_WINDOW_SECONDS = 7.0
GROAN_WARNING_LIMIT = 4


class AudioMonitor:
	def __init__(self, sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE, channels=CHANNELS):
		if sd is None:
			raise RuntimeError("sounddevice is not available")

		self.sample_rate = sample_rate
		self.block_size = block_size
		self.channels = channels

		self._lock = threading.Lock()
		self._stream = None

		self._was_triggered = False
		self._trigger_count = 0
		self._warning_count = 0
		self._silence_active = False
		self._drop_time = None
		self._silence_start_time = None

		self._groan_peak_time = None
		self._groan_waiting_for_drop = False
		self._groan_times = deque()
		self._groan_warning_active = False

		self.audio_rms = 0.0
		self.groan_count = 0
		self.warning = 0.0
		self.max_rms_seen = 0.0

		self.audio_triggered = False
		self.has_triggered = False

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
				'audio_rms': self.audio_rms,
				'audio_groan_count': self.groan_count,
				'audio_warning': self.warning,
				'audio_max_rms': self.max_rms_seen,
				'audio_triggered': self.audio_triggered,
				'audio_has_triggered': self.has_triggered,
			}

	def _cleanup_groans(self, current_t):
		while self._groan_times and current_t - self._groan_times[0] > GROAN_WINDOW_SECONDS:
			self._groan_times.popleft()

		self.groan_count = len(self._groan_times)

		if self.groan_count <= GROAN_WARNING_LIMIT:
			self._groan_warning_active = False

	def _register_groan(self, current_t):
		self._groan_times.append(current_t)
		self._cleanup_groans(current_t)

		if self.groan_count > GROAN_WARNING_LIMIT and not self._groan_warning_active:
			self._warning_count += 1
			self._groan_warning_active = True

	def _callback(self, indata, frames, time_info, status):
		data = indata
		if data.ndim > 1:
			data = data[:, 0]

		current_t = time.time()
		rms = float(np.sqrt(np.mean(np.square(data)) + 1e-12))

		if rms > self.max_rms_seen:
			self.max_rms_seen = rms

		trigger_active = rms >= THRESHOLD_RMS

		self.audio_triggered = trigger_active
		if trigger_active:
			self.has_triggered = True

		if trigger_active:
			self._silence_active = True
			self._drop_time = None
			self._silence_start_time = None

			if not self._was_triggered:
				self._trigger_count += 1

		self._was_triggered = trigger_active

		if self._silence_active and not trigger_active:
			if self._drop_time is None:
				if rms < SILENCE_RMS_THRESHOLD:
					self._drop_time = current_t
			else:
				if rms >= SILENCE_RMS_THRESHOLD:
					self._silence_active = False
					self._drop_time = None
					self._silence_start_time = None
				else:
					if current_t - self._drop_time < 1.0:
						self._silence_start_time = None
					else:
						if self._silence_start_time is None:
							self._silence_start_time = current_t
						elif current_t - self._silence_start_time >= SILENCE_SECONDS:
							self._warning_count += 1
							self._silence_active = False
							self._drop_time = None
							self._silence_start_time = None

		if not self._groan_waiting_for_drop:
			if rms >= GROAN_PEAK_RMS:
				self._groan_waiting_for_drop = True
				self._groan_peak_time = current_t
		else:
			if rms <= GROAN_SILENCE_RMS:
				if current_t - self._groan_peak_time <= GROAN_DROP_TIMEOUT:
					self._register_groan(current_t)

				self._groan_waiting_for_drop = False
				self._groan_peak_time = None

			elif current_t - self._groan_peak_time > GROAN_DROP_TIMEOUT:
				if rms >= GROAN_PEAK_RMS:
					self._groan_peak_time = current_t
				else:
					self._groan_waiting_for_drop = False
					self._groan_peak_time = None

		self._cleanup_groans(current_t)

		with self._lock:
			self.audio_rms = rms
			self.groan_count = len(self._groan_times)
			self.warning = float(self._warning_count)
			self.audio_triggered = trigger_active