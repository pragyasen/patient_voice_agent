from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from src.config import SCENARIOS_DIR, TRANSCRIPTS_DIR


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    goal: str
    opening_line: str
    persona_notes: str
    edge_case_hints: str
    persona_override: str = ""


PATIENT_NAME = "Pragya Sen"
PATIENT_DOB = "June 4, 2001"
PATIENT_CLINIC = "Pivot Point Orthopedics"

BASE_PERSONA = f"""You are {PATIENT_NAME}, a real patient calling {PATIENT_CLINIC} on the phone.
Your date of birth is {PATIENT_DOB}, but do NOT say it unless the agent explicitly asks for your date of birth or DOB.
You are NOT an AI assistant. You are the patient on the call.

Clinic system context:
- You are NOT already in their system at the start of this call. They do not have your patient profile, chart, or records on file yet.
- Do not say you are an existing patient or that they should already have your information unless the scenario says otherwise.
- The agent may ask to create a "demo patient profile" before they can help you. That is normal on this line - say yes and cooperate unless the specific scenario you're in has explicitly said not to (for example, in the unauthorized_records_access scenario).
- When setting up the profile, give your name when they ask for your name. Give your date of birth only when they ask for DOB or date of birth.

Rules:
- Speak in short, natural phone sentences. Usually ONE sentence per turn.
- Answer ONLY the agent's latest question. Do not repeat your whole story.
- Do not repeat information you already said earlier in this call, especially in your opening line unless explicitly asked.
- Let the agent finish speaking before you reply. If they are still explaining something, wait.
- If the agent gives a short acknowledgment like "Great" or "May I help?", reply briefly in one short sentence.
- Be polite and realistic. Use casual phrasing like "yeah", "um", "okay" sparingly.
- Give your name only when asked for your name. Give your date of birth only when asked for DOB or date of birth.
- Never volunteer personal details the agent did not ask for.
- Do not invent doctor names, prior visits, or medical records the agent has not mentioned.
- If you do not know something, say you are not sure or ask the agent to check - do not make up an answer.
- If you already spelled or answered something and they ask again, repeat it once calmly - do not loop the same answer more than twice.
- Stay focused on your goal for this call but respond naturally to the agent.
- Speak at a relaxed, conversational pace. Do not rush or sound like you are reading a script.
- Do not mention testing, bots, demo systems, or AI.
- Never produce bullet points, stage directions, or labels like "Patient:".
- Output ONLY the words you would say out loud on the phone."""


def resolve_scenario_id(scenario_id: str) -> str:
    """Map a scenario id (or shorthand) to an existing YAML stem."""
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if path.exists():
        return scenario_id

    prefix_matches = sorted(
        p.stem
        for p in SCENARIOS_DIR.glob("*.yaml")
        if p.stem.startswith(scenario_id)
    )
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    available = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))
    hint = ""
    if prefix_matches:
        hint = f" Did you mean one of: {', '.join(prefix_matches)}?"
    raise FileNotFoundError(
        f"Scenario '{scenario_id}' not found.{hint} Available: {', '.join(available)}"
    )


def load_scenario(scenario_id: str) -> Scenario:
    scenario_id = resolve_scenario_id(scenario_id)
    path = SCENARIOS_DIR / f"{scenario_id}.yaml"

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Scenario(
        id=scenario_id,
        name=data["name"],
        goal=data["goal"],
        opening_line=data["opening_line"],
        persona_notes=data.get("persona_notes", ""),
        edge_case_hints=data.get("edge_case_hints", ""),
        persona_override=data.get("persona_override", ""),
    )


def build_system_prompt(scenario: Scenario) -> str:
    persona = scenario.persona_override.strip() or BASE_PERSONA
    parts = [
        persona,
        f"\nScenario: {scenario.name}",
        f"Your goal for this call: {scenario.goal}",
    ]
    if scenario.persona_notes:
        parts.append(f"Additional context: {scenario.persona_notes}")
    if scenario.edge_case_hints:
        parts.append(f"Testing note (do not say this aloud): {scenario.edge_case_hints}")
    return "\n".join(parts)


@dataclass
class TranscriptWriter:
    call_id: str
    scenario_id: str
    path: Path
    _started_at: datetime

    @classmethod
    def create(cls, call_id: str, scenario_id: str) -> TranscriptWriter:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = TRANSCRIPTS_DIR / f"call-{call_id}.txt"
        writer = cls(
            call_id=call_id,
            scenario_id=scenario_id,
            path=path,
            _started_at=datetime.now(timezone.utc),
        )
        writer.path.write_text(
            f"# Call {call_id} | Scenario: {scenario_id}\n"
            f"# Started: {writer._started_at.isoformat()}\n\n",
            encoding="utf-8",
        )
        return writer

    def _elapsed(self) -> str:
        delta = datetime.now(timezone.utc) - self._started_at
        total_seconds = int(delta.total_seconds())
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def append(self, speaker: Literal["AGENT", "PATIENT"], text: str) -> None:
        line = f"[{self._elapsed()}] {speaker}: {text.strip()}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
