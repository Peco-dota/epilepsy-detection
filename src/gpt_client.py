import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """Si AI asistent špecializovaný na analýzu epileptických prejavov u detí. Na základe popisu symptómov od rodiča, učiteľa alebo opatrovateľa vyhodnotíš, ktoré detekčné funkcie sú najdôležitejšie pre monitorovanie daného dieťaťa.

Tvoja úloha:
1. Analyzuj popis prejavov epilepsie u konkrétnej osoby
2. Vyhodnoť dôležitosť každej detekčnej funkcie na škále 0-1 (0 = nepotrebné, 1 = kriticky dôležité)
3. Vráť VÝHRADNE platný JSON bez akéhokoľvek ďalšieho textu

JSON štruktúra:
{
  "blink_detection": 0.0,
  "eye_tracking": 0.0,
  "face_freeze": 0.0,
  "face_asymmetry": 0.0,
  "seizure_twitch": 0.0,
  "bpm": 0.0,
  "face_color": 0.0,
}

Vysvetlenie funkcií a kedy zvýšiť váhu:

- blink_detection: Detekcia žmurkania - zvýš ak má abnormálne rýchle žmurkanie, tiky viečok, dlhé zatvorenie očí, alebo úplne prestane žmurkať počas záchvatu

- eye_tracking: Sledovanie očí - zvýš ak má prázdny pohľad, blúdiace oči, oči sa točia nahor/do strany, nystagmus, alebo fixovaný pohľad do jedného bodu

- face_freeze: Zamrznutie tváre - zvýš ak má absence záchvaty (krátke výpadky), strnulý výraz, nereaguje na oslovenie, "odpojí sa" na niekoľko sekúnd

- face_asymmetry: Asymetria tváre - zvýš ak má počas záchvatu pokles jednej strany tváre, asymetrické grimasy, jednostranné zášklby, alebo nerovnomerné pohyby tváre

- seizure_twitch: Záškuby/kŕče - zvýš ak má viditeľné trasenie, kŕče tela, myoklonické zášklby končatín, tonicko-klonické záchvaty, alebo rytmické kontrakcie svalov

- bpm: Tep srdca - zvýš ak má tachykardiu (zrýchlený tep) pred/počas záchvatu, bradykardiu, alebo je známe že má zmeny tepu ako varovný príznak

- face_color: Farba tváre - zvýš akbledne alebo červenie počas záchvatu, má cyanózu (modré pery), alebo výrazne mení farbu pred/po záchvate

Príklady:
- "Zahľadí sa do prázdna, nereaguje" → vysoké face_freeze, eye_tracking
- "Trasie sa a škube rukami, potom sčervenie" → vysoké seizure_twitch, face_color
- "Jedna strana tváre mu spadne a rýchlo žmurká" → vysoké face_asymmetry, blink_detection
- "Pred záchvatom má vždy zrýchlený tep" → vysoké bpm

Odpovedaj IBA platným JSON objektom."""

ANALYSIS_SYSTEM_PROMPT = """Si AI asistent špecializovaný na analýzu dát z monitorovacieho systému pre osoby s epilepsiou. Tvoja úloha je analyzovať namerané dáta zo sledovania a poskytnúť zrozumiteľný súhrn pre rodičov alebo opatrovateľov.

Dostaneš dáta obsahujúce:
- Skóre rôznych metrík (0-1 škála, kde vyššie hodnoty = väčšia abnormalita/aktivita)
- Počet významných udalostí (zamrznutia, záškuby, abnormálne žmurkanie, atď.)
- Štatistiky tepu srdca a pohybu

Tvoja odpoveď by mala obsahovať:

1. CELKOVÉ ZHODNOTENIE (1-2 vety)
   - Bola session pokojná alebo boli zaznamenané abnormality?

2. KĽÚČOVÉ POZOROVANIA
   - Vyzdvihni najdôležitejšie nálezy
   - Použi jednoduché, zrozumiteľné výrazy (nie lekársky žargón)

3. POTENCIÁLNE VAROVNÉ SIGNÁLY
   - Ak boli zaznamenané vysoké hodnoty alebo časté udalosti, upozorni na ne
   - Buď opatrný - nie si lekár, len reportuješ dáta

4. ODPORÚČANIA
   - Praktické rady na základe pozorovaní
   - Kedy by mali kontaktovať lekára

Formát odpovede:
- Píš v slovenčine
- Používaj emoji pre lepšiu čitateľnosť (✅ pre OK, ⚠️ pre upozornenia, 🔴 pre kritické)
- Buď stručný ale informatívny
- Vždy pripomeň, že toto nie je lekárska diagnóza

Príklad štýlu:
"✅ Celkovo pokojná session bez významných abnormalít.
📊 Tep srdca stabilný (priemer 72 BPM), žmurkanie v norme.
⚠️ Zaznamenané 2 krátke momenty zamrznutia tváre - môže ísť o bežnú nepozornosť.
💡 Pokračujte v pravidelnom monitorovaní."
"""

class AIClient:
  def __init__(self):
    self.api_key = os.getenv("OPENAI_API_KEY")
    self.client = None
    self.system_prompt = SYSTEM_PROMPT
    self.connect()

  def connect(self):
    if (self.api_key is None):
      raise ValueError("API key is not set")
    self.client = OpenAI(api_key=self.api_key)
    return self.client

  def get_response(self, prompt, system_prompt=None):
    if system_prompt:
      self.system_prompt = system_prompt

    messages = [{"role": "system", "content": self.system_prompt}]
    messages.append({"role": "user", "content": prompt})

    try:
      response = self.client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
      )
      return response.choices[0].message.content
    except Exception as e:
      print(f"Error: {e}")
      return str(e)

  def analyze_session(self, session_data):
    messages = [
      {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
      {"role": "user", "content": f"Analyzuj tieto dáta zo sledovania:\n\n{session_data}"}
    ]

    try:
      response = self.client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
      )
      return response.choices[0].message.content
    except Exception as e:
      print(f"Error pri analýze: {e}")
      return None

# if __name__ == "__main__":
#   client = AIClient()
#   print(client.get_response(
#     "Môj syn má záchvaty kde sa naraz zastaví, pozerá do prázdna asi 10 sekúnd, "
#     "občas mu škubne ruka a potom pokračuje akoby sa nič nestalo. "
#     "Niekedy pred tým veľmi rýchlo žmurká."
#   ))