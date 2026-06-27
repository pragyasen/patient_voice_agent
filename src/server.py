from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import unquote

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from src.config import RECORDINGS_DIR, Settings, get_settings
from src.media_stream import CallSession
from src.twilio_client import call_registry, download_recording, media_stream_url

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Patient Voice Agent", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/voice/outbound")
    async def voice_outbound(request: Request) -> Response:
        scenario_id = request.query_params.get("scenario", "schedule_new")
        call_id = request.query_params.get("call_id", "01")

        form = await request.form()
        call_sid = str(form.get("CallSid", ""))
        if call_sid:
            call_registry.register(call_sid, call_id, scenario_id)
            logger.info("Registered call %s -> call-%s (%s)", call_sid, call_id, scenario_id)

        response = VoiceResponse()
        connect = Connect()
        stream = Stream(url=media_stream_url(settings.public_webhook_url))
        stream.parameter(name="scenario", value=scenario_id)
        stream.parameter(name="call_id", value=call_id)
        connect.append(stream)
        response.append(connect)
        return Response(content=str(response), media_type="application/xml")

    @app.post("/voice/recording-status")
    async def recording_status(request: Request) -> dict[str, str]:
        try:
            form = await request.form()
            call_sid = str(form.get("CallSid", ""))
            recording_url = str(form.get("RecordingUrl", ""))
            status = str(form.get("RecordingStatus", ""))

            if status != "completed" or not recording_url:
                return {"status": "ignored"}

            metadata = call_registry.lookup(call_sid)
            call_id = metadata["call_id"] if metadata else call_sid

            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            destination = RECORDINGS_DIR / f"call-{call_id}.mp3"
            download_recording(settings, recording_url, destination)
            logger.info("Saved recording to %s", destination)
            return {"status": "saved", "path": str(destination)}
        except Exception:
            logger.exception("Failed to save recording callback")
            return {"status": "error"}

    @app.websocket("/media-stream")
    async def media_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        scenario_id = "schedule_new"
        call_id = "01"
        session: CallSession | None = None

        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                if data.get("event") == "start":
                    custom = data.get("start", {}).get("customParameters", {})
                    if isinstance(custom, list):
                        custom = {
                            item["name"]: item["value"] for item in custom
                        }
                    scenario_id = unquote(custom.get("scenario", scenario_id))
                    call_id = unquote(custom.get("call_id", call_id))
                    session = CallSession(websocket, settings, scenario_id, call_id)
                    await session.handle_message(message)
                elif session:
                    asyncio.create_task(
                        _handle_stream_message(session, message),
                        name="twilio-media-message",
                    )
        except WebSocketDisconnect:
            logger.info("Media stream disconnected")
        except Exception:
            logger.exception("Media stream error")

    return app


async def _handle_stream_message(session: CallSession, message: str) -> None:
    try:
        await session.handle_message(message)
    except Exception:
        logger.exception("Error handling media stream message")
