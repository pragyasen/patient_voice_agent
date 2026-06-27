from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

from src.config import Settings
from src.patient_agent import PatientAgent
from src.scenarios import TranscriptWriter, load_scenario
from src.speech import SAMPLE_RATE, LiveTranscriber, synthesize_speech

logger = logging.getLogger(__name__)

_BOILERPLATE_MARKERS = (
    "call may be recorded",
    "quality and training",
)


def _is_boilerplate_agent_text(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _BOILERPLATE_MARKERS)


class AudioPlayout:
    """Send mulaw to Twilio in a dedicated task so STT traffic cannot stutter playback."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._stream_sid: str | None = None
        self._queue: asyncio.Queue[tuple[bytes, asyncio.Event] | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def bind(self, stream_sid: str) -> None:
        self._stream_sid = stream_sid
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def play(self, mulaw: bytes) -> None:
        if not self._stream_sid or not mulaw:
            return
        done = asyncio.Event()
        await self._queue.put((mulaw, done))
        await done.wait()

    async def close(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            mulaw, done = item
            try:
                await self._send(mulaw)
            finally:
                done.set()

    async def _send(self, mulaw: bytes) -> None:
        assert self._stream_sid is not None
        # Send the full utterance in one message — Twilio buffers and plays it smoothly.
        # Chunking with asyncio.sleep() causes gaps/clicks on Windows event loops.
        await self._websocket.send_json(
            {
                "event": "media",
                "streamSid": self._stream_sid,
                "media": {
                    "payload": base64.b64encode(mulaw).decode("ascii"),
                },
            }
        )
        await asyncio.sleep(len(mulaw) / SAMPLE_RATE)


class CallSession:
    def __init__(
        self,
        websocket: WebSocket,
        settings: Settings,
        scenario_id: str,
        call_id: str,
    ) -> None:
        self.websocket = websocket
        self.settings = settings
        self.scenario = load_scenario(scenario_id)
        self.agent = PatientAgent(settings, self.scenario)
        self.transcript = TranscriptWriter.create(call_id, scenario_id)
        self.stream_sid: str | None = None
        self.is_speaking = False
        self.processing = False
        self.heard_agent = False
        self.opening_sent = False
        self._transcriber: LiveTranscriber | None = None
        self._pending_agent_parts: list[str] = []
        self._listen_after = 0.0
        self._playout = AudioPlayout(websocket)

    async def handle_message(self, raw: str) -> None:
        data: dict[str, Any] = json.loads(raw)
        event = data.get("event")

        if event == "connected":
            logger.info("Twilio media stream connected")

        elif event == "start":
            self.stream_sid = data["start"]["streamSid"]
            self._playout.bind(self.stream_sid)
            logger.info("Stream started: %s", self.stream_sid)
            self._transcriber = LiveTranscriber(
                self.settings.deepgram_api_key,
                self._on_agent_utterance,
                stt_model=self.settings.stt_model,
                utterance_end_ms=self.settings.utterance_end_ms,
                endpointing_ms=self.settings.endpointing_ms,
            )
            try:
                await self._transcriber.start()
            except Exception:
                logger.exception(
                    "Deepgram STT failed to start (check UTTERANCE_END_MS >= 1000)"
                )
                self._transcriber = None
                return
            asyncio.create_task(self._maybe_send_opening())

        elif event == "media":
            if not self._transcriber:
                return
            payload = base64.b64decode(data["media"]["payload"])
            await self._transcriber.send(payload)

        elif event == "stop":
            logger.info("Stream stopped")
            if self._transcriber:
                await self._transcriber.finish()
            await self._playout.close()

    async def _maybe_send_opening(self) -> None:
        await asyncio.sleep(self.settings.silence_opening_seconds)
        if not self.heard_agent and not self.opening_sent:
            opening = self.agent.opening_line(self.scenario)
            await self.speak(opening)
            self.agent.record_opening(opening)

    def _queue_agent_text(self, text: str) -> None:
        if self._pending_agent_parts and text == self._pending_agent_parts[-1]:
            return
        self._pending_agent_parts.append(text)
        logger.debug("Queued agent text while busy: %s", text[:80])

    async def _on_agent_utterance(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        if _is_boilerplate_agent_text(text):
            self.heard_agent = True
            self.transcript.append("AGENT", text)
            logger.debug("Ignored boilerplate agent line: %s", text[:80])
            return

        if self.processing or self.is_speaking:
            self._queue_agent_text(text)
            return

        if time.monotonic() < self._listen_after:
            self._queue_agent_text(text)
            asyncio.create_task(self._flush_pending_agent_text())
            return

        await self._process_utterance(text)

    async def _flush_pending_agent_text(self) -> None:
        if not self._pending_agent_parts or self.processing or self.is_speaking:
            return

        delay = self._listen_after - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

        if not self._pending_agent_parts or self.processing or self.is_speaking:
            return

        pending = " ".join(self._pending_agent_parts).strip()
        self._pending_agent_parts = []
        if pending:
            await self._process_utterance(pending)

    async def _process_utterance(self, text: str) -> None:
        self.heard_agent = True
        self.processing = True
        self.transcript.append("AGENT", text)

        try:
            reply = await asyncio.to_thread(self.agent.generate_reply, text)
            if reply:
                self.transcript.append("PATIENT", reply)
                self.opening_sent = True
                await self.speak(reply, append_transcript=False)
        finally:
            self.processing = False
            await self._flush_pending_agent_text()

    async def speak(self, text: str, *, append_transcript: bool = True) -> None:
        if not self.stream_sid:
            return

        text = text.strip()
        if not text:
            return

        if append_transcript:
            self.transcript.append("PATIENT", text)
            self.opening_sent = True

        try:
            mulaw = await asyncio.to_thread(
                synthesize_speech,
                self.settings.deepgram_api_key,
                text,
                tts_model=self.settings.tts_model,
                gain_db=self.settings.tts_gain_db,
            )
            self.is_speaking = True
            await self._playout.play(mulaw)
        except Exception:
            logger.exception("TTS failed for: %s", text[:80])
        finally:
            self.is_speaking = False
            self._listen_after = (
                time.monotonic() + self.settings.agent_listen_cooldown_ms / 1000.0
            )
