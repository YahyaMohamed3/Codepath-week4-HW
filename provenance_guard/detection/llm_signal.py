"""Groq semantic assessment signal.

Uses the Groq SDK and the ``llama-3.3-70b-versatile`` model to estimate how
AI-like a passage reads, based purely on writing properties. The prompt tells
the model that detection is uncertain, that authorship must not be inferred from
topic, and that strict JSON with brief reasoning is required.

If Groq is unavailable or returns malformed output, the signal is marked
``available: False`` — it never invents a random score.
"""

from __future__ import annotations

import json
import logging
import re

from ..config import DEFAULT_GROQ_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a careful writing analyst. AI-text detection is inherently "
    "uncertain and false accusations against human writers are harmful. Judge "
    "only the writing properties of the passage (structure, variation, "
    "phrasing, tone). Do NOT infer authorship from the topic or subject matter. "
    "You are estimating likelihood, never proving authorship. Respond with "
    "strict JSON only."
)

USER_PROMPT_TEMPLATE = (
    "Analyze the following passage and estimate how likely it is to be "
    "AI-generated, based only on writing properties such as semantic "
    "organization, overly balanced exposition, generic qualification, "
    "formulaic explanatory language, and consistency of tone.\n\n"
    "Return ONLY strict JSON in exactly this shape:\n"
    "{{\n"
    '  "ai_likelihood": 0.0,\n'
    '  "reasoning": "brief explanation",\n'
    '  "indicators": ["indicator one", "indicator two"]\n'
    "}}\n\n"
    "ai_likelihood must be a number between 0.0 and 1.0. Keep reasoning brief "
    "(one or two sentences); do not include hidden chain-of-thought.\n\n"
    "PASSAGE:\n{passage}"
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _extract_json(raw: str) -> dict:
    """Extract the first JSON object from a model response.

    Raises ``ValueError`` if no valid JSON object can be parsed.
    """
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model response")
    return json.loads(match.group(0))


def parse_response(raw: str) -> dict:
    """Validate and normalize a raw Groq response string.

    Returns an available signal dict. Raises ``ValueError`` on malformed output
    so the caller can mark the signal unavailable.
    """
    data = _extract_json(raw)
    if "ai_likelihood" not in data:
        raise ValueError("missing ai_likelihood in model response")

    likelihood = float(data["ai_likelihood"])
    reasoning = str(data.get("reasoning", "")).strip()
    indicators = data.get("indicators", [])
    if not isinstance(indicators, list):
        indicators = [str(indicators)]
    indicators = [str(i) for i in indicators][:10]

    return {
        "score": round(_clamp(likelihood), 4),
        "available": True,
        "reasoning": reasoning[:500],
        "indicators": indicators,
    }


def _unavailable(reason: str) -> dict:
    return {
        "score": None,
        "available": False,
        "reasoning": reason,
        "indicators": [],
    }


class GroqSemanticSignal:
    """Detector that calls Groq for a semantic AI-likelihood estimate.

    Accepts an optional pre-built ``client`` for dependency injection so tests
    can supply a fake client and never hit the network.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_GROQ_MODEL,
        client=None,
    ) -> None:
        self.model = model
        self._client = client
        self._api_key = api_key

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from groq import Groq  # imported lazily so tests don't need it

            self._client = Groq(api_key=self._api_key)
            return self._client
        except Exception as exc:  # pragma: no cover - import/config failure
            logger.warning("Could not construct Groq client: %s", exc)
            return None

    def analyze(self, text: str) -> dict:
        """Return the semantic signal dict, marking it unavailable on failure."""
        client = self._get_client()
        if client is None:
            return _unavailable("Groq API key not configured.")

        try:
            completion = client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(passage=text),
                    },
                ],
            )
            raw = completion.choices[0].message.content
        except Exception as exc:
            # External-service failure: log and safely translate to unavailable.
            logger.warning("Groq request failed: %s", exc)
            return _unavailable("Groq request failed.")

        try:
            return parse_response(raw)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Groq response could not be parsed: %s", exc)
            return _unavailable("Groq returned malformed output.")
