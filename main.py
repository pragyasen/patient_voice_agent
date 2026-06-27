from __future__ import annotations

import argparse
import logging
import sys

from src.config import SCENARIOS_DIR, ROOT_DIR, get_settings
from src.scenarios import load_scenario
from src.speech import SAMPLE_RATE, mulaw_to_wav_bytes, synthesize_speech


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from src.server import create_app

    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


def cmd_call(args: argparse.Namespace) -> None:
    from src.twilio_client import place_outbound_call

    settings = get_settings()
    try:
        scenario_id = load_scenario(args.scenario).id
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    call_sid = place_outbound_call(settings, scenario_id, args.call_id)
    print(f"Call started: {call_sid}")
    print(f"Scenario: {scenario_id}")
    print(f"Call ID: {args.call_id}")
    print(f"Transcript will be saved to transcripts/call-{args.call_id}.txt")
    print(f"Recording will be saved to recordings/call-{args.call_id}.mp3")


def cmd_call_all(args: argparse.Namespace) -> None:
    import time

    from src.twilio_client import place_outbound_call, wait_for_call_complete

    settings = get_settings()
    scenarios = sorted(path.stem for path in SCENARIOS_DIR.glob("*.yaml"))
    if not scenarios:
        print("No scenarios found.", file=sys.stderr)
        sys.exit(1)

    start_num = int(args.start_id)
    total = len(scenarios)

    print(f"Running {total} scenarios sequentially (call IDs {start_num:02d} onward)")
    print("Keep start.bat running in another terminal.\n")

    for index, scenario_id in enumerate(scenarios):
        call_id = f"{start_num + index:02d}"
        print(f"=== [{index + 1}/{total}] {scenario_id} -> call-{call_id} ===")

        try:
            resolved_id = load_scenario(scenario_id).id
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        call_sid = place_outbound_call(settings, resolved_id, call_id)
        print(f"Call started: {call_sid}")

        status = wait_for_call_complete(
            settings,
            call_sid,
            poll_seconds=args.poll_seconds,
        )
        print(f"Call finished: {status}")
        print(f"  transcript: transcripts/call-{call_id}.txt")
        print(f"  recording:  recordings/call-{call_id}.mp3")

        if args.delay > 0 and index < total - 1:
            print(f"Waiting {args.delay}s before next call...\n")
            time.sleep(args.delay)

    print("\nAll scenarios complete.")


def cmd_list_scenarios(_: argparse.Namespace) -> None:
    scenarios = sorted(path.stem for path in SCENARIOS_DIR.glob("*.yaml"))
    if not scenarios:
        print("No scenarios found.")
        return
    print("Available scenarios:")
    for scenario in scenarios:
        print(f"  - {scenario}")


def cmd_preview_voice(args: argparse.Namespace) -> None:
    """Generate a local WAV preview of patient TTS (no Twilio call)."""
    settings = get_settings()
    text = args.text
    if args.scenario:
        scenario = load_scenario(args.scenario)
        text = text or scenario.opening_line

    if not text:
        print("Error: provide --text or --scenario", file=sys.stderr)
        sys.exit(1)

    mulaw = synthesize_speech(
        settings.deepgram_api_key,
        text,
        tts_model=settings.tts_model,
        gain_db=settings.tts_gain_db,
    )
    wav = mulaw_to_wav_bytes(mulaw)

    out_dir = ROOT_DIR / "previews"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / args.output
    out_path.write_bytes(wav)

    duration_s = len(mulaw) / SAMPLE_RATE
    print(f"Saved preview: {out_path}")
    print(f"Duration: {duration_s:.1f}s | gain: {settings.tts_gain_db} dB | model: {settings.tts_model}")
    print(f"Text: {text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Patient voice agent — automated caller for Pretty Good AI assessment"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start webhook + media stream server")
    serve.set_defaults(func=cmd_serve)

    call = subparsers.add_parser("call", help="Place one outbound test call")
    call.add_argument("--scenario", default="schedule_new")
    call.add_argument("--call-id", default="01")
    call.set_defaults(func=cmd_call)

    call_all = subparsers.add_parser(
        "call-all",
        help="Run every scenario one after another (waits for each call to finish)",
    )
    call_all.add_argument(
        "--start-id",
        default="01",
        help="First call ID number (default: 01, then 02, 03, ...)",
    )
    call_all.add_argument(
        "--delay",
        type=int,
        default=10,
        help="Seconds to wait between calls (default: 10)",
    )
    call_all.add_argument(
        "--poll-seconds",
        type=float,
        default=3.0,
        help="How often to check Twilio call status (default: 3)",
    )
    call_all.set_defaults(func=cmd_call_all)

    scenarios = subparsers.add_parser("scenarios", help="List available scenarios")
    scenarios.set_defaults(func=cmd_list_scenarios)

    preview = subparsers.add_parser(
        "preview-voice",
        help="Render patient TTS to a local WAV file (free — no Twilio call)",
    )
    preview.add_argument(
        "--text",
        default="",
        help="Words to speak (default: scenario opening line if --scenario is set)",
    )
    preview.add_argument(
        "--scenario",
        default="",
        help="Use opening line from this scenario when --text is omitted",
    )
    preview.add_argument(
        "--output",
        default="voice-preview.wav",
        help="Output filename inside previews/",
    )
    preview.set_defaults(func=cmd_preview_voice)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    try:
        args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
