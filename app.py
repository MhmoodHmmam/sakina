"""SAKINA — operator console.

Left: what the network says. Right: what the agent is thinking.
The right panel is the product. Judges are told to look for the reasoning trace;
this makes it the largest thing on screen.

The operator does not choose which zone to look at — the agent does, each
cycle, via scheduler.pick_next_zone(). That choice is itself a trace entry.

    streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pydeck as pdk
import streamlit as st

from sakina import config
from sakina.agent import Sakina
from sakina.camara import CamaraTools
from sakina.scheduler import ZoneStatus, explain, pick_next_zone
from sakina.trace import EventKind, Source, Trace

st.set_page_config(page_title="SAKINA", page_icon="🕋", layout="wide")

CSS = """
<style>
  .stApp { background: #0d1117; }
  .zone-card {
    border:1px solid #30363d; border-radius:10px; padding:14px 16px;
    margin-bottom:10px; background:#161b22;
  }
  .zone-card.hot { border-color:#f85149; background:#1d1416; }
  .zone-card.warm { border-color:#d29922; background:#1c1a13; }
  .zone-card.chosen { box-shadow: 0 0 0 1px #58a6ff inset; }
  .zone-name { font-weight:600; font-size:15px; color:#e6edf3; }
  .zone-meta { font-size:12px; color:#7d8590; margin-top:2px; }
  .trace-row {
    border-left:3px solid #30363d; padding:8px 0 8px 14px; margin:2px 0;
    font-size:13px; color:#c9d1d9;
  }
  .trace-row.phase { border-left-color:#58a6ff; font-weight:600; color:#58a6ff;
    margin-top:14px; text-transform:uppercase; letter-spacing:.6px; font-size:12px; }
  .trace-row.api { border-left-color:#3fb950; font-family:ui-monospace,monospace; font-size:12px; }
  .trace-row.api.cache { border-left-color:#8957e5; }
  .trace-row.thought { border-left-color:#d29922; background:#1c1a13;
    border-radius:0 6px 6px 0; padding:10px 12px; }
  .trace-row.decision { border-left-color:#58a6ff; background:#0f1620;
    border-radius:0 6px 6px 0; padding:10px 12px; font-weight:500; }
  .trace-row.action { border-left-color:#f85149; background:#1d1416;
    border-radius:0 6px 6px 0; padding:10px 12px; font-weight:600; }
  .trace-row.degrade { border-left-color:#d29922; color:#d29922; font-size:12px; }
  .trace-detail { color:#8b949e; font-size:12px; margin-top:5px; line-height:1.55; }
  .badge { display:inline-block; padding:1px 7px; border-radius:9px; font-size:10px;
    font-weight:600; margin-left:6px; letter-spacing:.4px; }
  .badge.live { background:#238636; color:#fff; }
  .badge.cache { background:#8957e5; color:#fff; }
  .risk { font-size:40px; font-weight:700; line-height:1; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def get_agent(mode: str) -> Sakina:
    return Sakina(CamaraTools(mode=mode))  # type: ignore[arg-type]


def render_trace(trace: Trace) -> str:
    css = {
        EventKind.PHASE: "phase",
        EventKind.API_CALL: "api",
        EventKind.THOUGHT: "thought",
        EventKind.DECISION: "decision",
        EventKind.ACTION: "action",
        EventKind.DEGRADE: "degrade",
        EventKind.ERROR: "degrade",
    }
    glyph = {
        EventKind.PHASE: "", EventKind.API_CALL: "↗", EventKind.THOUGHT: "🧠",
        EventKind.DECISION: "◆", EventKind.ACTION: "⚡",
        EventKind.DEGRADE: "⚠", EventKind.ERROR: "✗",
    }
    out: list[str] = []
    for e in trace.events:
        klass = css[e.kind]
        if e.kind is EventKind.API_CALL and e.source is Source.CACHE:
            klass += " cache"
        head = f"{glyph[e.kind]} {e.label}".strip()
        if e.api:
            tag = "live" if e.source is Source.LIVE else "cache"
            head += (f'<span class="badge {tag}">{tag.upper()}</span>'
                     f'<span style="color:#6e7681;font-size:11px"> {e.latency_ms:.0f}ms</span>')
        block = f'<div class="trace-row {klass}">{head}'
        if e.detail:
            block += f'<div class="trace-detail">{e.detail}</div>'
        block += "</div>"
        out.append(block)
    return "".join(out)


def risk_color(score: float | None) -> list[int]:
    """RGBA for the zone map — same hot/warm/calm bands as the zone cards."""
    if score is None:
        return [88, 96, 105, 160]  # muted grey — never polled yet
    if score >= config.THRESHOLDS.act_at:
        return [248, 81, 73, 220]  # hot
    if score >= config.THRESHOLDS.escalate_at:
        return [210, 153, 34, 220]  # warm
    return [63, 185, 80, 200]  # calm


def zone_map_df(statuses: dict[str, ZoneStatus]) -> pd.DataFrame:
    rows = []
    for z in config.ZONES:
        s = statuses.get(z.id)
        risk = s.last_risk if s else None
        rows.append({
            "zone_id": z.id,
            "name": z.name,
            "lat": z.latitude,
            "lon": z.longitude,
            "risk": risk if risk is not None else -1,
            "risk_label": f"{risk:.2f}" if risk is not None else "not yet polled",
            "radius": max(z.radius_m, 150),
            "color": risk_color(risk),
        })
    return pd.DataFrame(rows)


# --- Session state init --------------------------------------------------------

if "zone_status" not in st.session_state:
    st.session_state["zone_status"] = {z.id: ZoneStatus(zone_id=z.id) for z in config.ZONES}
if "history" not in st.session_state:
    st.session_state["history"] = []  # list of dicts, one per cycle
if "cycle_n" not in st.session_state:
    st.session_state["cycle_n"] = 0

# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🕋 SAKINA")
    st.caption("Situational Awareness for Kinetic crowd Intelligence & Network Adaptation")
    st.markdown("---")
    mode = st.radio(
        "Data source",
        ["hybrid", "live", "replay"],
        index=0,
        help="hybrid: try Nokia NaC, fall back to recorded responses. "
             "replay: recorded only — guaranteed to run.",
    )
    st.caption(
        "The agent picks which zone to look at next — see **Multi-zone "
        "monitoring** below. Nothing here is operator-triggered."
    )
    st.markdown("---")
    agent = get_agent(mode)
    st.caption(
        f"Nokia NaC: {'🟢 connected' if agent.tools.live_available else '🟣 replay only'}"
    )
    st.caption(f"Model: {config.PRIMARY_MODEL} → {config.FALLBACK_MODEL}")
    run = st.button("▶ Run next cycle — agent picks the zone", type="primary", width="stretch")
    if st.button("Reset monitoring state", width="stretch"):
        st.session_state["zone_status"] = {z.id: ZoneStatus(zone_id=z.id) for z in config.ZONES}
        st.session_state["history"] = []
        st.session_state["cycle_n"] = 0
        st.rerun()
    st.markdown("---")
    st.caption("**CAMARA APIs orchestrated**")
    for a in ["Congestion Insights", "Location Retrieval", "Location Verification",
              "Device Status", "SIM Swap", "Quality on Demand", "Geofencing"]:
        st.caption(f"· {a}")


st.markdown("## Pilgrimage Crowd Safety — Agent Console")
st.caption(
    "The agent decides when to look, what to check, and whether to act. "
    "No operator input triggers a network change."
)

left, right = st.columns([1, 1.6])

# --- Run a cycle (agent picks the zone) ---------------------------------------

if run:
    statuses = st.session_state["zone_status"]
    chosen = pick_next_zone(statuses)
    rationale = explain(statuses, chosen)
    zone_name = config.ZONES_BY_ID[chosen].name

    trace = Trace()
    trace.decision(f"Multi-zone scheduler → {zone_name}", rationale)

    with st.spinner(f"Agent working on {zone_name}…"):
        state, trace = agent.cycle(chosen, trace)

    a = state["assessment"]
    now = datetime.now(timezone.utc)
    statuses[chosen] = ZoneStatus(
        zone_id=chosen,
        last_risk=a["risk_score"],
        last_polled=now,
        next_poll_s=a.get("recommended_poll_s", 60),
    )

    st.session_state["cycle_n"] += 1
    st.session_state["history"].append({
        "cycle": st.session_state["cycle_n"],
        "zone_id": chosen,
        "zone": zone_name,
        "ts": now,
        "risk_score": a["risk_score"],
        "confidence": a["confidence"],
        "model": a["model"],
        "reading": a["reading"],
    })

    st.session_state["last_trace_html"] = render_trace(trace)
    st.session_state["last_trace_json"] = trace.to_json()
    st.session_state["last_metrics"] = (trace.live_ratio(), len(trace.apis_touched()), trace.elapsed_ms)
    st.session_state["assessment"] = a
    st.session_state["assessment_zone"] = zone_name
    st.rerun()

# --- Zones + map ---------------------------------------------------------------

with left:
    st.markdown("#### Zones — multi-zone monitoring")
    statuses = st.session_state["zone_status"]

    df = zone_map_df(statuses)
    view = pdk.ViewState(
        latitude=float(df["lat"].mean()), longitude=float(df["lon"].mean()),
        zoom=13, pitch=0,
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.75,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer], initial_view_state=view, map_style=None,
        tooltip={"text": "{name}\nrisk: {risk_label}"},
    ), width="stretch", height=260)

    for z in config.ZONES:
        s = statuses.get(z.id)
        score = s.last_risk if s else None
        klass = "zone-card"
        if score is not None:
            klass += " hot" if score >= config.THRESHOLDS.act_at else (
                " warm" if score >= config.THRESHOLDS.escalate_at else "")
        if st.session_state.get("assessment_zone") == z.name:
            klass += " chosen"
        badge = f"<b style='color:#e6edf3'>{score:.2f}</b>" if score is not None else "<span style='color:#484f58'>—</span>"
        due = f"next due ~{s.next_poll_s}s after last poll" if s and s.last_polled else "never polled"
        st.markdown(
            f"""<div class="{klass}">
                <div style="display:flex;justify-content:space-between;align-items:baseline">
                  <span class="zone-name">{z.name}</span>{badge}
                </div>
                <div class="zone-meta">criticality {z.criticality}/5 · capacity {z.capacity:,} · {due}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    if "assessment" in st.session_state:
        a = st.session_state["assessment"]
        st.markdown(f"#### Current reading — {st.session_state.get('assessment_zone', '')}")
        st.markdown(
            f'<div class="risk" style="color:{"#f85149" if a["risk_score"]>=0.7 else "#d29922" if a["risk_score"]>=0.55 else "#3fb950"}">'
            f'{a["risk_score"]:.2f}</div>'
            f'<div style="color:#7d8590;font-size:12px;margin-bottom:8px">'
            f'{a["confidence"]} confidence · via {a["model"]}</div>',
            unsafe_allow_html=True,
        )
        st.info(a["reading"])
        if a.get("contradictions"):
            st.warning("**Contradictions:** " + "; ".join(a["contradictions"]))

    if st.session_state["history"]:
        st.markdown("#### Cycle history")
        hist_df = pd.DataFrame(st.session_state["history"])
        chart_df = hist_df.pivot_table(
            index="cycle", columns="zone", values="risk_score", aggfunc="last"
        )
        st.line_chart(chart_df, height=180)
        with st.expander(f"Log ({len(hist_df)} cycles)"):
            st.dataframe(
                hist_df[["cycle", "zone", "risk_score", "confidence", "model", "reading"]]
                .sort_values("cycle", ascending=False),
                hide_index=True,
            )

# --- Trace -------------------------------------------------------------------

with right:
    st.markdown("#### Agent reasoning")
    slot = st.empty()

    if "last_trace_html" in st.session_state:
        slot.markdown(st.session_state["last_trace_html"], unsafe_allow_html=True)

        live, total = st.session_state["last_metrics"][0][0], st.session_state["last_metrics"][0][1]
        apis_n = st.session_state["last_metrics"][1]
        elapsed = st.session_state["last_metrics"][2]
        c1, c2, c3 = st.columns(3)
        c1.metric("CAMARA calls", total, f"{live} live")
        c2.metric("APIs orchestrated", apis_n)
        c3.metric("Cycle time", f"{elapsed:.0f}ms")

        with st.expander("Raw trace (JSON)"):
            st.code(st.session_state["last_trace_json"], language="json")
    else:
        slot.caption("Press **Run next cycle** to watch the agent pick a zone and reason.")
