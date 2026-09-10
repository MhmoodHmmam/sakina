"""SAKINA — operator console.

Left: what the network says. Right: what the agent is thinking.
The right panel is the product. Judges are told to look for the reasoning trace;
this makes it the largest thing on screen.

The operator does not choose which zone to look at — the agent does, each
cycle, via scheduler.pick_next_zone(). That choice is itself a trace entry.

Bilingual: the language toggle switches both the static UI chrome and the
model's own reasoning (brain.py asks Gemini/Groq to answer in Arabic when
selected — this is not a translation layer bolted on afterwards).

    streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime, timezone

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from sakina import config, i18n
from sakina.agent import Sakina
from sakina.camara import CamaraTools
from sakina.scheduler import ZoneStatus, explain, pick_next_zone
from sakina.trace import EventKind, Source, Trace

st.set_page_config(page_title="SAKINA", page_icon="🕋", layout="wide")

# --- Language must be known before anything else renders ---------------------

with st.sidebar:
    lang = st.segmented_control(
        i18n.t("ui.language", "en") + " / " + i18n.t("ui.language", "ar"),
        options=["en", "ar"],
        format_func=lambda v: "English" if v == "en" else "العربية",
        default="en",
        required=True,
        key="language",
    )

RTL = lang == "ar"


def T(key: str, **kwargs) -> str:
    return i18n.t(key, lang, **kwargs)


# --- Design system + RTL -------------------------------------------------------
# Palette matches the architecture diagram published for this project — one
# visual language across the technical surfaces (console, diagrams).

CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0b1412;
    --panel: #101b18;
    --panel-2: #0d1815;
    --ink: #e7f1ec;
    --muted: #8fa69d;
    --accent: #3fd8c4;
    --ok: #4cc38a;
    --warn: #e8a33d;
    --danger: #e2574c;
    --rule: rgba(143, 166, 157, 0.22);
    --sans: 'IBM Plex Sans Arabic', -apple-system, 'Segoe UI', sans-serif;
    --mono: 'IBM Plex Mono', 'Cascadia Code', Consolas, monospace;
  }}
  html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background: var(--bg) !important;
    font-family: var(--sans);
    direction: {"rtl" if RTL else "ltr"};
  }}
  [data-testid="stSidebar"] {{ background: var(--panel-2); direction: {"rtl" if RTL else "ltr"}; }}
  h1, h2, h3, h4, p, span, div, label {{ font-family: var(--sans); }}
  code, .mono {{ font-family: var(--mono) !important; }}
  .masthead {{ border-bottom: 1px solid var(--rule); padding-bottom: 14px; margin-bottom: 6px; }}
  .masthead .eyebrow {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--accent); }}
  .masthead h1 {{ color: var(--ink); font-size: 26px; font-weight: 600; margin: 4px 0 6px; }}
  .masthead .sub {{ color: var(--muted); font-size: 13.5px; max-width: 70ch; line-height: 1.55; }}
  .zone-card {{
    border: 1px solid var(--rule); border-radius: 10px; padding: 14px 16px;
    margin-bottom: 10px; background: var(--panel);
  }}
  .zone-card.hot {{ border-color: var(--danger); background: #1d1416; }}
  .zone-card.warm {{ border-color: var(--warn); background: #1c1a13; }}
  .zone-card.chosen {{ box-shadow: 0 0 0 1px var(--accent) inset; }}
  .zone-name {{ font-weight: 600; font-size: 15px; color: var(--ink); }}
  .zone-meta {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .trace-row {{
    border-inline-start: 3px solid var(--rule); padding: 8px 14px;
    margin: 2px 0; font-size: 13px; color: var(--ink); text-align: start;
  }}
  .trace-row.phase {{ border-inline-start-color: var(--accent); font-weight: 600;
    color: var(--accent); margin-top: 14px; text-transform: uppercase; letter-spacing: 0.05em; font-size: 12px; }}
  .trace-row.api {{ border-inline-start-color: var(--ok); font-family: var(--mono); font-size: 12px; }}
  .trace-row.api.cache {{ border-inline-start-color: #8957e5; }}
  .trace-row.thought {{ border-inline-start-color: var(--warn); background: var(--panel);
    border-start-end-radius: 6px; border-end-end-radius: 6px; padding: 10px 12px; }}
  .trace-row.decision {{ border-inline-start-color: var(--accent); background: var(--panel-2);
    border-start-end-radius: 6px; border-end-end-radius: 6px; padding: 10px 12px; font-weight: 500; }}
  .trace-row.action {{ border-inline-start-color: var(--danger); background: #1d1416;
    border-start-end-radius: 6px; border-end-end-radius: 6px; padding: 10px 12px; font-weight: 600; }}
  .trace-row.degrade {{ border-inline-start-color: var(--warn); color: var(--warn); font-size: 12px; }}
  .trace-detail {{ color: var(--muted); font-size: 12px; margin-top: 5px; line-height: 1.6; }}
  .badge {{ display: inline-block; padding: 1px 7px; border-radius: 9px; font-size: 10px;
    font-weight: 600; margin-inline-start: 6px; letter-spacing: 0.4px; font-family: var(--mono); }}
  .badge.live {{ background: var(--ok); color: #04211a; }}
  .badge.cache {{ background: #8957e5; color: #fff; }}
  .risk {{ font-size: 38px; font-weight: 700; line-height: 1; font-family: var(--mono); }}
  .rtl-note {{ color: var(--muted); font-size: 11px; font-style: italic; margin-top: 4px; }}
  .callout {{ border-inline-start: 3px solid var(--accent); background: var(--panel);
    border-start-end-radius: 6px; border-end-end-radius: 6px; padding: 11px 14px;
    margin: 6px 0 10px; font-size: 13.5px; line-height: 1.6; color: var(--ink); text-align: start; }}
  .callout.contra {{ border-inline-start-color: var(--warn); color: var(--warn); font-size: 12.5px; }}
  [data-testid="stMetric"] {{ background: var(--panel); border: 1px solid var(--rule);
    border-radius: 10px; padding: 12px 14px; }}
  [data-testid="stMetricLabel"] {{ color: var(--muted) !important; font-size: 12px !important; }}
  [data-testid="stMetricValue"] {{ font-family: var(--mono) !important; color: var(--ink) !important;
    font-size: 26px !important; }}
  [data-testid="stMetricDelta"] {{ font-family: var(--mono) !important; font-size: 12px !important; }}
  [data-testid="stExpander"] details {{ background: var(--panel); border: 1px solid var(--rule);
    border-radius: 10px; }}
  [data-testid="stExpander"] summary {{ font-size: 13px; color: var(--muted); }}
  [data-testid="stExpander"] summary:hover {{ color: var(--accent); }}
  [data-testid="stDataFrame"] {{ border: 1px solid var(--rule); border-radius: 8px; }}
  .stCode, pre {{ background: var(--panel-2) !important; border: 1px solid var(--rule);
    border-radius: 8px; font-family: var(--mono) !important; font-size: 11.5px !important; }}
  [data-testid="stVegaLiteChart"] {{ background: transparent; }}
  hr {{ border-color: var(--rule); }}
  .stSlider, .stRadio label {{ color: var(--ink); }}
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
            badge_text = T("ui.badge_live") if tag == "live" else T("ui.badge_cache")
            head += (f'<span class="badge {tag}">{badge_text}</span>'
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
        return [226, 87, 76, 220]  # hot
    if score >= config.THRESHOLDS.escalate_at:
        return [232, 163, 61, 220]  # warm
    return [76, 195, 138, 200]  # calm


# Categorical, deliberately NOT the risk palette: a line's colour identifies
# WHICH zone, while amber/red are reserved for severity. Reusing the risk
# colours for series identity would make a calm zone's line read as "danger".
ZONE_SERIES_COLORS = ["#3fd8c4", "#8a7ff0", "#5aa9e6", "#e07ba8"]


def history_chart(hist_df: pd.DataFrame, lang: str) -> alt.LayerChart:
    """Risk over cycles, with the agent's two decision thresholds drawn in.

    The thresholds are the point: without them a reader cannot tell whether a
    given score meant "keep watching" or "verify identity and consider
    elevating". Y is pinned to 0-1 so those lines stay where the eye expects.
    """
    axis_kw = dict(labelColor="#8fa69d", titleColor="#8fa69d", tickColor="#8fa69d55",
                   domainColor="#8fa69d55", labelFont="IBM Plex Mono",
                   titleFont="IBM Plex Sans Arabic", labelFontSize=11, titleFontSize=11)

    line = alt.Chart(hist_df).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=48, filled=True),
    ).encode(
        x=alt.X("cycle:Q", title=T("ui.chart_cycle"),
                axis=alt.Axis(tickMinStep=1, grid=False, **axis_kw)),
        y=alt.Y("risk_score:Q", title=T("ui.chart_risk"),
                scale=alt.Scale(domain=[0, 1], nice=False),
                axis=alt.Axis(grid=True, gridColor="#8fa69d1f", **axis_kw)),
        color=alt.Color("zone:N", title=None,
                        scale=alt.Scale(range=ZONE_SERIES_COLORS),
                        legend=alt.Legend(orient="top", labelColor="#e7f1ec",
                                          labelFont="IBM Plex Sans Arabic",
                                          labelFontSize=11, symbolStrokeWidth=3)),
        tooltip=[alt.Tooltip("cycle:Q", title=T("ui.col_cycle")),
                 alt.Tooltip("zone:N", title=T("ui.col_zone")),
                 alt.Tooltip("risk_score:Q", title=T("ui.col_risk"), format=".2f"),
                 alt.Tooltip("model:N", title=T("ui.col_model"))],
    )

    def threshold(value: float, color: str):
        return alt.Chart(pd.DataFrame({"y": [value]})).mark_rule(
            color=color, strokeDash=[4, 4], strokeWidth=1, opacity=0.85,
        ).encode(y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1], nice=False)))

    return (
        threshold(config.THRESHOLDS.escalate_at, "#e8a33d")
        + threshold(config.THRESHOLDS.act_at, "#e2574c")
        + line
    ).properties(
        height=210, width="container",
        padding={"left": 46, "top": 8, "right": 14, "bottom": 8},
    ).configure_view(
        strokeWidth=0, fill="transparent"
    ).configure(background="transparent")


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
            "risk_label": f"{risk:.2f}" if risk is not None else T("ui.never_polled"),
            "radius": max(z.radius_m, 150),
            "color": risk_color(risk),
            "fill": risk_color(risk)[:3] + [46],  # same hue, low alpha — zone footprint
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
    st.markdown(
        f'<div class="masthead"><div class="eyebrow">GSMA MENA Ignite · Theme 3</div>'
        f'<h1>🕋 SAKINA</h1><div class="sub">{T("ui.brand_sub")}</div></div>',
        unsafe_allow_html=True,
    )
    mode = st.radio(
        T("ui.data_source"),
        ["hybrid", "live", "replay"],
        index=0,
        format_func=lambda v: T(f"ui.mode.{v}"),
        help=T("ui.data_source_help"),
    )
    st.caption(T("ui.autonomy_note"))
    st.markdown("---")
    agent = get_agent(mode)
    st.caption(T("ui.nac_connected") if agent.tools.live_available else T("ui.nac_replay_only"))
    st.caption(T("ui.model_label", primary=config.PRIMARY_MODEL, fallback=config.FALLBACK_MODEL))
    run = st.button(T("ui.run_button"), type="primary", width="stretch")
    if st.button(T("ui.reset_button"), width="stretch"):
        st.session_state["zone_status"] = {z.id: ZoneStatus(zone_id=z.id) for z in config.ZONES}
        st.session_state["history"] = []
        st.session_state["cycle_n"] = 0
        st.rerun()
    st.markdown("---")
    st.caption(f"**{T('ui.apis_header')}**")
    for key in ["congestion", "location_retrieval", "location_verification",
                "device_status", "sim_swap", "qod", "geofencing"]:
        st.caption(f"· {T(f'ui.api.{key}')}")
    if RTL:
        st.markdown(f'<div class="rtl-note">{T("ui.rtl_note")}</div>', unsafe_allow_html=True)


st.markdown(
    f'<div class="masthead"><h1 style="font-size:28px">{T("ui.console_title")}</h1>'
    f'<div class="sub">{T("ui.console_sub")}</div></div>',
    unsafe_allow_html=True,
)

left, right = st.columns([1, 1.6])

# --- Run a cycle (agent picks the zone) ---------------------------------------

if run:
    statuses = st.session_state["zone_status"]
    chosen = pick_next_zone(statuses)
    rationale = explain(statuses, chosen, language=lang)
    zone_name = config.ZONES_BY_ID[chosen].name

    trace = Trace()
    trace.decision(T("scheduler.chosen", zone=zone_name), rationale)

    with st.spinner(f"{zone_name}…"):
        state, trace = agent.cycle(chosen, trace, language=lang)

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
    if "assessment" in st.session_state:
        a = st.session_state["assessment"]
        st.markdown(f"#### {T('ui.current_reading', zone=st.session_state.get('assessment_zone', ''))}")
        st.markdown(
            f'<div class="risk" style="color:{"var(--danger)" if a["risk_score"]>=0.7 else "var(--warn)" if a["risk_score"]>=0.55 else "var(--ok)"}">'
            f'{a["risk_score"]:.2f}</div>'
            f'<div style="color:var(--muted);font-size:12px;margin-bottom:8px">'
            f'{T("ui.confidence_via", confidence=i18n.confidence_label(a["confidence"], lang), model=a["model"])}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="callout reading">{a["reading"]}</div>', unsafe_allow_html=True
        )
        if a.get("contradictions"):
            st.markdown(
                f'<div class="callout contra">'
                f'{T("ui.contradictions_label", items="; ".join(a["contradictions"]))}</div>',
                unsafe_allow_html=True,
            )

    st.markdown(f"#### {T('ui.zones_header')}")
    statuses = st.session_state["zone_status"]

    df = zone_map_df(statuses)
    view = pdk.ViewState(
        latitude=float(df["lat"].mean()), longitude=float(df["lon"].mean()),
        zoom=13, pitch=0,
    )
    # Two layers, not one: the footprint carries the zone's true radius in
    # metres (so the geography stays honest), while the marker is pixel-clamped
    # so a 600m zone doesn't render as a blob that swallows the basemap.
    footprint = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="fill",
        get_line_color="color",
        get_radius="radius",
        stroked=True,
        filled=True,
        line_width_min_pixels=1,
        radius_min_pixels=8,
        pickable=True,
    )
    marker = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=40,
        radius_min_pixels=5,
        radius_max_pixels=7,
        stroked=False,
        filled=True,
        pickable=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[footprint, marker], initial_view_state=view, map_style="dark",
        tooltip={"text": "{name}\nrisk: {risk_label}"},
    ), width="stretch", height=300)

    for z in config.ZONES:
        s = statuses.get(z.id)
        score = s.last_risk if s else None
        klass = "zone-card"
        if score is not None:
            klass += " hot" if score >= config.THRESHOLDS.act_at else (
                " warm" if score >= config.THRESHOLDS.escalate_at else "")
        if st.session_state.get("assessment_zone") == z.name:
            klass += " chosen"
        badge = f"<b style='color:var(--ink)'>{score:.2f}</b>" if score is not None else "<span style='color:var(--muted)'>—</span>"
        due = T("ui.next_due", s=s.next_poll_s) if s and s.last_polled else T("ui.never_polled")
        st.markdown(
            f"""<div class="{klass}">
                <div style="display:flex;justify-content:space-between;align-items:baseline">
                  <span class="zone-name">{z.name}</span>{badge}
                </div>
                <div class="zone-meta">{T("ui.zone_meta", crit=z.criticality, cap=f"{z.capacity:,}", due=due)}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    if st.session_state["history"]:
        st.markdown(f"#### {T('ui.history_header')}")
        hist_df = pd.DataFrame(st.session_state["history"])
        st.altair_chart(history_chart(hist_df, lang), use_container_width=True)
        with st.expander(T("ui.log_expander", n=len(hist_df))):
            display_df = hist_df[["cycle", "zone", "risk_score", "confidence", "model", "reading"]].rename(
                columns={
                    "cycle": T("ui.col_cycle"), "zone": T("ui.col_zone"),
                    "risk_score": T("ui.col_risk"), "confidence": T("ui.col_confidence"),
                    "model": T("ui.col_model"), "reading": T("ui.col_reading"),
                }
            ).sort_values(T("ui.col_cycle"), ascending=False)
            st.dataframe(display_df, hide_index=True)

# --- Trace -------------------------------------------------------------------

with right:
    st.markdown(f"#### {T('ui.reasoning_header')}")
    slot = st.empty()

    if "last_trace_html" in st.session_state:
        slot.markdown(st.session_state["last_trace_html"], unsafe_allow_html=True)

        live, total = st.session_state["last_metrics"][0][0], st.session_state["last_metrics"][0][1]
        apis_n = st.session_state["last_metrics"][1]
        elapsed = st.session_state["last_metrics"][2]
        c1, c2, c3 = st.columns(3)
        c1.metric(T("ui.metric_calls"), total, T("ui.metric_calls_live", n=live))
        c2.metric(T("ui.metric_apis"), apis_n)
        c3.metric(T("ui.metric_time"), f"{elapsed:.0f}ms")

        with st.expander(T("ui.raw_trace")):
            st.code(st.session_state["last_trace_json"], language="json")
    else:
        slot.caption(T("ui.reasoning_placeholder"))
