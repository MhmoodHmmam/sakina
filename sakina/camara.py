"""CAMARA tool layer.

Wraps the Nokia Network-as-Code SDK. Every method:
  - is a *tool* the agent may choose to call (never a user button)
  - records itself in the trace with real latency and provenance
  - degrades to a recorded fixture rather than crashing the demo

Signatures verified against network_as_code (Fern-generated SDK) and the
Nokia portal playground on 2026-07-15.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import config, i18n
from .trace import Source, Trace

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# --- SDK bootstrap -----------------------------------------------------------


# Two distinct RapidAPI values, easy to conflate:
#   - the URL you actually connect to (NetworkAsCodeApiEnvironment.DEFAULT,
#     network-as-code.p-eu.rapidapi.com) — this one IS correct as the SDK default.
#   - the x-rapidapi-host HEADER, which RapidAPI's shared p-eu gateway uses to
#     route to the right upstream tenant. For this account's subscription that
#     value is network-as-code.nokia.rapidapi.com — a routing token, not a
#     resolvable hostname. Confirmed via the account's own RapidAPI code
#     snippet. Without this header (or with it set to the wrong value, e.g.
#     the connect-URL host), RapidAPI's gateway 404s with
#     {"message": "API doesn't exists"} rather than an auth error.
# Verified 2026-07-16.
RAPIDAPI_HOST = "network-as-code.nokia.rapidapi.com"


def _build_client():
    """Construct the NaC client, or None if the SDK/key is unavailable.

    NAC_API_KEY must be a RapidAPI key with an active Network-as-Code
    subscription — not a portal key.
    """
    if not config.NAC_API_KEY:
        return None
    try:
        import network_as_code as nac

        return nac.NetworkAsCodeApi(
            api_key=config.NAC_API_KEY, rapidapi_host=RAPIDAPI_HOST
        )
    except Exception:
        return None


# --- Fixtures ----------------------------------------------------------------


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def load_fixture(name: str) -> Any:
    p = _fixture_path(name)
    if not p.exists():
        raise FileNotFoundError(f"no fixture: {name}")
    return json.loads(p.read_text())


def save_fixture(name: str, data: Any) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _fixture_path(name).write_text(json.dumps(data, indent=2, default=str))


def _normalise(obj: Any) -> Any:
    """Pydantic model -> plain dict, recursively. Fern models expose .dict()."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_normalise(o) for o in obj]
    for attr in ("model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    if isinstance(obj, dict):
        return {k: _normalise(v) for k, v in obj.items()}
    return obj


# --- Client ------------------------------------------------------------------


class CamaraTools:
    """The agent's hands. One instance per process; trace swapped per cycle."""

    def __init__(self, trace: Trace | None = None, mode: config.Mode | None = None):
        self.trace = trace or Trace()
        self.mode: config.Mode = mode or config.MODE
        self._client = _build_client() if self.mode != "replay" else None
        self.language: str = "en"  # set by agent.py::cycle() per call, "en" | "ar"

    def bind(self, trace: Trace) -> "CamaraTools":
        self.trace = trace
        return self

    @property
    def live_available(self) -> bool:
        return self._client is not None

    # -- the one place live/cache/degrade is decided --------------------------

    def _invoke(
        self,
        api: str,
        label: str,
        fixture: str,
        call: Callable[[], Any],
        record: bool = False,
    ) -> Any:
        """Run a CAMARA call under the active mode, tracing provenance."""
        t0 = time.perf_counter()

        if self.mode == "replay" or self._client is None:
            data = load_fixture(fixture)
            self.trace.api_call(
                api,
                label,
                _as_payload(data),
                Source.CACHE,
                (time.perf_counter() - t0) * 1000,
                detail=i18n.t("api.replay_detail", self.language),
            )
            return data

        try:
            raw = call()
            data = _normalise(raw)
            dt = (time.perf_counter() - t0) * 1000
            self.trace.api_call(api, label, _as_payload(data), Source.LIVE, dt)
            if record:
                save_fixture(fixture, data)
            return data
        except Exception as exc:
            dt = (time.perf_counter() - t0) * 1000
            if self.mode == "live":
                self.trace.error(i18n.t("api.call_failed", self.language, api=api), f"{type(exc).__name__}: {exc}")
                raise
            # hybrid: the guide's rule — degrade, never die mid-demo.
            self.trace.degrade(
                i18n.t("api.call_unavailable", self.language, api=api),
                i18n.t("api.degrade_detail", self.language, err=f"{type(exc).__name__}: {exc}"),
            )
            data = load_fixture(fixture)
            self.trace.api_call(
                api, label, _as_payload(data), Source.CACHE, dt,
                detail=i18n.t("api.fallback_detail", self.language),
            )
            return data

    # -- Congestion Insights --------------------------------------------------

    def congestion(self, device: config.Device, hours: int = 1) -> list[dict]:
        """Congestion history+forecast for a device's cell.

        Returns buckets with congestionLevel and confidenceLevel. The confidence
        field is the whole reason this project needs an LLM: it turns a reading
        into evidence of varying weight rather than a fact.
        """
        now = datetime.now(timezone.utc)
        return self._invoke(
            "congestion_insights.query",
            i18n.t("api.congestion", self.language, label=device.label),
            f"congestion_{device.phone_number}",
            lambda: self._client.congestion_insights.query(
                device=device.as_camara_device(with_ip=True),
                start=now - timedelta(hours=hours),
                end=now,
            ),
        )

    # -- Location -------------------------------------------------------------

    def locate(self, device: config.Device, max_age: int = 60) -> dict:
        return self._invoke(
            "location.retrieve",
            i18n.t("api.locate", self.language, label=device.label),
            f"location_{device.phone_number}",
            lambda: self._client.location.retrieve(
                device=device.as_camara_device(), max_age=max_age
            ),
        )

    def verify_in_zone(
        self, device: config.Device, zone: config.Zone, max_age: int = 60
    ) -> dict:
        return self._invoke(
            "location.verify",
            i18n.t("api.verify", self.language, label=device.label, zone=zone.name),
            f"locverify_{device.phone_number}",
            lambda: self._client.location.verify(
                device=device.as_camara_device(),
                area=zone.as_camara_area(),
                max_age=max_age,
            ),
        )

    # -- Device Status --------------------------------------------------------

    def reachability(self, device: config.Device) -> dict:
        """Reachable + connectivity classes. SMS-only is a network-stress tell."""
        return self._invoke(
            "device_status.retrieve_reachability_status",
            i18n.t("api.reachability", self.language, label=device.label),
            f"reach_{device.phone_number}",
            lambda: self._client.device_status.retrieve_reachability_status(
                device=device.as_camara_device()
            ),
        )

    def roaming(self, device: config.Device) -> dict:
        return self._invoke(
            "device_status.retrieve_roaming_status",
            i18n.t("api.roaming", self.language, label=device.label),
            f"roam_{device.phone_number}",
            lambda: self._client.device_status.retrieve_roaming_status(
                device=device.as_camara_device()
            ),
        )

    # -- SIM Swap -------------------------------------------------------------

    def sim_swapped(self, device: config.Device, max_age_h: int | None = None) -> dict:
        h = max_age_h or config.THRESHOLDS.sim_swap_window_h
        return self._invoke(
            "sim_swap.check",
            i18n.t("api.simswap_check", self.language, label=device.label),
            f"simswap_{device.phone_number}",
            lambda: self._client.sim_swap.check(
                phone_number=device.phone_number, max_age=h * 60
            ),
        )

    def sim_swap_date(self, device: config.Device) -> dict:
        return self._invoke(
            "sim_swap.retrieve_date",
            i18n.t("api.simswap_date", self.language, label=device.label),
            f"simswapdate_{device.phone_number}",
            lambda: self._client.sim_swap.retrieve_date(
                phone_number=device.phone_number
            ),
        )

    # -- QoD ------------------------------------------------------------------

    def _create_qod_session(self, device: config.Device, dur: int) -> Any:
        """Create the session, tolerating a known SDK<->API schema mismatch.

        The live API returns startedAt/expiresAt as ISO8601 strings; the SDK's
        generated response model expects int (epoch). The HTTP call succeeds
        (a real session is created) but client-side response parsing then
        raises ParsingError — which would otherwise look like the whole call
        failed. ParsingError.body carries the raw, valid JSON, so recover from
        it rather than losing (and orphaning) a session that was actually
        created. Verified live 2026-07-17.
        """
        from network_as_code.core.parse_error import ParsingError

        try:
            return self._client.qod.create_session(
                device=device.as_camara_device(with_ip=True),
                application_server={"ipv4address": "8.8.8.8"},
                qos_profile=config.THRESHOLDS.qod_profile,
                duration=dur,
            )
        except ParsingError as exc:
            return exc.body

    def elevate_qod(
        self, device: config.Device, duration: int | None = None
    ) -> dict:
        """The agent's only side effect on the live network."""
        dur = duration or config.THRESHOLDS.qod_duration_s
        return self._invoke(
            "qod.create_session",
            i18n.t("api.qod_elevate", self.language, label=device.label),
            f"qod_{device.phone_number}",
            lambda: self._create_qod_session(device, dur),
        )

    def release_qod(self, session_id: str) -> None:
        if self._client is None or self.mode == "replay":
            self.trace.action(i18n.t("api.qod_release_replay", self.language), session_id)
            return
        try:
            self._client.qod.delete_session(session_id)
            self.trace.action(i18n.t("api.qod_released", self.language), session_id)
        except Exception as exc:
            self.trace.error(i18n.t("api.qod_release_failed", self.language), str(exc))

    # -- Geofencing -----------------------------------------------------------

    def geofences(self) -> list[dict]:
        return self._invoke(
            "geofencing.list_subscriptions",
            i18n.t("api.geofences", self.language),
            "geofences",
            lambda: self._client.geofencing.list_subscriptions(),
        )

    def watch_zone(self, device: config.Device, zone: config.Zone, sink: str) -> dict:
        """Subscribe to area-entered/left for a device.

        Requires a public sink URL. Demonstrates the event model; the main loop
        polls instead, because a solo demo cannot depend on inbound webhooks.
        """
        return self._invoke(
            "geofencing.create_subscription",
            i18n.t("api.watch_zone", self.language, zone=zone.name, label=device.label),
            f"geofence_{device.phone_number}",
            lambda: self._client.geofencing.create_subscription(
                protocol="HTTP",
                sink=sink,
                types=[
                    "org.camaraproject.geofencing-subscriptions.v0.area-entered",
                    "org.camaraproject.geofencing-subscriptions.v0.area-left",
                ],
                config={
                    "subscription_detail": {
                        "device": device.as_camara_device(),
                        "area": zone.as_camara_area(),
                    }
                },
            ),
        )


def _as_payload(data: Any) -> dict:
    if isinstance(data, dict):
        return data
    return {"result": data}
