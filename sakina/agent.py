"""The agent.

LangGraph StateGraph: PERCEIVE -> ASSESS -> (VERIFY -> DECIDE) -> ACT -> REPORT

The conditional edges are the point. The agent decides:
  - whether the evidence warrants spending identity checks (5 extra API calls)
  - which responders to verify
  - whether to spend a QoD session on each

Nothing here is user-triggered. The operator watches; the agent acts.

The trace is bilingual: every phase/thought/decision/action label goes through
i18n.t() against state["language"]. The model's own narrative text (reading,
reasoning, rationale, ...) is localized separately, at generation time, by
brain.py's Arabic directive — that's judgement-language, not UI-language, and
the two are deliberately kept apart.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from . import brain, config, i18n
from .camara import CamaraTools
from .signals import (
    CongestionRead,
    LocationRead,
    ReachabilityRead,
    ZoneEvidence,
    parse_identity,
)
from .trace import Trace


class AgentState(TypedDict, total=False):
    zone_id: str
    language: str            # "en" | "ar" — set once per cycle, read everywhere
    evidence: dict          # ZoneEvidence.summary()
    evidence_text: str      # rendered block handed to the LLM
    assessment: dict
    identity: list[dict]
    verdict: dict
    actions: list[dict]
    next_poll_s: int
    apis_used: Annotated[list[str], operator.add]


def _describe_concerns(ident, lang: str) -> list[str]:
    """Human-facing concern phrases in the selected language.

    Rebuilt from IdentityRead's raw fields rather than reusing
    IdentityRead.concerns (signals.py's English list) — that list is also
    used as model input elsewhere and stays English on purpose; this is the
    separate, display-only rendering for the operator's trace panel.
    """
    out: list[str] = []
    if ident.swapped:
        age = ident.swap_age_h
        if age is not None:
            out.append(i18n.t("concern.sim_swapped_aged", lang, age=f"{age:.1f}"))
        else:
            out.append(i18n.t("concern.sim_swapped_recent", lang))
    if ident.roaming:
        if ident.country:
            out.append(i18n.t("concern.roaming", lang, country=ident.country))
        else:
            out.append(i18n.t("concern.roaming_unknown", lang))
    if ident.location_verified == "FALSE":
        out.append(i18n.t("concern.location_false", lang))
    elif ident.location_verified == "UNKNOWN":
        out.append(i18n.t("concern.location_unknown", lang))
    return out


class Sakina:
    def __init__(self, tools: CamaraTools | None = None):
        self.tools = tools or CamaraTools()
        self.graph = self._build()

    # -- nodes ----------------------------------------------------------------

    def _perceive(self, state: AgentState) -> AgentState:
        lang = state.get("language", "en")
        zone = config.ZONES_BY_ID[state["zone_id"]]
        t = self.tools.trace
        t.phase(i18n.t("phase.perceive", lang), i18n.t("phase.perceive.detail", lang, zone=zone.name))

        sensors = config.devices_in_zone(zone.id, "pilgrim_sensor")
        responders = config.devices_in_zone(zone.id, "responder")
        probes = sensors or responders
        if not probes:
            raise ValueError(f"zone {zone.id} has no assigned devices to observe")

        # Congestion is the primary density proxy — read it from the probe.
        congestion = CongestionRead.parse(self.tools.congestion(probes[0]))

        # Corroborate with position + reachability across the zone's devices.
        locations = [LocationRead.parse(self.tools.locate(d)) for d in probes]
        reach = [ReachabilityRead.parse(self.tools.reachability(d)) for d in probes]

        ev = ZoneEvidence(zone, congestion, locations, reach)
        text = ev.render()

        t.thought(
            i18n.t("perceive.gathered", lang),
            i18n.t(
                "perceive.summary", lang,
                n=len(t.api_calls()),
                wm=f"{congestion.weighted_mean:.2f}",
                nm=f"{congestion.naive_mean:.2f}",
                trend=i18n.trend_label(congestion.confidence_trend, lang),
            ),
        )
        return {
            "evidence": ev.summary(),
            "evidence_text": text,
            "apis_used": ["congestion_insights", "location", "device_status"],
        }

    def _assess(self, state: AgentState) -> AgentState:
        lang = state.get("language", "en")
        t = self.tools.trace
        t.phase(i18n.t("phase.assess", lang), i18n.t("phase.assess.detail", lang))
        try:
            a = brain.assess_zone(state["evidence_text"], t, language=lang)
        except brain.LLMUnavailable as exc:
            t.degrade("All model providers unreachable", str(exc))
            a = brain.heuristic_assessment(state["evidence"])

        detail = f"{a.reading}\n\n{a.reasoning}\n\n" + i18n.t("assess.primary_driver", lang, driver=a.primary_driver)
        if a.contradictions:
            detail += "\n" + i18n.t("assess.contradictions", lang, items="; ".join(a.contradictions))
        t.thought(
            i18n.t(
                "assess.risk_label", lang,
                score=f"{a.risk_score:.2f}",
                confidence=i18n.confidence_label(a.confidence, lang),
                model=a.model,
            ),
            detail,
            payload=a.to_dict(),
        )
        return {"assessment": a.to_dict(), "next_poll_s": a.recommended_poll_s}

    def _verify(self, state: AgentState) -> AgentState:
        """Identity-gate the responders. The agent chose to spend these calls."""
        lang = state.get("language", "en")
        zone = config.ZONES_BY_ID[state["zone_id"]]
        t = self.tools.trace
        responders = config.devices_in_zone(zone.id, "responder")
        t.phase(i18n.t("phase.verify", lang), i18n.t("phase.verify.detail", lang, n=len(responders)))

        out: list[dict] = []
        for d in responders:
            ident = parse_identity(
                self.tools.sim_swapped(d),
                self.tools.sim_swap_date(d),
                self.tools.roaming(d),
                self.tools.verify_in_zone(d, zone),
            )
            reach = ReachabilityRead.parse(self.tools.reachability(d))
            rec = {
                "phone_number": d.phone_number,
                "label": d.label,
                "identity": ident.summary(),
                "reachability": reach.summary(),
            }
            out.append(rec)
            concerns = _describe_concerns(ident, lang)
            if concerns:
                t.thought(
                    i18n.t("verify.concerns", lang, label=d.label, n=len(concerns)),
                    "; ".join(concerns),
                )
            else:
                t.thought(
                    i18n.t("verify.clean_label", lang, label=d.label),
                    i18n.t("verify.clean_detail", lang),
                )

        return {"identity": out, "apis_used": ["sim_swap", "location", "device_status"]}

    def _decide(self, state: AgentState) -> AgentState:
        lang = state.get("language", "en")
        t = self.tools.trace
        t.phase(i18n.t("phase.decide", lang), i18n.t("phase.decide.detail", lang))

        a = state["assessment"]
        blocks: list[str] = [
            f"ZONE RISK: {a['risk_score']:.2f} ({a['confidence']} confidence)",
            f"READING: {a['reading']}",
            "",
            "RESPONDERS:",
        ]
        for r in state.get("identity", []):
            i = r["identity"]
            blocks.append(f"\n{r['label']}  ({r['phone_number']})")
            blocks.append(f"  SIM swapped: {i['swapped']}"
                          + (f" ({i['swap_age_h']}h ago)" if i.get("swap_age_h") else ""))
            blocks.append(f"  roaming: {i['roaming']} ({i.get('country') or 'n/a'})")
            blocks.append(f"  location verification: {i.get('location_verified')}")
            blocks.append(f"  connectivity: {r['reachability']['connectivity']} "
                          f"(data capable: {r['reachability']['data_capable']})")
            blocks.append(f"  concerns: {i['concerns'] or 'none'}")

        try:
            verdict = brain.gate_responders("\n".join(blocks), t, language=lang)
        except brain.LLMUnavailable:
            # Fail closed: no model, no elevation. Refusing is recoverable;
            # handing an impersonator priority spectrum is not.
            t.degrade(
                "No model for gating decision",
                "failing closed — no elevation without a reasoned verdict",
            )
            verdict = {
                "decisions": [
                    {
                        "phone_number": r["phone_number"],
                        "allow": False,
                        "rationale": "no reasoning available; defaulting to refuse",
                        "severity": "caution",
                    }
                    for r in state.get("identity", [])
                ],
                "summary": "Gating unavailable — all elevations withheld.",
            }

        for d in verdict.get("decisions", []):
            dev = config.DEVICES_BY_NUMBER.get(d.get("phone_number", ""))
            name = dev.label if dev else d.get("phone_number")
            t.decision(
                i18n.t(
                    "decide.verdict_label", lang,
                    name=name,
                    verdict=i18n.verdict_label(bool(d.get("allow")), lang),
                    severity=i18n.severity_label(d.get("severity", "?"), lang),
                ),
                d.get("rationale", ""),
            )
        return {"verdict": verdict}

    def _act(self, state: AgentState) -> AgentState:
        lang = state.get("language", "en")
        t = self.tools.trace
        t.phase(i18n.t("phase.act", lang), i18n.t("phase.act.detail", lang))
        actions: list[dict] = []
        for d in state.get("verdict", {}).get("decisions", []):
            if not d.get("allow"):
                continue
            dev = config.DEVICES_BY_NUMBER.get(d.get("phone_number", ""))
            if not dev:
                continue
            resp = self.tools.elevate_qod(dev)
            sid = resp.get("sessionId") or resp.get("session_id")
            status = resp.get("qosStatus") or resp.get("qos_status")
            t.action(
                i18n.t("act.qod_session", lang, label=dev.label),
                i18n.t("act.qod_detail", lang, profile=config.THRESHOLDS.qod_profile, status=status, sid=sid),
                payload=resp,
            )
            actions.append(
                {"phone_number": dev.phone_number, "session_id": sid, "status": status}
            )
        if not actions:
            t.action(i18n.t("act.none_applied", lang), i18n.t("act.none_applied_detail", lang))
        return {"actions": actions, "apis_used": ["qod"]}

    def _report(self, state: AgentState) -> AgentState:
        lang = state.get("language", "en")
        t = self.tools.trace
        live, total = t.live_ratio()
        t.phase(
            i18n.t("phase.report", lang),
            i18n.t(
                "report.summary", lang,
                total=total, live=live, cached=total - live,
                n=len(t.apis_touched()), ms=f"{t.elapsed_ms:.0f}",
                s=state.get("next_poll_s", 60),
            ),
        )
        return {}

    # -- edges ----------------------------------------------------------------

    def _after_assess(self, state: AgentState) -> str:
        lang = state.get("language", "en")
        a = state["assessment"]
        t = self.tools.trace
        score = a["risk_score"]
        if a.get("escalate_identity_check") or score >= config.THRESHOLDS.escalate_at:
            t.decision(
                i18n.t("assess.escalate", lang),
                i18n.t("assess.escalate.detail", lang, score=f"{score:.2f}", threshold=config.THRESHOLDS.escalate_at),
            )
            return "verify"
        t.decision(
            i18n.t("assess.continue", lang),
            i18n.t("assess.continue.detail", lang, score=f"{score:.2f}", threshold=config.THRESHOLDS.escalate_at),
        )
        return "report"

    def _after_decide(self, state: AgentState) -> str:
        lang = state.get("language", "en")
        a = state["assessment"]
        t = self.tools.trace
        allowed = [d for d in state.get("verdict", {}).get("decisions", []) if d.get("allow")]
        if a["risk_score"] >= config.THRESHOLDS.act_at and allowed:
            t.decision(
                i18n.t("decide.proceed", lang),
                i18n.t(
                    "decide.proceed.detail", lang,
                    score=f"{a['risk_score']:.2f}", threshold=config.THRESHOLDS.act_at, n=len(allowed),
                ),
            )
            return "act"
        reason = (
            i18n.t("decide.hold_low_risk", lang, score=f"{a['risk_score']:.2f}", threshold=config.THRESHOLDS.act_at)
            if a["risk_score"] < config.THRESHOLDS.act_at
            else i18n.t("decide.hold_none_cleared", lang)
        )
        t.decision(i18n.t("decide.hold", lang), reason)
        return "report"

    # -- build ----------------------------------------------------------------

    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("perceive", self._perceive)
        g.add_node("assess", self._assess)
        g.add_node("verify", self._verify)
        g.add_node("decide", self._decide)
        g.add_node("act", self._act)
        g.add_node("report", self._report)

        g.set_entry_point("perceive")
        g.add_edge("perceive", "assess")
        g.add_conditional_edges(
            "assess", self._after_assess, {"verify": "verify", "report": "report"}
        )
        g.add_edge("verify", "decide")
        g.add_conditional_edges(
            "decide", self._after_decide, {"act": "act", "report": "report"}
        )
        g.add_edge("act", "report")
        g.add_edge("report", END)
        return g.compile()

    # -- run ------------------------------------------------------------------

    def cycle(self, zone_id: str, trace: Trace | None = None, language: str = "en") -> tuple[AgentState, Trace]:
        t = trace or Trace()
        self.tools.bind(t)
        self.tools.language = language
        state = self.graph.invoke({"zone_id": zone_id, "apis_used": [], "language": language})
        return state, t
