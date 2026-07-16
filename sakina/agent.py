"""The agent.

LangGraph StateGraph: PERCEIVE -> ASSESS -> (VERIFY -> ACT) -> REPORT

The conditional edges are the point. The agent decides:
  - whether the evidence warrants spending identity checks (5 API calls)
  - which responders to verify
  - whether to spend a QoD session on each

Nothing here is user-triggered. The operator watches; the agent acts.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from . import brain, config
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
    evidence: dict          # ZoneEvidence.summary()
    evidence_text: str      # rendered block handed to the LLM
    assessment: dict
    identity: list[dict]
    verdict: dict
    actions: list[dict]
    next_poll_s: int
    apis_used: Annotated[list[str], operator.add]


class Sakina:
    def __init__(self, tools: CamaraTools | None = None):
        self.tools = tools or CamaraTools()
        self.graph = self._build()

    # -- nodes ----------------------------------------------------------------

    def _perceive(self, state: AgentState) -> AgentState:
        zone = config.ZONES_BY_ID[state["zone_id"]]
        t = self.tools.trace
        t.phase("PERCEIVE", f"Gathering network signals across {zone.name}")

        sensors = config.devices_in_zone(zone.id, "pilgrim_sensor")
        responders = config.devices_in_zone(zone.id, "responder")
        probes = sensors or responders  # always have something to read

        # Congestion is the primary density proxy — read it from the probe.
        congestion = CongestionRead.parse(self.tools.congestion(probes[0]))

        # Corroborate with position + reachability across the zone's devices.
        locations = [LocationRead.parse(self.tools.locate(d)) for d in probes]
        reach = [ReachabilityRead.parse(self.tools.reachability(d)) for d in probes]

        ev = ZoneEvidence(zone, congestion, locations, reach)
        text = ev.render()

        t.thought(
            "Signals gathered",
            f"{len(t.api_calls())} CAMARA calls · "
            f"congestion weighted mean {congestion.weighted_mean:.2f} "
            f"(naive {congestion.naive_mean:.2f}) · "
            f"telemetry confidence {congestion.confidence_trend}",
        )
        return {
            "evidence": ev.summary(),
            "evidence_text": text,
            "apis_used": ["congestion_insights", "location", "device_status"],
        }

    def _assess(self, state: AgentState) -> AgentState:
        t = self.tools.trace
        t.phase("ASSESS", "Weighing evidence — is this crowd or is this noise?")
        try:
            a = brain.assess_zone(state["evidence_text"], t)
        except brain.LLMUnavailable as exc:
            t.degrade("All model providers unreachable", str(exc))
            a = brain.heuristic_assessment(state["evidence"])

        detail = (
            f"{a.reading}\n\n{a.reasoning}\n\n"
            f"primary driver: {a.primary_driver}"
        )
        if a.contradictions:
            detail += "\ncontradictions: " + "; ".join(a.contradictions)
        t.thought(
            f"Risk {a.risk_score:.2f} ({a.confidence} confidence) · via {a.model}",
            detail,
            payload=a.to_dict(),
        )
        return {"assessment": a.to_dict(), "next_poll_s": a.recommended_poll_s}

    def _verify(self, state: AgentState) -> AgentState:
        """Identity-gate the responders. The agent chose to spend these calls."""
        zone = config.ZONES_BY_ID[state["zone_id"]]
        t = self.tools.trace
        responders = config.devices_in_zone(zone.id, "responder")
        t.phase(
            "VERIFY",
            f"Risk is material — checking identity of {len(responders)} responder(s) "
            f"before considering bandwidth elevation",
        )

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
            if ident.concerns:
                t.thought(
                    f"{d.label} — {len(ident.concerns)} concern(s)",
                    "; ".join(ident.concerns),
                )
            else:
                t.thought(f"{d.label} — identity clean", "no anomalies in network signals")

        return {"identity": out, "apis_used": ["sim_swap", "location", "device_status"]}

    def _decide(self, state: AgentState) -> AgentState:
        t = self.tools.trace
        t.phase("DECIDE", "Gating bandwidth elevation per responder")

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
            verdict = brain.gate_responders("\n".join(blocks), t)
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
                f"{name} → {'ALLOW' if d.get('allow') else 'REFUSE'} "
                f"[{d.get('severity', '?')}]",
                d.get("rationale", ""),
            )
        return {"verdict": verdict}

    def _act(self, state: AgentState) -> AgentState:
        t = self.tools.trace
        t.phase("ACT", "Applying network changes")
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
                f"QoD session for {dev.label}",
                f"profile {config.THRESHOLDS.qod_profile} · status {status} · id {sid}",
                payload=resp,
            )
            actions.append(
                {"phone_number": dev.phone_number, "session_id": sid, "status": status}
            )
        if not actions:
            t.action("No elevations applied", "every candidate was refused or none qualified")
        return {"actions": actions, "apis_used": ["qod"]}

    def _report(self, state: AgentState) -> AgentState:
        t = self.tools.trace
        live, total = t.live_ratio()
        t.phase(
            "REPORT",
            f"Cycle complete · {total} CAMARA calls ({live} live, {total - live} cached) "
            f"across {len(t.apis_touched())} APIs · {t.elapsed_ms:.0f}ms · "
            f"next poll in {state.get('next_poll_s', 60)}s",
        )
        return {}

    # -- edges ----------------------------------------------------------------

    def _after_assess(self, state: AgentState) -> str:
        a = state["assessment"]
        t = self.tools.trace
        score = a["risk_score"]
        if a.get("escalate_identity_check") or score >= config.THRESHOLDS.escalate_at:
            t.decision(
                "Escalate to identity verification",
                f"risk {score:.2f} ≥ {config.THRESHOLDS.escalate_at} "
                f"or model requested pre-emptive check",
            )
            return "verify"
        t.decision(
            "Continue monitoring",
            f"risk {score:.2f} below escalation floor "
            f"{config.THRESHOLDS.escalate_at}; spending no further API budget",
        )
        return "report"

    def _after_decide(self, state: AgentState) -> str:
        a = state["assessment"]
        t = self.tools.trace
        allowed = [d for d in state.get("verdict", {}).get("decisions", []) if d.get("allow")]
        if a["risk_score"] >= config.THRESHOLDS.act_at and allowed:
            t.decision(
                "Proceed to elevation",
                f"risk {a['risk_score']:.2f} ≥ {config.THRESHOLDS.act_at} "
                f"and {len(allowed)} responder(s) cleared",
            )
            return "act"
        reason = (
            f"risk {a['risk_score']:.2f} below action floor {config.THRESHOLDS.act_at}"
            if a["risk_score"] < config.THRESHOLDS.act_at
            else "no responder cleared the identity gate"
        )
        t.decision("Hold — no elevation", reason)
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

    def cycle(self, zone_id: str, trace: Trace | None = None) -> tuple[AgentState, Trace]:
        t = trace or Trace()
        self.tools.bind(t)
        state = self.graph.invoke({"zone_id": zone_id, "apis_used": []})
        return state, t
