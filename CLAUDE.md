# SAKINA — Project Context

> Claude Code reads this file automatically at the start of every session.
> It is the single source of truth for hard-won facts. Keep it current.

## What this is

An AI agent for the **GSMA MENA Ignite Hackathon** (HackerEarth, hosted by GSMA).
It reads telecom network signals via Nokia Network-as-Code (CAMARA APIs) to detect
crowd-crush risk at mass gatherings, and elevates emergency responder bandwidth —
but only for responders whose identity the network can vouch for.

**Theme 3** — Tourism, Pilgrimage & Cultural Experience Innovation.

## Hard deadlines

| Date | Event |
|---|---|
| 2026-08-23 | Idea Phase closes (Idea Capture doc + Pitch Deck) |
| 2026-08-28 | Prototype Phase opens |
| 2026-09-13 | Prototype Phase closes (video + repo + submission) |
| 2026-11 | MWC Doha (winners showcase) |

Internal targets: submit Phase 1 by **Aug 20**, Phase 2 by **Sep 12**. Unlimited
resubmissions; last one counts. Submit early, iterate.

## Team

**Solo developer.** Everything below must be achievable by one person. Reject
suggestions that assume a team. The developer's hands are the bottleneck, not
ideas. Scope down before adding.

## The core insight (do not lose this)

CAMARA Congestion Insights returns a `confidenceLevel` (0-100) with every reading.
That field is the entire project. It makes a reading *evidence of varying weight*
rather than a fact.

Real window from the Nokia simulator:

```
13:33  High   confidence  71%
13:38  Medium confidence  16%   <- near-worthless
13:43  High   confidence  51%
13:48  Low    confidence  97%
```

A threshold engine reads `Low` and stands down. The real question — is that
dispersal, or did telemetry improve while the crowd stayed? — is unanswerable by
any rule. That is why this needs an agent.

- Congestion falling + confidence **improving** → genuine dispersal
- Congestion falling + confidence **degrading** → going blind; risk UNKNOWN, not low

Confidence-weighted mean **1.11** vs naive **1.25**. Volatility **1.33/2.0**.
Yet 100% of devices are SMS-only — an independent signal that the data plane is
still saturated, **contradicting** the Low reading. The agent surfaces the
contradiction rather than resolving it away.

**Architectural rule:** `signals.py` does deterministic, tested arithmetic.
`brain.py` does judgement. A system where a threshold function decides and the LLM
writes the press release is not an agent. Never blur this line.

## Verified facts — do not re-derive

Verified against the Nokia NaC portal playground and SDK introspection on
**2026-07-15**. Trust these; they cost a full session to establish.

### SDK

- Package: `network-as-code` (PyPI). **Fern-generated** — flat namespaced clients.
- **There is no `Device` object and no `client.devices.get()`.** Any code or doc
  showing `from network_as_code.models.device import DeviceIpv4Addr` is describing
  an older SDK that no longer exists. Ignore it.
- Entry point: `nac.NetworkAsCodeApi(api_key=...)`
- Clients: `client.location`, `client.qod`, `client.sim_swap`,
  `client.device_status`, `client.congestion_insights`, `client.geofencing`,
  `client.number_verification`, `client.kyc`, `client.device_swap`,
  `client.number_recycling`, `client.call_forwarding_signal`
- Devices are passed as inline dicts: `device={"phone_number": "+99..."}`

### Auth — the biggest gotcha

`NetworkAsCodeApiEnvironment.DEFAULT = 'https://network-as-code.p-eu.rapidapi.com'`

**`NAC_API_KEY` must be a RapidAPI key with an active Network-as-Code
subscription — NOT a Nokia portal key.** If every call 401s/403s, this is why.
`client.oauth.get_client_credentials()` exists but takes no args; it is not the
auth path.

### Method signatures (verified)

```python
client.location.retrieve(device=..., max_age=60)
client.location.verify(device=..., area=..., max_age=60)
client.sim_swap.check(phone_number="+99...", max_age=240)      # minutes
client.sim_swap.retrieve_date(phone_number="+99...")
client.device_status.retrieve_reachability_status(device=...)
client.device_status.retrieve_roaming_status(device=...)
client.congestion_insights.query(device=..., start=dt, end=dt)  # device NEEDS ipv4_address
client.qod.create_session(device=..., application_server=..., qos_profile=..., duration=...)
client.qod.delete_session(session_id)
client.geofencing.list_subscriptions()
client.geofencing.create_subscription(protocol="HTTP", sink=url, types=[...], config={...})
```

### Payload shapes (verified)

- Wire is **camelCase** (`lastLocationTime`, `congestionLevel`, `qosStatus`,
  `sessionId`); SDK returns **snake_case**. `signals.py` tolerates both via `_get()`.
- **QoS profile: `DOWNLINK_M_UPLINK_L`** (not `QOS_L` — that guess was wrong).
- Location verify area: `{"area_type": "CIRCLE", "center": {"latitude": …,
  "longitude": …}, "radius": …}` — **nested center**, not flat lat/lon.
- **Congestion Insights returns newest-first.** `CongestionRead.parse()` sorts
  oldest-first. Getting this backwards silently inverts every trend conclusion.
  There is a test for it.
- Geofencing returns `[]` when empty — an empty list, not an error.
- Geofencing + Congestion subscriptions require a public `sink` URL (webhook).
  **The agent polls instead.** A solo demo cannot depend on inbound webhooks.

### Simulator numbers

| Number | State |
|---|---|
| `+99999991000` | reachable **SMS-only**, roaming **HU**, **SIM swapped**, location verify **FALSE** |
| `+99999991001` | clean, DATA-capable, **QoD session creation works** |

`+99999991000`'s dirty state is not a bug — **it is the demo.** A responder whose
SIM changed hours before a mass gathering, roaming abroad, position unconfirmed.

## Mandatory hackathon requirements

Violating any of these is disqualification:

1. **≥1 CAMARA API** from Nokia NaC. (We use 7.)
2. **AI agent layer** orchestrating CAMARA APIs as *trusted real-time data
   sources*, not user-triggered actions.
3. **Agent layer built ONLY with tools from the AI Resource & Tooling Guide.**
   No external tooling for that component.
4. **Original code**, written entirely inside the hackathon window (opened
   2026-07-01). Open-source libraries are fine. Keep git history clean from the
   first commit.
5. Aligned to one of 7 themes.

### Approved stack (all from the Guide)

| Layer | Choice | Guide § |
|---|---|---|
| Orchestration | LangGraph | §2 code-first frameworks |
| Reasoning | Gemini 2.5 Flash (Google AI Studio) | §3 hosted, free tier |
| Fallback | Groq Llama 3.3 70B | §3 rate-limit resilience |
| UI | Streamlit | §6 hosting & deployment |
| Data | Nokia Network-as-Code | §5 CAMARA |
| Vector store *(only if RAG is genuinely needed)* | Chroma | §4 |

**Do not add tools outside the Guide.** If a new dependency is needed, check the
Guide first. If it is not listed, do not use it in the agent layer.

## Guide §11 — what judges actually reward

Straight from the Guide's own tips section. Treat as a rubric:

- CAMARA APIs are tools the **agent decides** when to call, not buttons
- **Show the agent's reasoning trace on screen during the demo** ← `trace.py` exists for this
- Graceful degradation when rate-limited
- **Cache demo data** — live calls fail at the worst moment
- One polished agent beats five half-built ones

## Scoring rubric

**Phase 1** (Idea Capture + Deck): Relevance · Impact · Innovation · Complexity &
Implementation

**Phase 2** (Live Demo): Innovation & Originality · Impact · Scalability &
Commercial Viability · Technical Feasibility & API Usage · **Agentic AI &
Multi-API Orchestration** · Presentation & Pitch

Build every deliverable with these as section headers. Judges score what they can find.

## Architecture

```
PERCEIVE ──► ASSESS ──┬──► (risk low) ─────────────► REPORT
                      │
                      └──► VERIFY ──► DECIDE ──┬──► ACT ──► REPORT
                                               └──► REPORT
```

LangGraph `StateGraph`. The **conditional edges are the product** — the agent
decides whether to spend 5 extra API calls on identity checks, which responders to
verify, and whether to spend a QoD session on each. Nothing is user-triggered.

```
sakina/
  config.py    zones, device roster, thresholds — all tunables
  trace.py     reasoning trace; the artifact judges watch
  camara.py    CAMARA tool layer; live/cache/degrade decided in ONE place (_invoke)
  signals.py   confidence-weighted interpretation — deterministic, 21 tests
  brain.py     LLM reasoning, prompts, provider fallback
  agent.py     LangGraph StateGraph
app.py         Streamlit operator console
tests/         21 tests against real playground payloads
fixtures/      recorded Nokia NaC responses — replay mode works with zero keys
```

## Operating modes

- `live` — Nokia NaC only; raises on failure
- `replay` — fixtures only; **works with no credentials at all**
- `hybrid` *(default)* — try live, fall back to fixture, **declare it in the trace**

**Cached data is never disguised as live.** Every trace entry carries
`Source.LIVE` or `Source.CACHE`. This is an honesty guarantee — do not weaken it.

**Fail closed:** no model → no QoD elevation. Refusing a medic is recoverable;
handing an impersonator priority spectrum is not.

## Current status (2026-07-15)

- ✅ 7 CAMARA APIs verified live in the portal playground
- ✅ LangGraph agent executes end-to-end: 14 calls, 5 API families
- ✅ 21 tests passing on the confidence-weighting core
- ✅ Streamlit console renders the live trace
- ✅ Replay mode runs with zero credentials
- ✅ Idea Capture .docx drafted (needs name/team/contact)
- ⬜ **Live Python calls never verified with a real RapidAPI key** ← blocker
- ⬜ **Real LLM output never seen** — prompts tuned against fabricated responses
- ⬜ Pitch deck, architecture diagram, demo video

## Conventions

- Python 3.11+, type hints, `from __future__ import annotations`
- Docstrings explain **why**, not what
- No new deps outside the Guide
- Every CAMARA call goes through `CamaraTools._invoke` — never call the SDK
  directly from a node
- Run `python -m pytest tests/ -q` before every commit
- Secrets only in `.env` (gitignored). Never commit a key. Never paste a key into
  a chat or a commit message.

## Working agreements

- **Verify, don't assume.** This project has already been burned by a
  confidently-wrong SDK guess. When unsure about an API shape, introspect it or
  hit the playground — do not pattern-match from training data.
- **Solo constraints are real.** Suggest less, not more.
- Update this file when a fact changes. It is the memory.
