# Patient Voice Agent

Automated voice bot that calls the Pretty Good AI assessment line (`+1-805-439-8008`), simulates realistic patient scenarios, records conversations and saves transcripts for bug reporting.

## Stack

- **Twilio**: outbound calls, Media Streams, dual-channel recordings
- **Deepgram**: speech-to-text (`nova-2-phonecall`) and text-to-speech (`aura-2-thalia-en`)
- **Groq (Llama 3.1 8B Instant)**: patient conversation brain
- **FastAPI**: webhooks and WebSocket media bridge

See [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale.

## Prerequisites

1. Python 3.11+
2. [ffmpeg](https://ffmpeg.org/) on your PATH (required by `pydub` for audio conversion; `start.bat` also tries WinGet-installed ffmpeg)
3. Accounts / API keys:
  - [Twilio](https://www.twilio.com/try-twilio) - outbound number + trial/paid balance
  - [Deepgram](https://console.deepgram.com)
  - [Groq](https://console.groq.com)
4. [ngrok](https://ngrok.com) - public webhook tunnel (`winget install Ngrok.Ngrok` on Windows)

## Setup (one time)

```powershell
cd patient_voice_agent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` with your Twilio, Deepgram, and Groq credentials. Leave `PUBLIC_WEBHOOK_URL` blank — `start.bat` sets it from ngrok automatically.

**Restart the server** after any `.env` change.

## Run

### Terminal 1 : ngrok + server

```bat
.\start.bat
```

This will:

1. Start ngrok in a new window (or reuse an existing tunnel)
2. Auto-update `PUBLIC_WEBHOOK_URL` in `.env`
3. Start the FastAPI server on port 8000

Keep this terminal open while placing calls. Watch it for live logs (STT, TTS, Groq, errors).

### Terminal 2 : place calls

**Single call** (scenario name + call id):

```bat
.\call.bat schedule_new 01
```

Invalid scenario names fail **before** Twilio dials.

**All scenarios sequentially** (waits for each call to finish, 10 s pause between):

```bat
.\call-all.bat
```

Start at a specific call id (e.g. if 01–04 already exist):

```bat
.\call-all.bat 05
```

**List scenarios:**

```bat
.venv\Scripts\python.exe main.py scenarios
```

**Preview voice locally for testing** (no Twilio cost: writes `previews/voice-preview.wav`):

```bat
.\preview.bat medication_reaction
```



### CLI reference


| Command                                            | Purpose                             |
| -------------------------------------------------- | ----------------------------------- |
| `python main.py serve`                             | Start webhook + media stream server |
| `python main.py call --scenario ID --call-id 01`   | Place one outbound call             |
| `python main.py call-all --start-id 01 --delay 10` | Run every scenario in order         |
| `python main.py scenarios`                         | List scenario ids                   |
| `python main.py preview-voice --scenario ID`       | Local TTS preview                   |




### Manual flow (3 terminals)

If you prefer not to use the batch scripts:

```powershell
ngrok http 8000
#Copy the https URL into .env as PUBLIC_WEBHOOK_URL

.venv\Scripts\python.exe main.py serve
.venv\Scripts\python.exe main.py call --scenario schedule_new --call-id 01
```



## Outputs

After each call:


| Artifact                            | Location                    |
| ----------------------------------- | --------------------------- |
| Transcript (both sides, timestamps) | `transcripts/call-{id}.txt` |
| Recording (dual-channel mp3)        | `recordings/call-{id}.mp3`  |


Recordings arrive a few seconds after the call ends via Twilio callback. Log bugs in [BUGS.md](BUGS.md).

## Scenarios (10 included)


| ID                            | Purpose                                                                  |
| ----------------------------- | ------------------------------------------------------------------------ |
| `change_mind`                 | Switch intent mid-call                                                   |
| `insurance_update`            | Update insurance (Aetna PPO)                                             |
| `medical_advice_request`      | Asks for diagnosis/treatment. Agent should defer to physician            |
| `medication_reaction`         | Urgent possible adverse reaction (hives, lip swelling)                   |
| `non_orthopedic_ailment`      | Sore throat/fever. Tests whether **their** agent redirects out of scope. |
| `office_hours`                | Ask about clinic hours                                                   |
| `refill`                      | Routine medication refill                                                |
| `schedule_new`                | Book a knee follow-up appointment                                        |
| `unauthorized_records_access` | Impersonator tries to obtain another patient's info                      |
| `unprescribed_refill`         | Refill for a drug never prescribed (controlled Rx)                       |


Scenario YAML lives in `scenarios/`.

### Batch call id mapping

`call-all.bat` runs scenarios in alphabetical order:


| Call ID | Scenario                      |
| ------- | ----------------------------- |
| 01      | `change_mind`                 |
| 02      | `insurance_update`            |
| 03      | `medical_advice_request`      |
| 04      | `medication_reaction`         |
| 05      | `non_orthopedic_ailment`      |
| 06      | `office_hours`                |
| 07      | `refill`                      |
| 08      | `schedule_new`                |
| 09      | `unauthorized_records_access` |
| 10      | `unprescribed_refill`         |




## Latency tuning

Conversation timing is controlled via `.env` (restart server after edits):


| Variable                   | Role                                                    | Notes                                   |
| -------------------------- | ------------------------------------------------------- | --------------------------------------- |
| `UTTERANCE_END_MS`         | Silence before agent turn is considered complete        | Must stay **≥ 1000** (Deepgram minimum) |
| `ENDPOINTING_MS`           | STT endpointing sensitivity                             | Lower = snappier, more fragment risk    |
| `AGENT_LISTEN_COOLDOWN_MS` | Pause after patient speaks before listening again       | Lower = snappier, more overlap risk     |
| `SILENCE_OPENING_SECONDS`  | Wait before patient opening line if agent hasn't spoken | Default 2                               |


If the patient talks over the agent or replies to half-sentences, raise `AGENT_LISTEN_COOLDOWN_MS` first, then `UTTERANCE_END_MS`.

