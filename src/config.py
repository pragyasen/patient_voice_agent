from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT_DIR / "scenarios"
RECORDINGS_DIR = ROOT_DIR / "recordings"
TRANSCRIPTS_DIR = ROOT_DIR / "transcripts"


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_caller_number: str
    target_number: str
    public_webhook_url: str
    deepgram_api_key: str
    groq_api_key: str
    groq_model: str
    host: str
    port: int
    max_call_duration_seconds: int
    silence_opening_seconds: int
    tts_model: str
    stt_model: str
    utterance_end_ms: int
    endpointing_ms: int
    tts_gain_db: float
    tts_playback_speed: float
    agent_listen_cooldown_ms: int

    @classmethod
    def from_env(cls) -> Settings:
        missing = [
            name
            for name, value in {
                "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID"),
                "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN"),
                "TWILIO_CALLER_NUMBER": os.getenv("TWILIO_CALLER_NUMBER"),
                "PUBLIC_WEBHOOK_URL": os.getenv("PUBLIC_WEBHOOK_URL"),
                "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY"),
                "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill in values."
            )

        return cls(
            twilio_account_sid=os.environ["TWILIO_ACCOUNT_SID"],
            twilio_auth_token=os.environ["TWILIO_AUTH_TOKEN"],
            twilio_caller_number=os.environ["TWILIO_CALLER_NUMBER"],
            target_number=os.getenv("TARGET_NUMBER", "+18054398008"),
            public_webhook_url=os.environ["PUBLIC_WEBHOOK_URL"].rstrip("/"),
            deepgram_api_key=os.environ["DEEPGRAM_API_KEY"],
            groq_api_key=os.environ["GROQ_API_KEY"],
            groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            max_call_duration_seconds=int(os.getenv("MAX_CALL_DURATION_SECONDS", "180")),
            silence_opening_seconds=int(os.getenv("SILENCE_OPENING_SECONDS", "2")),
            tts_model=os.getenv("TTS_MODEL", "aura-2-thalia-en"),
            stt_model=os.getenv("STT_MODEL", "nova-2-phonecall"),
            utterance_end_ms=max(
                1000,
                min(5000, int(os.getenv("UTTERANCE_END_MS", "1200"))),
            ),
            endpointing_ms=max(
                100,
                min(500, int(os.getenv("ENDPOINTING_MS", "400"))),
            ),
            tts_gain_db=float(os.getenv("TTS_GAIN_DB", "5")),
            tts_playback_speed=max(
                0.85,
                min(1.0, float(os.getenv("TTS_PLAYBACK_SPEED", "1.0"))),
            ),
            agent_listen_cooldown_ms=max(
                0,
                min(2000, int(os.getenv("AGENT_LISTEN_COOLDOWN_MS", "350"))),
            ),
        )


def get_settings() -> Settings:
    return Settings.from_env()
