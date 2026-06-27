from __future__ import annotations

import asyncio
import audioop
import json
import logging
import os
import shutil
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import httpx
import websockets

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
MULAW_CHUNK_SIZE = 160  # 20ms at 8kHz
MULAW_SILENCE = b"\xff"
CHUNK_DURATION_SECONDS = MULAW_CHUNK_SIZE / SAMPLE_RATE


def _ensure_ffmpeg_on_path() -> None:
    if shutil.which("ffmpeg"):
        return
    winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    matches = list(winget_root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    if matches:
        os.environ["PATH"] = str(matches[0].parent) + os.pathsep + os.environ.get("PATH", "")


_ensure_ffmpeg_on_path()

from pydub import AudioSegment


def _looks_complete_utterance(text: str) -> bool:
    """Kept for tests; live STT only emits on UtteranceEnd."""
    text = " ".join(text.split()).strip()
    if len(text) < 8:
        return False
    if text[-1] in ".?!":
        return True
    return len(text) >= 55


def iter_mulaw_chunks(mulaw_audio: bytes) -> Iterator[bytes]:
    for offset in range(0, len(mulaw_audio), MULAW_CHUNK_SIZE):
        chunk = mulaw_audio[offset : offset + MULAW_CHUNK_SIZE]
        if len(chunk) < MULAW_CHUNK_SIZE:
            chunk = chunk + MULAW_SILENCE * (MULAW_CHUNK_SIZE - len(chunk))
        yield chunk


def wav_bytes_to_mulaw(wav_bytes: bytes, *, gain_db: float = 5.0) -> bytes:
    audio = AudioSegment.from_wav(BytesIO(wav_bytes))
    audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    if gain_db:
        audio = audio + gain_db
    return audioop.lin2ulaw(audio.raw_data, 2)


def mulaw_to_wav_bytes(mulaw: bytes) -> bytes:
    """Convert mulaw back to WAV for local listening tests."""
    pcm = audioop.ulaw2lin(mulaw, 2)
    audio = AudioSegment(
        data=pcm,
        sample_width=2,
        frame_rate=SAMPLE_RATE,
        channels=1,
    )
    buf = BytesIO()
    audio.export(buf, format="wav")
    return buf.getvalue()


def synthesize_speech(
    api_key: str,
    text: str,
    *,
    tts_model: str = "aura-2-thalia-en",
    gain_db: float = 5.0,
) -> bytes:
    """Batch TTS via WAV, converted once to 8kHz mulaw for Twilio."""
    response = httpx.post(
        "https://api.deepgram.com/v1/speak",
        params={
            "model": tts_model,
            "encoding": "linear16",
            "container": "wav",
            "sample_rate": str(SAMPLE_RATE),
        },
        json={"text": text},
        headers={"Authorization": f"Token {api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return wav_bytes_to_mulaw(response.content, gain_db=gain_db)


class LiveTranscriber:
    """Async Deepgram live STT for Twilio mulaw 8kHz audio."""

    def __init__(
        self,
        api_key: str,
        on_utterance,
        *,
        stt_model: str = "nova-2-phonecall",
        utterance_end_ms: int = 1000,
        endpointing_ms: int = 300,
    ) -> None:
        self._api_key = api_key
        self._on_utterance = on_utterance
        self._stt_model = stt_model
        self._utterance_end_ms = utterance_end_ms
        self._endpointing_ms = endpointing_ms
        self._parts: list[str] = []
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._receive_task: asyncio.Task | None = None
        self._last_utterance = ""

    async def start(self) -> None:
        query = (
            "encoding=mulaw&sample_rate=8000&channels=1"
            f"&model={self._stt_model}&interim_results=true"
            f"&utterance_end_ms={self._utterance_end_ms}"
            f"&endpointing={self._endpointing_ms}&smart_format=true"
        )
        url = f"wss://api.deepgram.com/v1/listen?{query}"
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {self._api_key}"},
        )
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("Deepgram live transcription started")

    async def send(self, chunk: bytes) -> None:
        if self._ws:
            await self._ws.send(chunk)

    async def finish(self) -> None:
        if self._ws:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            await self._ws.close()
        if self._receive_task:
            self._receive_task.cancel()

    async def _emit_utterance(self) -> None:
        text = " ".join(self._parts).strip()
        self._parts = []
        if not text or text == self._last_utterance:
            return
        if len(text) < 4:
            logger.debug("Ignored tiny STT fragment: %r", text)
            return
        self._last_utterance = text
        await self._on_utterance(text)

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue
                data = json.loads(message)
                message_type = data.get("type")

                if message_type == "Results":
                    alternative = data["channel"]["alternatives"][0]
                    transcript = alternative.get("transcript", "")
                    if transcript and data.get("is_final"):
                        self._parts.append(transcript)
                elif message_type == "UtteranceEnd":
                    await self._emit_utterance()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Deepgram receive loop failed")
