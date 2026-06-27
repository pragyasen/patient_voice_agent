# Architecture

The patient voice agent is a modular **STT (Speech-to-Text) → LLM → TTS (Text-to-Speech)** pipeline bridged to the phone network via Twilio Media Streams. When we place an outbound call to the assessment number, Twilio connects the live audio to our FastAPI WebSocket server. Incoming audio from the clinic agent is streamed to Deepgram for live transcription; when Deepgram detects the end of an utterance, the transcript is sent to **Llama 3.3 70B on Groq** with a scenario-specific system prompt that simulates patient Pragya Sen. The model’s reply is synthesized by Deepgram Aura TTS, converted to 8 kHz μ-law (Twilio’s phone format), and streamed back into the call in real-time chunks.

This architecture was chosen over end-to-end voice APIs (e.g. OpenAI Realtime) because the goal is a **test harness**, not a general voice assistant. Separating speech, reasoning and synthesis gives explicit two-sided transcripts with timestamps, which is essential for bug reports and lets us swap scenarios, tune turn-taking and iterate on patient prompts without reworking telephony. Groq provides fast inference on open-weight Llama at negligible cost, keeping the budget on unavoidable Twilio minutes.

**Tradeoff:** Increases integration work (endpointing, echo avoidance while the bot speaks, pacing TTS chunks), but gain control and auditable evidence for each test call.

## Call flow

```
python main.py call
       │
       ▼
 Twilio REST ──► dials +1-805-439-8008
       │
       ▼
 /voice/outbound ──► TwiML <Connect><Stream wss://...>
       │
       ▼
 /media-stream WebSocket
   ├─ inbound audio ──► Deepgram STT ──► utterance text
   ├─ utterance text ──► Groq Llama ──► patient reply
   └─ reply text ──► Deepgram TTS ──► μ-law ──► Twilio ──► caller hears patient
       │
       ▼
 Post-call: Twilio recording callback ──► recordings/call-{id}.mp3
 Live logging ──► transcripts/call-{id}.txt
```



## Key design choices


| Decision                     | Rationale                                                                |
| ---------------------------- | ------------------------------------------------------------------------ |
| Groq + Llama 70B             | Fast, free-tier friendly, strong enough for multi-step patient scenarios |
| Deepgram phonecall STT model | Tuned for 8 kHz telephony audio                                          |
| Scenario YAML files          | Reproducible test matrix without code changes                            |
| Dual-channel recording       | Both sides captured for submission evidence                              |
| Mute STT while bot speaks    | Avoid transcribing our own TTS as agent speech                           |


