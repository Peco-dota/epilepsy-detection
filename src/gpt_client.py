import os
import re
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _call_with_retry(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if '429' in msg:
                # parse suggested retry delay from error, default to 30s
                match = re.search(r'retry in (\d+)', msg)
                wait = int(match.group(1)) if match else 30
                wait = min(wait, 60)  # cap at 60s
                print(f"⏳ Rate limited — waiting {wait}s before retry ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Gemini API failed after {max_retries} retries")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = "gemini-3.1-flash-lite"

SYSTEM_PROMPT = """You are an AI assistant specialized in analyzing epileptic symptoms in children. Based on a symptom description provided by a parent, teacher, or caregiver, you determine which detection features are most important for monitoring the child.

Your task:
1. Analyze the description of epileptic symptoms for a specific person
2. Rate the importance of each detection feature on a 0-1 scale (0 = not needed, 1 = critically important)
3. Return ONLY a valid JSON object with no additional text

JSON structure:
{
  "blink_detection": 0.0,
  "eye_tracking": 0.0,
  "face_freeze": 0.0,
  "face_asymmetry": 0.0,
  "seizure_twitch": 0.0,
  "bpm": 0.0,
  "face_color": 0.0,
}

Feature explanations and when to increase the weight:

- blink_detection: Blink detection - increase if abnormally rapid blinking, eyelid tics, prolonged eye closure, or complete cessation of blinking during a seizure

- eye_tracking: Eye tracking - increase if blank stare, wandering eyes, eyes rolling upward/sideways, nystagmus, or fixed gaze at one point

- face_freeze: Face freeze - increase if absence seizures (brief blackouts), rigid expression, unresponsive to voice, "disconnects" for several seconds

- face_asymmetry: Facial asymmetry - increase if one side of the face droops during a seizure, asymmetric grimacing, unilateral twitching, or uneven facial movements

- seizure_twitch: Twitches/convulsions - increase if visible shaking, body convulsions, myoclonic limb jerks, tonic-clonic seizures, or rhythmic muscle contractions

- bpm: Heart rate - increase if tachycardia before/during seizure, bradycardia, or known heart rate changes as a warning sign

- face_color: Face color - increase if pallor or flushing during seizure, cyanosis (blue lips), or significant color change before/after seizure

Examples:
- "Stares into space, unresponsive" → high face_freeze, eye_tracking
- "Shakes and jerks arms, then flushes" → high seizure_twitch, face_color
- "One side of face droops and rapid blinking" → high face_asymmetry, blink_detection
- "Always has rapid heartbeat before seizure" → high bpm

Respond with ONLY a valid JSON object."""

CONTEXT_SYSTEM_PROMPT = """You are EpiGuard's pre-session risk assessor. A caregiver has described the patient's current condition and context before a monitoring session.

Your job is to output a JSON object with a sensitivity multiplier (0.5 – 2.0) for each detection signal, based on known epilepsy trigger research:
- Sleep deprivation → lower threshold for all signals (multiplier > 1.0)
- Stress / anxiety → lower threshold especially for autonomic signals (bpm, color)
- Screen/photosensitive exposure → lower threshold for visual signals (eye, blink)
- Medication taken correctly → slightly raise threshold (multiplier slightly < 1.0)
- Calm day, well-rested → keep at baseline (multiplier = 1.0)
- Missed medication → significantly lower all thresholds (multiplier > 1.5)

Output ONLY valid JSON with these exact keys and float values between 0.5 and 2.0:
{"shake": 1.0, "blink": 1.0, "eye": 1.0, "freeze": 1.0, "asym": 1.0, "twitch": 1.0, "bpm": 1.0, "color": 1.0}

Also include a "summary" key with a single plain-English sentence explaining the main risk factor identified.
Example: {"shake": 1.3, "blink": 1.4, ..., "summary": "Sleep deprivation increases seizure risk — all signals set to higher sensitivity."}"""

RECALIBRATION_SYSTEM_PROMPT = """You are an AI assistant that recalibrates seizure detection weights based on user feedback from a monitoring session.

You will receive:
- Current detection weights (each 0.05–0.8 range)
- A list of alerts that fired during the session, each with:
  - The signal scores at alert time (0-1 scale)
  - Whether the user confirmed it was a real seizure (correct) or false positive (wrong)

Your task:
- Analyze the pattern of correct vs false positive alerts
- Return updated weights that will improve future detection accuracy
- If a signal was consistently high during correct alerts → increase its weight
- If a signal was high during false positives but low during correct alerts → decrease its weight
- Keep weights in range 0.05–0.80
- Return ONLY a valid JSON object, no other text

Weight keys: w_bpm, w_color, w_shake, w_twitch, w_blink, w_freeze, w_asym, w_blink_nc, w_bpm_nc

Respond with ONLY a valid JSON object like:
{"w_bpm": 0.10, "w_color": 0.10, "w_shake": 0.30, "w_twitch": 0.35, "w_blink": 0.30, "w_freeze": 0.40, "w_asym": 0.55, "w_blink_nc": 0.30, "w_bpm_nc": 0.10}"""

ANALYSIS_SYSTEM_PROMPT = """You are an AI assistant helping caregivers understand epilepsy monitoring session data.

IMPORTANT INTERPRETATION RULES:
- Scores are 0.0-1.0. Below 0.3 = normal, 0.3-0.6 = mild, above 0.6 = notable.
- High-score moments are given as a percentage of the session — a low percentage (under 20%) is normal even if the raw count sounds large.
- Face freeze score is triggered by stillness — normal during calm sitting or reading.
- Eye movement score can be elevated by normal looking around.
- Only flag something as concerning if the AVERAGE score is above 0.5 OR if high-score moments exceed 30% of the session.
- Heart rate below 50 BPM average likely means calibration was incomplete — do not flag as abnormal.
- Be conservative. A quiet session should be reported as quiet.

Your response should be brief (4-6 sentences max):
1. One sentence: overall session tone (calm / mildly active / notable activity)
2. One or two sentences: what the data actually showed, using percentages not raw counts
3. One sentence: anything genuinely worth mentioning to a doctor (if anything)
4. One sentence: practical next step

Use ✅ for calm findings, ⚠️ only for genuinely elevated values, 🔴 only for clearly abnormal patterns.
Always end with: "This is not a medical diagnosis — consult your doctor for clinical interpretation."
"""

class AIClient:
  def __init__(self):
    self.api_key = os.getenv("GEMINI_API_KEY")
    self.client = None
    self.system_prompt = SYSTEM_PROMPT
    if self.api_key is None:
      raise ValueError("GEMINI_API_KEY is not set in .env")
    self.client = OpenAI(api_key=self.api_key, base_url=GEMINI_BASE_URL)

  def get_response(self, prompt, system_prompt=None):
    if system_prompt:
      self.system_prompt = system_prompt

    messages = [{"role": "system", "content": self.system_prompt}]
    messages.append({"role": "user", "content": prompt})

    try:
      return _call_with_retry(lambda: self.client.chat.completions.create(
        model=GEMINI_MODEL, messages=messages
      ).choices[0].message.content)
    except Exception as e:
      print(f"Error: {e}")
      return str(e)

  def analyze_session(self, session_data):
    messages = [
      {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
      {"role": "user", "content": f"Analyze the following monitoring session data:\n\n{session_data}"}
    ]
    try:
      return _call_with_retry(lambda: self.client.chat.completions.create(
        model=GEMINI_MODEL, messages=messages
      ).choices[0].message.content)
    except Exception as e:
      print(f"Error during analysis: {e}")
      return None

  def assess_context(self, context_text):
    messages = [
      {"role": "system", "content": CONTEXT_SYSTEM_PROMPT},
      {"role": "user", "content": context_text}
    ]
    try:
      return _call_with_retry(lambda: self.client.chat.completions.create(
        model=GEMINI_MODEL, messages=messages
      ).choices[0].message.content)
    except Exception as e:
      print(f"Error during context assessment: {e}")
      return None

  def recalibrate_weights(self, current_weights, feedback_events):
    if not feedback_events:
      return None

    events_text = ""
    for i, event in enumerate(feedback_events, 1):
      result = "CORRECT (real seizure)" if event['correct'] else "FALSE POSITIVE"
      events_text += f"\nAlert {i} [{result}]:\n"
      for signal, score in event['scores'].items():
        events_text += f"  {signal}: {score:.3f}\n"

    messages = [
      {"role": "system", "content": RECALIBRATION_SYSTEM_PROMPT},
      {"role": "user", "content": f"Current weights:\n{current_weights}\n\nAlert feedback:{events_text}"}
    ]
    try:
      return _call_with_retry(lambda: self.client.chat.completions.create(
        model=GEMINI_MODEL, messages=messages
      ).choices[0].message.content)
    except Exception as e:
      print(f"Error during recalibration: {e}")
      return None

