# epilepsy-detection

## What you need
**python3 3.10.x (ideally)**

## Setup
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
``` 

## Setup .env file
```
OPENAI_API_KEY="" # openai api key
TWILIO_ACCOUNT_SID="" # sms account sid
TWILIO_AUTH_TOKEN="" # sms auth token
TELEPHONE_NUMBER="" # Phone number of sms receiver
```

## How to run it
```
python3 ./src/main.py
```

If you want to avoid API usage, leave `USE_AI = False` in [src/main.py](src/main.py).
Set it to `True` only when you want AI features enabled.

\
You can adjust variable "debug" in main.py \
True = without gui | False = with gui \
Also this parameter affects if you see camera output \
\
Variable "solo_video" in main.py represents if all "model" outputs are shown in one frame or multiple frames (camera output windows).\
\
If you don't have access to .env properties set ai client and twilio client to "None"