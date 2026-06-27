from __future__ import annotations

from groq import Groq

from src.config import Settings
from src.scenarios import Scenario, build_system_prompt


class PatientAgent:
    def __init__(self, settings: Settings, scenario: Scenario) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = settings.groq_model
        self._system_prompt = build_system_prompt(scenario)
        self._history: list[dict[str, str]] = []

    def generate_reply(self, agent_text: str) -> str:
        self._history.append({"role": "user", "content": agent_text})
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                *self._history,
            ],
            temperature=0.4,
            max_tokens=60,
        )
        reply = (response.choices[0].message.content or "").strip().strip('"')
        if reply:
            self._history.append({"role": "assistant", "content": reply})
        return reply

    def opening_line(self, scenario: Scenario) -> str:
        return scenario.opening_line

    def record_opening(self, text: str) -> None:
        """Seed history so the LLM knows the opening was already spoken aloud."""
        text = text.strip()
        if text and (
            not self._history or self._history[-1].get("content") != text
        ):
            self._history.append({"role": "assistant", "content": text})
