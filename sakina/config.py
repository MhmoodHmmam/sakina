"""SAKINA configuration.

All tunables live here. Zone geometry, device roster, thresholds, model choice.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# --- Credentials -------------------------------------------------------------

NAC_API_KEY = os.getenv("NAC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Models ------------------------------------------------------------------
# Primary: Gemini 2.5 Flash (free tier, generous limits).
# Fallback: Groq Llama (free tier, fast) — used when Gemini rate-limits.
# Both are on the approved Resource & Tooling Guide list.

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "llama-3.3-70b-versatile"

# --- Operating mode ----------------------------------------------------------
# live    : call Nokia NaC for real
# replay  : serve recorded fixtures (demo insurance — guide section 11)
# hybrid  : try live, fall back to fixture on failure  <-- default for demos

Mode = Literal["live", "replay", "hybrid"]
MODE: Mode = os.getenv("SAKINA_MODE", "hybrid")  # type: ignore[assignment]


# --- Zones -------------------------------------------------------------------


@dataclass(frozen=True)
class Zone:
    """A monitored sector of the pilgrimage site."""

    id: str
    name: str
    latitude: float
    longitude: float
    radius_m: int
    capacity: int  # design capacity, persons
    criticality: int  # 1-5; 5 = historically lethal chokepoint

    def as_camara_area(self) -> dict:
        """Shape expected by location.verify and geofencing subscriptions."""
        return {
            "area_type": "CIRCLE",
            "center": {"latitude": self.latitude, "longitude": self.longitude},
            "radius": self.radius_m,
        }


# Mina / Jamarat geography. Coordinates are approximate real-world values;
# the simulator does not honour them, but they make the map legible and the
# architecture honest — swap the roster for real MSISDNs and this is production.
ZONES: list[Zone] = [
    Zone("jamarat-bridge", "Jamarat Bridge", 21.4225, 39.8730, 400, 300_000, 5),
    Zone("street-204", "Street 204 Approach", 21.4180, 39.8760, 300, 120_000, 5),
    Zone("mina-camps-a", "Mina Camps — Sector A", 21.4130, 39.8850, 600, 200_000, 3),
    Zone("tunnel-al-muaisim", "Al-Muaisim Tunnel", 21.4090, 39.8690, 250, 80_000, 4),
]

ZONES_BY_ID = {z.id: z for z in ZONES}


# --- Devices -----------------------------------------------------------------


@dataclass(frozen=True)
class Device:
    """A simulator MSISDN standing in for a real handset."""

    phone_number: str
    role: Literal["pilgrim_sensor", "responder"]
    zone_id: str
    label: str
    # QoD requires an IP tuple; the simulator accepts these values.
    public_address: str = "233.252.0.2"
    private_address: str = "192.0.2.25"
    public_port: int = 80

    def as_camara_device(self, with_ip: bool = False) -> dict:
        d: dict = {"phone_number": self.phone_number}
        if with_ip:
            d["ipv4_address"] = {
                "public_address": self.public_address,
                "private_address": self.private_address,
                "public_port": self.public_port,
            }
        return d


# Nokia NaC simulator roster.
#
# VERIFIED against the portal playground on 2026-07-15:
#   +99999991000 -> reachable (SMS only), roaming HU, SIM swapped 12 min ago
#   +99999991001 -> QoD session creation succeeds
#
# The swapped SIM on 1000 is not a bug — it is the demo. The agent must refuse
# to elevate a responder whose SIM changed hours before a mass gathering.
DEVICES: list[Device] = [
    Device("+99999991000", "responder", "jamarat-bridge", "Medic Unit 1 (Alpha)"),
    Device("+99999991001", "responder", "jamarat-bridge", "Medic Unit 2 (Bravo)"),
    Device("+99999991002", "pilgrim_sensor", "jamarat-bridge", "Density probe J-1"),
    Device("+99999991003", "pilgrim_sensor", "street-204", "Density probe S-1"),
]

DEVICES_BY_NUMBER = {d.phone_number: d for d in DEVICES}


def devices_in_zone(zone_id: str, role: str | None = None) -> list[Device]:
    return [
        d
        for d in DEVICES
        if d.zone_id == zone_id and (role is None or d.role == role)
    ]


# --- Reasoning parameters ----------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Tunables for the assess step.

    These bound the LLM rather than replace it: the model produces a risk score
    and rationale, these decide what the system does about it.
    """

    escalate_at: float = 0.55  # risk score triggering identity verification
    act_at: float = 0.70  # risk score triggering QoD elevation
    min_confidence: int = 40  # below this, a congestion reading is near-noise
    stale_after_s: int = 300  # location older than this is not trusted
    qod_duration_s: int = 300
    qod_profile: str = "DOWNLINK_M_UPLINK_L"  # VERIFIED against playground
    sim_swap_window_h: int = 24  # a swap this recent blocks elevation


THRESHOLDS = Thresholds()

# Congestion levels as returned by the API, mapped to an ordinal for trend math.
CONGESTION_ORDINAL = {"Low": 0, "Medium": 1, "High": 2}
