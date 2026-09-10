"""The reasoning layer.

Primary: Gemini Flash-Lite — config.PRIMARY_MODEL (Google AI Studio free tier).
Fallback: Groq Llama 3.3 70B (free tier) when Gemini rate-limits.
Both appear in the AI Resource & Tooling Guide. No other model providers.

Design rule: the LLM is asked to *weigh evidence*, not to compute. Arithmetic
happens in signals.py, where it is deterministic and testable. The model's job
is the part that is genuinely judgement: reconciling signals that disagree.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import config
from .trace import Trace


class LLMUnavailable(RuntimeError):
    pass


# --- Providers ---------------------------------------------------------------


def _call_gemini(system: str, user: str) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMUnavailable("no GEMINI_API_KEY")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=config.PRIMARY_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return resp.text or ""


def _call_groq(system: str, user: str) -> str:
    if not config.GROQ_API_KEY:
        raise LLMUnavailable("no GROQ_API_KEY")
    from groq import Groq

    client = Groq(api_key=config.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=config.FALLBACK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def reason(system: str, user: str, trace: Trace, label: str) -> dict:
    """Ask the model, with provider fallback. Never raises on rate limit."""
    for name, fn in (("gemini", _call_gemini), ("groq", _call_groq)):
        try:
            raw = fn(system, user)
            data = _extract_json(raw)
            data["_model"] = name
            return data
        except LLMUnavailable:
            continue
        except Exception as exc:
            trace.degrade(
                f"{name} unavailable",
                f"{label}: {type(exc).__name__}: {exc} — trying next provider",
            )
            continue
    raise LLMUnavailable("no model provider reachable")


# --- Prompts -----------------------------------------------------------------

ASSESS_SYSTEM = """\
You are SAKINA, a crowd-safety analyst for mass religious gatherings (Hajj, Umrah).
You reason over live telecom network signals from CAMARA APIs. Lives depend on
your calibration in both directions: a missed crush kills people, and a false
alarm that empties a bridge into a bottleneck also kills people.

WHAT YOU ARE LOOKING AT
Mobile network congestion is a *proxy* for crowd density — more handsets in a
cell means more contention. It is an indirect and noisy proxy. Each congestion
reading carries a confidenceLevel (0-100) telling you how much the network
trusts its own measurement.

THE DISTINCTION THAT MATTERS MOST
When congestion appears to drop, there are two very different explanations:
  (a) the crowd genuinely dispersed          -> risk falling, stand down
  (b) telemetry degraded and you are blind   -> risk UNKNOWN, escalate watch
Use the confidence trend to tell these apart. Congestion falling while
confidence *improves* supports (a). Congestion falling while confidence
*degrades* is consistent with (b) and must not be read as good news.

CORROBORATION
- Devices dropping to SMS-only means the data plane is saturated. That supports
  a genuine density reading, independent of the congestion metric.
- Stale location fixes mean the network is struggling to position handsets —
  itself a mild congestion signal, and a reason to distrust position data.
- A coarse location radius (e.g. 1000m) is not a position. Do not reason as if
  it were.

CALIBRATION
- High volatility with low confidence = insufficient evidence, not high risk.
  Say so. Recommend a shorter polling interval instead of an intervention.
- A single trustworthy reading beats three noisy ones.
- Zone criticality (1-5) scales consequence, not probability. A 5 means be
  quicker to escalate for a given risk level — it does not mean the risk is
  higher.

OUTPUT
Return ONLY a JSON object:
{
  "risk_score": 0.0-1.0,
  "confidence": "low" | "medium" | "high",
  "reading": "one sentence: what is actually happening in this zone",
  "reasoning": "2-4 sentences. Cite specific numbers. State explicitly whether
                any apparent change is real or a telemetry artefact.",
  "primary_driver": "the single signal carrying the most weight",
  "contradictions": ["signals that disagree with your conclusion, if any"],
  "recommended_poll_s": 30-300,
  "escalate_identity_check": true | false
}
Set escalate_identity_check true when risk is material enough that you may need
to elevate responder bandwidth shortly — identity verification takes time, so
start it before you need the answer.
"""

VERDICT_SYSTEM = """\
You are SAKINA's action gate. A zone has been assessed as elevated risk, and
responder devices have been checked against network identity signals.

You decide whether each responder may receive prioritised network bandwidth
(a CAMARA Quality-on-Demand session).

WHY THIS GATE EXISTS
Whoever can trigger QoD elevation controls emergency bandwidth allocation at a
mass gathering. That is worth attacking. A responder handset whose SIM was
swapped hours before an event, roaming on a foreign network, whose position the
network cannot confirm, is not a responder you should trust with priority
spectrum — it is a plausible impersonation.

BUT
Refusing a real medic during a real crush also kills people. Weigh the concerns
against the operational cost of refusal. Not every anomaly is an attack:
- Roaming alone is weak evidence. Pilgrims and international medical teams roam
  by definition. Hajj is the largest roaming event on earth.
- A SIM swap alone is weak-to-moderate. People break phones.
- A SIM swap PLUS unconfirmed position PLUS roaming, within hours of a mass
  gathering, is a coherent attack pattern and should be refused.
- Location verification returning FALSE while the device claims to be a
  responder in that zone is the strongest single signal available to you.

If a device is SMS-only, note that QoD elevation is likely futile — there is no
data session to prioritise. That is an operational fact, not a trust question.

OUTPUT
Return ONLY a JSON object:
{
  "decisions": [
    {
      "phone_number": "...",
      "allow": true | false,
      "rationale": "1-2 sentences citing the specific signals",
      "severity": "clear" | "caution" | "block"
    }
  ],
  "summary": "one sentence on the overall responder posture in this zone"
}
"""


# --- Callable wrappers -------------------------------------------------------


@dataclass
class Assessment:
    risk_score: float
    confidence: str
    reading: str
    reasoning: str
    primary_driver: str
    contradictions: list[str]
    recommended_poll_s: int
    escalate_identity_check: bool
    model: str

    @classmethod
    def from_json(cls, d: dict) -> Assessment:
        return cls(
            risk_score=float(d.get("risk_score", 0.0)),
            confidence=str(d.get("confidence", "low")),
            reading=str(d.get("reading", "")),
            reasoning=str(d.get("reasoning", "")),
            primary_driver=str(d.get("primary_driver", "")),
            contradictions=list(d.get("contradictions", []) or []),
            recommended_poll_s=int(d.get("recommended_poll_s", 60)),
            escalate_identity_check=bool(d.get("escalate_identity_check", False)),
            model=str(d.get("_model", "?")),
        )

    def to_dict(self) -> dict:
        return {
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "reading": self.reading,
            "reasoning": self.reasoning,
            "primary_driver": self.primary_driver,
            "contradictions": self.contradictions,
            "recommended_poll_s": self.recommended_poll_s,
            "escalate_identity_check": self.escalate_identity_check,
            "model": self.model,
        }


_ARABIC_DIRECTIVE = """

RESPONSE LANGUAGE: Modern Standard Arabic (Fusha). Translate every narrative
field into Arabic — reading, reasoning, primary_driver, contradictions,
rationale, summary. Keep the JSON keys themselves in English exactly as
specified. Numbers stay as numbers. Two fields are structural control
values, not narrative — keep them as the exact English tokens given, do NOT
translate them: confidence must be exactly "low", "medium", or "high";
severity must be exactly "clear", "caution", or "block"."""


def _localize(system: str, language: str) -> str:
    return system + _ARABIC_DIRECTIVE if language == "ar" else system


def assess_zone(evidence_text: str, trace: Trace, language: str = "en") -> Assessment:
    """Ask the model, then validate the shape it handed back.

    reason() already retries malformed *JSON* (a parse failure) against the
    next provider. But valid JSON with the wrong field types — risk_score as
    the string "high" instead of a float — parses fine and only breaks here,
    at Assessment.from_json()'s float()/int()/bool() coercion. Route that
    failure through the same LLMUnavailable path agent.py already handles
    (heuristic fallback, degrade logged in the trace) instead of letting a
    ValueError crash the whole cycle.
    """
    d = reason(_localize(ASSESS_SYSTEM, language), evidence_text, trace, "assess")
    try:
        return Assessment.from_json(d)
    except (TypeError, ValueError) as exc:
        trace.degrade("assess response malformed", f"{type(exc).__name__}: {exc}")
        raise LLMUnavailable(f"malformed assessment shape: {exc}") from exc


def gate_responders(evidence_text: str, trace: Trace, language: str = "en") -> dict:
    """Ask the model for a verdict, then validate the shape before use.

    _decide() iterates verdict["decisions"] expecting a list of dicts. A model
    that returns valid JSON with "decisions" as something else (a string, a
    single object) would otherwise crash that loop with an uncaught
    AttributeError/TypeError. Fail the same way a missing model does instead.
    """
    d = reason(_localize(VERDICT_SYSTEM, language), evidence_text, trace, "verdict")
    decisions = d.get("decisions")
    if not isinstance(decisions, list) or not all(isinstance(x, dict) for x in decisions):
        trace.degrade(
            "verdict response malformed",
            f"expected decisions: list[dict], got {type(decisions).__name__}",
        )
        raise LLMUnavailable("malformed verdict shape: decisions is not a list of objects")
    return d


# --- Deterministic fallback --------------------------------------------------


def heuristic_assessment(summary: dict) -> Assessment:
    """Used only when every model provider is unreachable.

    Deliberately conservative and deliberately worse than the LLM — its job is
    to keep the demo alive, and to make the delta visible. A rule engine cannot
    tell dispersal from blindness; it just reports the number.
    """
    c = summary.get("congestion", {})
    wm = float(c.get("weighted_mean", 0.0))
    vol = float(c.get("volatility", 0.0))
    crit = int(summary.get("criticality", 3))
    score = min(1.0, (wm / 2.0) * 0.7 + (crit / 5.0) * 0.3)
    return Assessment(
        risk_score=round(score, 2),
        confidence="low",
        reading="Heuristic fallback — no model provider reachable.",
        reasoning=(
            f"Confidence-weighted congestion {wm:.2f}/2.0, volatility {vol:.2f}, "
            f"zone criticality {crit}/5. This is threshold arithmetic only: it "
            f"cannot distinguish genuine dispersal from telemetry loss."
        ),
        primary_driver="weighted congestion mean",
        contradictions=["no semantic reasoning available in fallback mode"],
        recommended_poll_s=45,
        escalate_identity_check=score >= config.THRESHOLDS.escalate_at,
        model="heuristic",
    )
