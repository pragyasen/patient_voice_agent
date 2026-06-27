from __future__ import annotations

import time
from dataclasses import dataclass, field

from pathlib import Path

import httpx
from twilio.rest import Client

from src.config import Settings

TERMINAL_CALL_STATUSES = frozenset(
    {"completed", "busy", "failed", "no-answer", "canceled"}
)


@dataclass
class CallRegistry:
    """Maps Twilio CallSid to local call metadata."""

    by_call_sid: dict[str, dict[str, str]] = field(default_factory=dict)

    def register(self, call_sid: str, call_id: str, scenario_id: str) -> None:
        self.by_call_sid[call_sid] = {
            "call_id": call_id,
            "scenario_id": scenario_id,
        }

    def lookup(self, call_sid: str) -> dict[str, str] | None:
        return self.by_call_sid.get(call_sid)


call_registry = CallRegistry()


def media_stream_url(public_webhook_url: str) -> str:
    base = public_webhook_url.rstrip("/")
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1) + "/media-stream"
    if base.startswith("http://"):
        return base.replace("http://", "ws://", 1) + "/media-stream"
    return f"wss://{base}/media-stream"


def place_outbound_call(settings: Settings, scenario_id: str, call_id: str) -> str:
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    webhook = settings.public_webhook_url.rstrip("/")
    call = client.calls.create(
        to=settings.target_number,
        from_=settings.twilio_caller_number,
        url=f"{webhook}/voice/outbound?scenario={scenario_id}&call_id={call_id}",
        record=True,
        recording_channels="dual",
        recording_status_callback=f"{webhook}/voice/recording-status",
        recording_status_callback_event=["completed"],
        timeout=30,
        time_limit=settings.max_call_duration_seconds,
    )
    call_registry.register(call.sid, call_id, scenario_id)
    return call.sid


def wait_for_call_complete(
    settings: Settings,
    call_sid: str,
    *,
    poll_seconds: float = 3.0,
) -> str:
    """Poll Twilio until the call reaches a terminal status."""
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    while True:
        status = client.calls(call_sid).fetch().status
        if status in TERMINAL_CALL_STATUSES:
            return status
        time.sleep(poll_seconds)


def download_recording(settings: Settings, recording_url: str, destination: Path) -> None:
    recording_url = recording_url.rstrip("/")
    if recording_url.endswith(".mp3"):
        mp3_url = recording_url
    elif recording_url.endswith(".json"):
        mp3_url = recording_url.replace(".json", ".mp3")
    else:
        mp3_url = f"{recording_url}.mp3"

    response = httpx.get(
        mp3_url,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        timeout=60.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    destination.write_bytes(response.content)
