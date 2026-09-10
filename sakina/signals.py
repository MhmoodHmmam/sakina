"""Signal interpretation.

This module does the arithmetic. It deliberately does NOT decide anything —
it prepares evidence for the LLM to weigh. The separation matters: judges score
"AI agent design that intelligently orchestrates CAMARA APIs", and a system
where a threshold function makes the call and the LLM writes the press release
is not that.

The central idea: congestion readings arrive with a confidenceLevel. A "High"
at 51% confidence and a "Low" at 97% are not comparable facts. Treating them as
equal is the mistake every rule engine makes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .config import CONGESTION_ORDINAL, THRESHOLDS, Zone


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _get(d: dict, *names: str, default: Any = None) -> Any:
    """Field access tolerant of camelCase (wire) vs snake_case (SDK)."""
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default


# --- Congestion --------------------------------------------------------------


@dataclass
class CongestionBucket:
    start: datetime | None
    stop: datetime | None
    level: str
    confidence: int

    @property
    def ordinal(self) -> int:
        return CONGESTION_ORDINAL.get(self.level, 0)

    @property
    def trustworthy(self) -> bool:
        return self.confidence >= THRESHOLDS.min_confidence

    def describe(self) -> str:
        when = self.start.strftime("%H:%M") if self.start else "??:??"
        flag = "" if self.trustworthy else "  <- below trust floor"
        return f"{when}  {self.level:<6} confidence {self.confidence:>3}%{flag}"


@dataclass
class CongestionRead:
    """A time-ordered congestion window, with the honest caveats attached."""

    buckets: list[CongestionBucket]

    @classmethod
    def parse(cls, raw: list[dict]) -> CongestionRead:
        out: list[CongestionBucket] = []
        for b in raw or []:
            out.append(
                CongestionBucket(
                    start=_parse_ts(_get(b, "timeIntervalStart", "time_interval_start")),
                    stop=_parse_ts(_get(b, "timeIntervalStop", "time_interval_stop")),
                    level=str(_get(b, "congestionLevel", "congestion_level", default="Low")),
                    confidence=int(_get(b, "confidenceLevel", "confidence_level", default=0)),
                )
            )
        out.sort(key=lambda b: b.start or datetime.min.replace(tzinfo=UTC))
        return cls(out)

    # -- derived views --------------------------------------------------------

    @property
    def latest(self) -> CongestionBucket | None:
        return self.buckets[-1] if self.buckets else None

    @property
    def weighted_mean(self) -> float:
        """Confidence-weighted mean congestion ordinal (0=Low .. 2=High).

        Low-confidence buckets pull the mean less. This is the number a naive
        implementation would compute as a plain average and get wrong.
        """
        num = sum(b.ordinal * b.confidence for b in self.buckets)
        den = sum(b.confidence for b in self.buckets)
        return (num / den) if den else 0.0

    @property
    def naive_mean(self) -> float:
        """Unweighted mean — kept to show the delta in the trace/demo."""
        if not self.buckets:
            return 0.0
        return sum(b.ordinal for b in self.buckets) / len(self.buckets)

    @property
    def volatility(self) -> float:
        """Mean absolute step between consecutive levels. High = unstable read."""
        if len(self.buckets) < 2:
            return 0.0
        steps = [
            abs(self.buckets[i].ordinal - self.buckets[i - 1].ordinal)
            for i in range(1, len(self.buckets))
        ]
        return sum(steps) / len(steps)

    @property
    def confidence_trend(self) -> str:
        """Is our telemetry getting better or worse?

        This distinguishes 'the crowd left' from 'we stopped being able to see
        the crowd' — the distinction the whole agent exists to make.
        """
        if len(self.buckets) < 2:
            return "unknown"
        first = self.buckets[0].confidence
        last = self.buckets[-1].confidence
        if last - first > 20:
            return "improving"
        if first - last > 20:
            return "degrading"
        return "stable"

    @property
    def trusted_only(self) -> list[CongestionBucket]:
        return [b for b in self.buckets if b.trustworthy]

    def summary(self) -> dict:
        return {
            "buckets": len(self.buckets),
            "trusted_buckets": len(self.trusted_only),
            "latest_level": self.latest.level if self.latest else None,
            "latest_confidence": self.latest.confidence if self.latest else None,
            "weighted_mean": round(self.weighted_mean, 3),
            "naive_mean": round(self.naive_mean, 3),
            "volatility": round(self.volatility, 3),
            "confidence_trend": self.confidence_trend,
        }

    def render(self) -> str:
        """Human/LLM-readable evidence block, oldest first."""
        if not self.buckets:
            return "  (no congestion data)"
        lines = [b.describe() for b in self.buckets]
        lines.append("")
        lines.append(
            f"  confidence-weighted mean: {self.weighted_mean:.2f} "
            f"(naive mean {self.naive_mean:.2f})"
        )
        lines.append(f"  volatility: {self.volatility:.2f}   "
                     f"telemetry confidence is {self.confidence_trend}")
        return "\n".join(lines)


# --- Location ----------------------------------------------------------------


@dataclass
class LocationRead:
    latitude: float | None
    longitude: float | None
    radius_m: int | None
    last_seen: datetime | None

    @classmethod
    def parse(cls, raw: dict) -> LocationRead:
        area = _get(raw or {}, "area", default={}) or {}
        centre = _get(area, "center", "centre", default={}) or {}
        return cls(
            latitude=_get(centre, "latitude"),
            longitude=_get(centre, "longitude"),
            radius_m=_get(area, "radius"),
            last_seen=_parse_ts(_get(raw or {}, "lastLocationTime", "last_location_time")),
        )

    @property
    def age_s(self) -> float | None:
        if not self.last_seen:
            return None
        return (datetime.now(UTC) - self.last_seen).total_seconds()

    @property
    def stale(self) -> bool:
        a = self.age_s
        return a is None or a > THRESHOLDS.stale_after_s

    @property
    def precision_note(self) -> str:
        """Radius is a fix-quality signal — a 1km circle is not a position."""
        if self.radius_m is None:
            return "unknown precision"
        if self.radius_m <= 200:
            return "fine fix"
        if self.radius_m <= 1000:
            return "coarse fix"
        return "very coarse fix"

    def summary(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_m": self.radius_m,
            "age_s": round(self.age_s, 1) if self.age_s is not None else None,
            "stale": self.stale,
            "precision": self.precision_note,
        }


# --- Reachability ------------------------------------------------------------


@dataclass
class ReachabilityRead:
    reachable: bool
    connectivity: list[str]
    last_seen: datetime | None

    @classmethod
    def parse(cls, raw: dict) -> ReachabilityRead:
        conn = _get(raw or {}, "connectivity", default=[]) or []
        return cls(
            reachable=bool(_get(raw or {}, "reachable", default=False)),
            connectivity=[str(c) for c in conn],
            last_seen=_parse_ts(_get(raw or {}, "lastStatusTime", "last_status_time")),
        )

    @property
    def data_capable(self) -> bool:
        return any(c.upper() == "DATA" for c in self.connectivity)

    @property
    def sms_only(self) -> bool:
        """Reachable but no data path.

        In a crowd context this is a corroborating density signal: handsets fall
        back to SMS when the data plane is saturated. It is also the reason a
        QoD elevation may be futile — you cannot prioritise a data session on a
        device that has no data session.
        """
        return self.reachable and not self.data_capable

    def summary(self) -> dict:
        return {
            "reachable": self.reachable,
            "connectivity": self.connectivity,
            "data_capable": self.data_capable,
            "sms_only": self.sms_only,
        }


# --- Identity ----------------------------------------------------------------


@dataclass
class IdentityRead:
    swapped: bool
    swap_time: datetime | None
    roaming: bool
    country: str | None
    location_verified: str | None  # TRUE / FALSE / PARTIAL / UNKNOWN

    @property
    def swap_age_h(self) -> float | None:
        if not self.swap_time:
            return None
        return (datetime.now(UTC) - self.swap_time).total_seconds() / 3600

    @property
    def concerns(self) -> list[str]:
        """Plain-language risk flags. The LLM weighs these; it does not get a verdict."""
        out: list[str] = []
        if self.swapped:
            age = self.swap_age_h
            when = f"{age:.1f}h ago" if age is not None else "recently"
            out.append(f"SIM was swapped {when}")
        if self.roaming:
            out.append(f"device is roaming ({self.country or 'unknown network'})")
        if self.location_verified == "FALSE":
            out.append("network says device is NOT in its assigned zone")
        elif self.location_verified == "UNKNOWN":
            out.append("network could not confirm device position")
        return out

    @property
    def clean(self) -> bool:
        return not self.concerns

    def summary(self) -> dict:
        d = asdict(self)
        d["swap_time"] = self.swap_time.isoformat() if self.swap_time else None
        d["swap_age_h"] = round(self.swap_age_h, 2) if self.swap_age_h is not None else None
        d["concerns"] = self.concerns
        return d


def parse_identity(
    swap_raw: dict, date_raw: dict, roam_raw: dict, verify_raw: dict | None
) -> IdentityRead:
    country_list = _get(roam_raw or {}, "countryName", "country_name", default=[]) or []
    return IdentityRead(
        swapped=bool(_get(swap_raw or {}, "swapped", default=False)),
        swap_time=_parse_ts(_get(date_raw or {}, "latestSimChange", "latest_sim_change")),
        roaming=bool(_get(roam_raw or {}, "roaming", default=False)),
        country=country_list[0] if country_list else None,
        location_verified=(
            str(_get(verify_raw, "verificationResult", "verification_result", default="UNKNOWN"))
            if verify_raw
            else None
        ),
    )


# --- Zone rollup -------------------------------------------------------------


@dataclass
class ZoneEvidence:
    """Everything the agent knows about one zone, ready to hand to the LLM."""

    zone: Zone
    congestion: CongestionRead
    locations: list[LocationRead]
    reachability: list[ReachabilityRead]

    @property
    def sms_only_ratio(self) -> float:
        if not self.reachability:
            return 0.0
        return sum(1 for r in self.reachability if r.sms_only) / len(self.reachability)

    @property
    def stale_ratio(self) -> float:
        if not self.locations:
            return 0.0
        return sum(1 for loc in self.locations if loc.stale) / len(self.locations)

    def render(self) -> str:
        z = self.zone
        lines = [
            f"ZONE: {z.name}  (criticality {z.criticality}/5, capacity {z.capacity:,})",
            "",
            "Congestion window (oldest first):",
            self.congestion.render(),
            "",
            "Corroborating signals:",
            f"  devices on SMS-only fallback: {self.sms_only_ratio:.0%}",
            f"  location fixes stale (>{THRESHOLDS.stale_after_s}s): {self.stale_ratio:.0%}",
        ]
        for loc in self.locations:
            if loc.latitude is not None:
                lines.append(
                    f"  fix: {loc.latitude:.4f},{loc.longitude:.4f} "
                    f"r={loc.radius_m}m ({loc.precision_note}, "
                    f"{loc.age_s:.0f}s old)" if loc.age_s is not None else
                    f"  fix: {loc.latitude:.4f},{loc.longitude:.4f} r={loc.radius_m}m"
                )
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "zone_id": self.zone.id,
            "zone_name": self.zone.name,
            "criticality": self.zone.criticality,
            "congestion": self.congestion.summary(),
            "sms_only_ratio": round(self.sms_only_ratio, 3),
            "stale_ratio": round(self.stale_ratio, 3),
        }
