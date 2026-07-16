"""Reasoning trace.

The Resource & Tooling Guide says judges love seeing the agent think. So the
trace is not a debug log bolted on afterwards — it is a structured artifact the
agent emits as it works, rendered live in the UI and replayable afterwards.

Every entry answers: what happened, why, what did it cost, was it real.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    PHASE = "phase"  # entered a node in the graph
    API_CALL = "api_call"  # a CAMARA call went out
    THOUGHT = "thought"  # the LLM reasoned
    DECISION = "decision"  # the agent chose a branch
    ACTION = "action"  # a side effect on the network
    DEGRADE = "degrade"  # a fallback fired
    ERROR = "error"


class Source(str, Enum):
    LIVE = "live"  # real Nokia NaC response
    CACHE = "cache"  # recorded fixture (declared, never disguised)
    DERIVED = "derived"  # computed locally


@dataclass
class TraceEvent:
    kind: EventKind
    label: str
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    source: Source | None = None
    api: str | None = None  # e.g. "congestion_insights.query"
    latency_ms: float | None = None
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["source"] = self.source.value if self.source else None
        return d


class Trace:
    """Append-only reasoning record for one agent cycle."""

    def __init__(self, cycle_id: str | None = None) -> None:
        self.cycle_id = cycle_id or uuid.uuid4().hex[:8]
        self.events: list[TraceEvent] = []
        self._t0 = time.time()

    # -- emit -----------------------------------------------------------------

    def add(self, event: TraceEvent) -> TraceEvent:
        self.events.append(event)
        return event

    def phase(self, label: str, detail: str = "") -> TraceEvent:
        return self.add(TraceEvent(EventKind.PHASE, label, detail))

    def api_call(
        self,
        api: str,
        label: str,
        payload: dict,
        source: Source,
        latency_ms: float,
        detail: str = "",
    ) -> TraceEvent:
        return self.add(
            TraceEvent(
                EventKind.API_CALL,
                label,
                detail,
                payload=payload,
                source=source,
                api=api,
                latency_ms=latency_ms,
            )
        )

    def thought(self, label: str, detail: str, payload: dict | None = None) -> TraceEvent:
        return self.add(
            TraceEvent(EventKind.THOUGHT, label, detail, payload=payload or {})
        )

    def decision(self, label: str, detail: str, payload: dict | None = None) -> TraceEvent:
        return self.add(
            TraceEvent(EventKind.DECISION, label, detail, payload=payload or {})
        )

    def action(self, label: str, detail: str, payload: dict | None = None) -> TraceEvent:
        return self.add(
            TraceEvent(EventKind.ACTION, label, detail, payload=payload or {})
        )

    def degrade(self, label: str, detail: str) -> TraceEvent:
        return self.add(TraceEvent(EventKind.DEGRADE, label, detail))

    def error(self, label: str, detail: str) -> TraceEvent:
        return self.add(TraceEvent(EventKind.ERROR, label, detail))

    # -- report ---------------------------------------------------------------

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._t0) * 1000

    def api_calls(self) -> list[TraceEvent]:
        return [e for e in self.events if e.kind is EventKind.API_CALL]

    def apis_touched(self) -> list[str]:
        seen: list[str] = []
        for e in self.api_calls():
            root = (e.api or "").split(".")[0]
            if root and root not in seen:
                seen.append(root)
        return seen

    def live_ratio(self) -> tuple[int, int]:
        """(live calls, total calls) — honesty metric for the demo."""
        calls = self.api_calls()
        live = sum(1 for e in calls if e.source is Source.LIVE)
        return live, len(calls)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "cycle_id": self.cycle_id,
                "elapsed_ms": round(self.elapsed_ms, 1),
                "apis_touched": self.apis_touched(),
                "events": [e.to_dict() for e in self.events],
            },
            indent=indent,
            default=str,
        )

    def render_console(self) -> str:
        """Plain-text trace. Used in the recorded demo's log panel."""
        glyph = {
            EventKind.PHASE: "▶",
            EventKind.API_CALL: "↗",
            EventKind.THOUGHT: "🧠",
            EventKind.DECISION: "◆",
            EventKind.ACTION: "⚡",
            EventKind.DEGRADE: "⚠",
            EventKind.ERROR: "✗",
        }
        lines: list[str] = []
        for e in self.events:
            head = f"{glyph[e.kind]} {e.label}"
            if e.api:
                tag = e.source.value.upper() if e.source else "?"
                head += f"  [{e.api} · {tag} · {e.latency_ms:.0f}ms]"
            lines.append(head)
            if e.detail:
                for line in e.detail.strip().splitlines():
                    lines.append(f"    {line}")
        return "\n".join(lines)
