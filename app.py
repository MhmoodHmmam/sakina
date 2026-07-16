"""SAKINA — operator console.

Left: what the network says. Right: what the agent is thinking.
The right panel is the product. Judges are told to look for the reasoning trace;
this makes it the largest thing on screen.

    streamlit run app.py
"""
from __future__ import annotations

import time

import streamlit as st

from sakina import config
from sakina.agent import Sakina
from sakina.camara import CamaraTools
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
    zone_id = st.selectbox(
        "Zone",
        [z.id for z in config.ZONES],
        format_func=lambda i: config.ZONES_BY_ID[i].name,
    )
    st.markdown("---")
    agent = get_agent(mode)
    st.caption(
        f"Nokia NaC: {'🟢 connected' if agent.tools.live_available else '🟣 replay only'}"
    )
    st.caption(f"Model: {config.PRIMARY_MODEL} → {config.FALLBACK_MODEL}")
    run = st.button("▶ Run agent cycle", type="primary", use_container_width=True)
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

# --- Zones -------------------------------------------------------------------

with left:
    st.markdown("#### Zones")
    scores = st.session_state.get("scores", {})
    for z in config.ZONES:
        s = scores.get(z.id)
        klass = "zone-card"
        if s is not None:
            klass += " hot" if s >= 0.7 else (" warm" if s >= 0.55 else "")
        badge = f"<b style='color:#e6edf3'>{s:.2f}</b>" if s is not None else "<span style='color:#484f58'>—</span>"
        st.markdown(
            f"""<div class="{klass}">
                <div style="display:flex;justify-content:space-between;align-items:baseline">
                  <span class="zone-name">{z.name}</span>{badge}
                </div>
                <div class="zone-meta">criticality {z.criticality}/5 · capacity {z.capacity:,} · r={z.radius_m}m</div>
            </div>""",
            unsafe_allow_html=True,
        )

    if "assessment" in st.session_state:
        a = st.session_state["assessment"]
        st.markdown("#### Current reading")
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

# --- Trace -------------------------------------------------------------------

with right:
    st.markdown("#### Agent reasoning")
    slot = st.empty()

    if run:
        trace = Trace()
        with st.spinner("Agent working…"):
            state, trace = agent.cycle(zone_id, trace)
        slot.markdown(render_trace(trace), unsafe_allow_html=True)

        st.session_state.setdefault("scores", {})
        st.session_state["scores"][zone_id] = state["assessment"]["risk_score"]
        st.session_state["assessment"] = state["assessment"]

        live, total = trace.live_ratio()
        c1, c2, c3 = st.columns(3)
        c1.metric("CAMARA calls", total, f"{live} live")
        c2.metric("APIs orchestrated", len(trace.apis_touched()))
        c3.metric("Cycle time", f"{trace.elapsed_ms:.0f}ms")

        with st.expander("Raw trace (JSON)"):
            st.code(trace.to_json(), language="json")
        st.rerun()
    elif "last_trace_html" in st.session_state:
        slot.markdown(st.session_state["last_trace_html"], unsafe_allow_html=True)
    else:
        slot.caption("Press **Run agent cycle** to watch the agent reason.")
