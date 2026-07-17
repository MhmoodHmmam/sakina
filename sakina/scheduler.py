"""Multi-zone scheduling.

Deterministic priority arithmetic — same spirit as signals.py: this module
decides which zone the agent looks at next. It never decides what to
conclude about a zone once picked; that judgement still belongs to brain.py,
one zone at a time. Keeping the split means the "which zone next" choice
stays testable and explainable, exactly like the confidence-weighting core.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import config, i18n


@dataclass
class ZoneStatus:
    """What the scheduler remembers about a zone between cycles."""

    zone_id: str
    last_risk: float | None = None
    last_polled: datetime | None = None
    next_poll_s: int = 60

    def priority(self, now: datetime | None = None) -> float:
        """Higher = more urgent to poll next.

        A zone never polled always outranks a polled one — the agent has to
        see every zone at least once before it has any basis to prioritise
        among them. Among never-polled zones, criticality breaks the tie.

        Once a zone has a reading, priority is how overdue it is (elapsed
        time over its own recommended interval) scaled by how risky it last
        looked and how critical the zone is — a zone that came back "risk
        0.65, poll again in 30s" and is now 90s overdue outranks a calm zone
        that is merely a little overdue.
        """
        zone = config.ZONES_BY_ID[self.zone_id]
        crit_weight = zone.criticality / 5
        if self.last_polled is None:
            return 1000.0 + crit_weight
        now = now or datetime.now(timezone.utc)
        elapsed = (now - self.last_polled).total_seconds()
        overdue_ratio = elapsed / max(self.next_poll_s, 1)
        risk_weight = 0.5 + 0.5 * (self.last_risk or 0.0)
        return overdue_ratio * risk_weight * crit_weight


def pick_next_zone(statuses: dict[str, ZoneStatus], now: datetime | None = None) -> str:
    """The agent's own choice of where to look next — never operator-picked."""
    if not statuses:
        raise ValueError("no zones to schedule")
    now = now or datetime.now(timezone.utc)
    return max(statuses, key=lambda zid: statuses[zid].priority(now))


def explain(
    statuses: dict[str, ZoneStatus], chosen: str, now: datetime | None = None, language: str = "en"
) -> str:
    """One-line rationale for the trace — why this zone, not another."""
    now = now or datetime.now(timezone.utc)
    st = statuses[chosen]
    zone = config.ZONES_BY_ID[chosen]
    if st.last_polled is None:
        return i18n.t("scheduler.never_polled", language, crit=zone.criticality)
    elapsed = (now - st.last_polled).total_seconds()
    return i18n.t(
        "scheduler.overdue", language,
        elapsed=elapsed, next_s=st.next_poll_s, risk=st.last_risk or 0.0, crit=zone.criticality,
    )
