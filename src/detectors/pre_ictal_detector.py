"""
Pre-ictal pattern detector.

Scientific basis:
  - Pre-ictal state is characterised by gradual multi-signal escalation, not a
    single threshold crossing (Mormann et al., 2007; Kuhlmann et al., 2018).
  - Signals are processed with exponentially weighted moving averages (EWMA)
    to give recency bias while smoothing noise — standard in biosignal processing.
  - Trend (slope) is estimated via online linear regression over a sliding window.
    A rising trend across multiple signals simultaneously is more diagnostic than
    any single elevated value.
  - Stages follow the clinical pre-ictal progression:
      0  Baseline    — all signals quiet
      1  Prodromal   — early autonomic / attention shift (freeze, blink change)
      2  Pre-ictal   — motor + autonomic co-activation (eye deviation + asymmetry)
      3  Imminent    — multi-signal convergence with positive trends
  - Stage transitions only advance; they reset slowly (hysteresis) to avoid
    flickering from momentary dips.
  - Final score combines stage level + weighted trend magnitude + signal
    co-activation count, all normalised to [0, 1].
"""

import time
import math
from collections import deque


# ── Tunable constants ──────────────────────────────────────────────────────────

WINDOW_SECONDS   = 30      # history length for trend analysis
EWMA_ALPHA       = 0.15    # EWMA smoothing factor (lower = smoother, slower)
TREND_WINDOW     = 15      # seconds of data used for slope estimation
STAGE_HOLD       = 5.0     # seconds a stage must be sustained before advancing
STAGE_DECAY      = 8.0     # seconds before stage drops back one level if unsupported

# Per-signal thresholds that indicate "elevated" for stage scoring
# Tuned conservatively — we want warning, not false alarms
SIGNAL_THRESHOLDS = {
    'freeze':  0.25,   # face stillness (absence-like)
    'blink':   0.30,   # abnormal blinking
    'eye':     0.30,   # eye deviation
    'asym':    0.20,   # facial asymmetry
    'twitch':  0.25,   # myoclonic twitching
    'shake':   0.25,   # head tremor
    'bpm':     0.20,   # heart rate change
    'color':   0.15,   # skin color change
}

# Stage definitions: which signals must be elevated, and how many minimum
STAGE_RULES = {
    # Stage 1 — prodromal: autonomic shift or attention change
    1: {
        'required_any': ['freeze', 'blink', 'eye'],
        'min_signals': 1,
        'score_threshold': 0.20,
    },
    # Stage 2 — pre-ictal: motor signs joining autonomic
    2: {
        'required_any': ['eye', 'asym', 'twitch', 'shake'],
        'min_signals': 2,
        'score_threshold': 0.40,
    },
    # Stage 3 — imminent: broad multi-signal convergence with rising trends
    3: {
        'required_any': ['freeze', 'blink', 'eye', 'asym', 'twitch', 'shake'],
        'min_signals': 3,
        'score_threshold': 0.60,
        'requires_trend': True,   # at least 2 signals must have positive slope
    },
}


class _SignalTracker:
    """
    Tracks one signal over time with:
      - EWMA smoothed value
      - timestamped history for slope estimation
      - normalised 'elevation' (0-1) above its threshold
    """

    def __init__(self, name, threshold, alpha=EWMA_ALPHA, window=WINDOW_SECONDS):
        self.name = name
        self.threshold = threshold
        self.alpha = alpha
        self.window = window
        self.ewma = 0.0
        self.history = deque()   # (timestamp, raw_value)

    def update(self, value, t=None):
        if t is None:
            t = time.time()
        # EWMA update
        self.ewma = self.alpha * value + (1 - self.alpha) * self.ewma
        self.history.append((t, value))
        # prune old entries
        cutoff = t - self.window
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()

    @property
    def elevation(self):
        """How far above threshold the EWMA is, normalised 0-1."""
        if self.threshold == 0:
            return 0.0
        return max(0.0, min(1.0, self.ewma / self.threshold - 1.0))

    @property
    def is_elevated(self):
        return self.ewma >= self.threshold

    def slope(self, window_seconds=TREND_WINDOW):
        """
        Linear regression slope over the last `window_seconds`.
        Returns normalised slope: positive = rising, negative = falling.
        Uses Welford-style online approach for numerical stability.
        """
        t_now = time.time()
        cutoff = t_now - window_seconds
        pts = [(t, v) for t, v in self.history if t >= cutoff]
        n = len(pts)
        if n < 4:
            return 0.0

        # centre timestamps to improve numerical stability
        t0 = pts[0][0]
        xs = [t - t0 for t, _ in pts]
        ys = [v for _, v in pts]

        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        if den == 0:
            return 0.0

        raw_slope = num / den   # units: signal/second
        # normalise by threshold so all signals are comparable
        return raw_slope / max(self.threshold, 0.01)


class PreIctalDetector:
    """
    Detects pre-ictal escalation patterns across multiple biosignals.

    Usage:
        detector = PreIctalDetector()
        # each frame:
        result = detector.update(shake=0.1, blink=0.3, eye=0.4, ...)
        print(result['pre_ictal_score'], result['stage'], result['warning'])
    """

    def __init__(self):
        self.trackers = {
            name: _SignalTracker(name, thr)
            for name, thr in SIGNAL_THRESHOLDS.items()
        }
        self.current_stage = 0
        self._stage_entry_time = None   # when current stage was entered
        self._stage_last_supported = time.time()
        self.pre_ictal_score = 0.0
        self.history = deque(maxlen=int(WINDOW_SECONDS * 30))  # ~30fps buffer

    def update(self, shake=0.0, blink=0.0, eye=0.0, freeze=0.0,
               asym=0.0, twitch=0.0, bpm=0.0, color=0.0):
        t = time.time()
        signals = {
            'shake': shake, 'blink': blink, 'eye': eye, 'freeze': freeze,
            'asym': asym, 'twitch': twitch, 'bpm': bpm, 'color': color,
        }

        # update all trackers
        for name, tracker in self.trackers.items():
            tracker.update(signals[name], t)

        # ── Stage evaluation ──────────────────────────────────────────────
        target_stage = self._evaluate_target_stage()
        self._update_stage(target_stage, t)

        # ── Score computation ─────────────────────────────────────────────
        self.pre_ictal_score = self._compute_score()

        result = {
            'pre_ictal_score': round(self.pre_ictal_score, 3),
            'stage':           self.current_stage,
            'stage_label':     self._stage_label(),
            'elevated_signals': [n for n, tr in self.trackers.items() if tr.is_elevated],
            'rising_signals':  [n for n, tr in self.trackers.items() if tr.slope() > 0.01],
            'warning':         self.pre_ictal_score >= 0.55,
            'signal_ewmas':    {n: round(tr.ewma, 3) for n, tr in self.trackers.items()},
        }

        self.history.append((t, result))
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _evaluate_target_stage(self):
        """
        Determine the highest stage currently supported by the signal state.
        Checks from highest to lowest so we always return the best-fitting stage.
        """
        elevated = {n for n, tr in self.trackers.items() if tr.is_elevated}
        rising   = {n for n, tr in self.trackers.items() if tr.slope() > 0.01}

        for stage in [3, 2, 1]:
            rule = STAGE_RULES[stage]
            # count how many of the rule's candidate signals are elevated
            candidates  = rule['required_any']
            n_elevated  = sum(1 for s in candidates if s in elevated)
            mean_score  = sum(self.trackers[s].ewma for s in candidates) / len(candidates)

            if n_elevated < rule['min_signals']:
                continue
            if mean_score < rule['score_threshold']:
                continue
            if rule.get('requires_trend'):
                n_rising = sum(1 for s in candidates if s in rising)
                if n_rising < 2:
                    continue
            return stage

        return 0

    def _update_stage(self, target_stage, t):
        """
        Apply hysteresis: advance stage only after it's been continuously
        supported for STAGE_HOLD seconds. Decay stage if unsupported for
        STAGE_DECAY seconds.
        """
        if target_stage >= self.current_stage:
            self._stage_last_supported = t
            if target_stage > self.current_stage:
                if self._stage_entry_time is None:
                    self._stage_entry_time = t
                elif (t - self._stage_entry_time) >= STAGE_HOLD:
                    self.current_stage = target_stage
                    self._stage_entry_time = t
            else:
                self._stage_entry_time = None
        else:
            # target is lower — decay slowly
            if (t - self._stage_last_supported) >= STAGE_DECAY:
                if self.current_stage > 0:
                    self.current_stage -= 1
                    self._stage_last_supported = t
                    self._stage_entry_time = None

    def _compute_score(self):
        """
        Combine three components into a single pre-ictal score [0, 1]:
          1. Stage component     — normalised stage level (0-3 → 0-0.5)
          2. Co-activation       — fraction of signals elevated simultaneously
          3. Trend component     — mean positive slope across elevated signals
        Weights reflect clinical importance: sustained pattern > momentary spike.
        """
        # 1. Stage (contributes up to 0.50)
        stage_score = (self.current_stage / 3.0) * 0.50

        # 2. Co-activation — how many signals elevated at once (up to 0.30)
        n_elevated = sum(1 for tr in self.trackers.values() if tr.is_elevated)
        coact_score = min(n_elevated / len(self.trackers), 1.0) * 0.30

        # 3. Trend — exponential weighting rewards consistent rise (up to 0.20)
        slopes = [tr.slope() for tr in self.trackers.values() if tr.is_elevated]
        if slopes:
            # sigmoid to keep in [0,1]; slopes >0.1/s get full weight
            mean_slope = sum(max(s, 0) for s in slopes) / len(slopes)
            trend_score = (1 / (1 + math.exp(-10 * (mean_slope - 0.05)))) * 0.20
        else:
            trend_score = 0.0

        return min(stage_score + coact_score + trend_score, 1.0)

    def _stage_label(self):
        return {
            0: 'Baseline',
            1: 'Prodromal',
            2: 'Pre-ictal',
            3: 'Imminent',
        }[self.current_stage]
