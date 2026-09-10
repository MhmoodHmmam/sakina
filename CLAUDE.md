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

**Hardening gotcha (found S3.5, 2026-07-17):** `brain.reason()`'s try/except
only catches a *parse* failure (malformed JSON text) and retries the next
provider. It does NOT catch a model returning valid JSON with the wrong field
*types* — `{"risk_score": "high"}` parses fine and then crashes
`Assessment.from_json()`'s `float()` coercion with an uncaught `ValueError`,
invisible to `agent.py`'s `except brain.LLMUnavailable`. Confirmed as a real
crash before fixing it, not assumed. `assess_zone()`/`gate_responders()` now
validate shape themselves and raise `LLMUnavailable` on failure, reusing the
already-tested fallback path instead of adding a second one.

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
— this URL (the one you connect to) is correct as-is. Do not override `base_url`.

**`NAC_API_KEY` must be a RapidAPI key with an active Network-as-Code
subscription — NOT a Nokia portal key.** If every call 401s/403s, this is why.
`client.oauth.get_client_credentials()` exists but takes no args; it is not the
auth path.

**`rapidapi_host` is a REQUIRED constructor arg, separate from `base_url`, and
easy to get wrong in two different ways.** Verified live 2026-07-16:

```python
nac.NetworkAsCodeApi(
    api_key=NAC_API_KEY,
    rapidapi_host="network-as-code.nokia.rapidapi.com",  # NOT the connect URL's host
)
```

- Omit `rapidapi_host` entirely → SDK never sends the `x-rapidapi-host` header
  → RapidAPI's shared `p-eu` gateway can't resolve which upstream tenant you
  mean → **404 `{"message": "API doesn't exists"}`** on every single endpoint,
  account-wide, not endpoint-specific. Looks nothing like an auth failure —
  confirmed identical even with a raw `httpx` call bypassing the SDK.
- Set `rapidapi_host` to the same string as the connect URL
  (`network-as-code.p-eu.rapidapi.com`) → **`httpx.ConnectError: getaddrinfo
  failed`**. `network-as-code.nokia.rapidapi.com` is a routing token this
  account's gateway understands, not a resolvable DNS name — don't `base_url`
  it.
- Get the exact `x-rapidapi-host` value from your own account's RapidAPI code
  snippet (Location Retrieval → code snippets → cURL). It is tenant-specific;
  do not assume `nokia` is universal across all NaC subscriptions.

`sakina/camara.py`'s `_build_client()` implements this correctly — copy that
pattern for any new CAMARA client construction.

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
- **Device/application-server IP dict key is `ipv4address` (no underscore),
  not `ipv4_address`.** The SDK's TypedDict aliases the attr name `ipv4address`
  to wire `ipv4Address`; a dict key of `ipv4_address` doesn't match, so it
  passes through unconverted and the live API rejects it as a missing field
  (422, "Application IP address is missing" — looks like a payload-shape
  problem, is actually a key-spelling problem). The device's nested IP object
  (`{"ipv4address": {...}}`) is typed `Any` server-side, so *its* inner keys
  get zero auto-conversion and must already be camelCase:
  `publicAddress`/`privateAddress`/`publicPort`. `application_server`'s
  `ipv4address` value is a plain string, not nested. `config.Device
  .as_camara_device()` implements this correctly — verified live 2026-07-17
  against a real `qod.create_session` 422, then a real 201.
- **`qod.create_session` response parsing breaks even on success.** The SDK's
  response model types `startedAt`/`expiresAt` as `int` (epoch); the live API
  returns ISO8601 strings. The HTTP call succeeds (a real session is created —
  verified: got a real `sessionId`, confirmed released after) but the SDK then
  raises `network_as_code.core.parse_error.ParsingError` trying to validate
  the response. **Don't let this orphan a live session** — `ParsingError.body`
  carries the raw, valid JSON; catch it and use that instead of the parsed
  model. `camara.py`'s `_create_qod_session()` implements this. Verified live
  2026-07-17.

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
| Reasoning | Gemini Flash-Lite (`gemini-flash-lite-latest`, Google AI Studio) | §3 hosted, free tier |
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
  config.py     zones, device roster, thresholds — all tunables
  trace.py      reasoning trace; the artifact judges watch
  camara.py     CAMARA tool layer; live/cache/degrade decided in ONE place (_invoke)
  signals.py    confidence-weighted interpretation — deterministic, tested
  scheduler.py  multi-zone priority arithmetic — which zone next, deterministic, tested
  brain.py      LLM reasoning, prompts, provider fallback
  agent.py      LangGraph StateGraph — single zone, one cycle
app.py          Streamlit operator console — drives the scheduler across zones
tests/          tests against real playground payloads
fixtures/       recorded Nokia NaC responses — replay mode works with zero keys
```

**`scheduler.py` (added Stage 3, S3.1):** the agent picks which zone to look at
next — never-polled zones first (criticality breaks ties), then how overdue a
zone is scaled by its last risk and criticality. Same split as `signals.py` vs
`brain.py`: this is deterministic priority arithmetic, not LLM judgement — the
model still only ever reasons about one zone at a time, inside `agent.cycle()`.
`app.py` calls `scheduler.pick_next_zone()` and logs the rationale as a
`trace.decision()` entry before the chosen zone's cycle even starts.

**Unobservable-zone crash (found 2026-09-10 on the deployed URL):** two zones
in `config.ZONES` (Mina Camps, Al-Muaisim Tunnel) have no devices assigned —
they exist for the map and roster. The scheduler still picked them once the
two observable zones had been polled (never-polled beats everything), and
`_perceive` did `probes[0]` on an empty list: IndexError, raw traceback in
the console on a judge's **third click**. `scheduler.observable()` now
filters candidates to zones with ≥1 device; `_perceive` raises a clear
ValueError instead of IndexError; `app.py` wraps `agent.cycle()` and renders
one `Cycle failed — …` callout plus the partial trace rather than a
traceback. Tested. Zones without a probe read "no probe assigned" in the UI.

## Bilingual (EN/AR) — added 2026-07-17, user requirement (MENA region)

Two independent mechanisms, deliberately not one:

- **`i18n.py`** — deterministic lookup for everything SAKINA itself generates:
  trace phase/label/detail text (`agent.py`, `camara.py`, `scheduler.py`) and
  static UI chrome (`app.py`). Every template is tested for EN/AR placeholder
  parity (`tests/test_i18n.py`) — a mismatched `{placeholder}` name is a
  silent runtime crash otherwise, not a typo you'd catch reading the diff.
- **`brain.py`'s Arabic directive** — appended to the system prompt when
  `language="ar"`, asking Gemini/Groq to answer in Arabic. This is the
  model's own judgement changing language, not a translation layer over
  English output. `confidence`/`severity` are explicitly instructed to stay
  fixed English enum tokens regardless of response language, precisely so
  `i18n.py`'s display lookup for them stays reliable across both providers.

`evidence_text` built for the model (`signals.py`'s `ZoneEvidence.render()`,
the DECIDE node's prompt blocks) is deliberately **not** translated — it's
model input, not something an operator reads directly, and the model already
reasons about it correctly regardless of its own output language.

**RTL in Streamlit**: full mirroring, via CSS logical properties
(`border-inline-start`, `margin-inline-start`, `text-align: start`) plus a
single `direction: rtl` toggle on the app/sidebar containers — not
conditionally including/excluding whole CSS rule blocks per language.
**That distinction matters**: an earlier version toggled entire CSS chunks
on/off with `{"...css..." if RTL else ""}`, and when the condition was
false the resulting **blank line inside `<style>`** made Streamlit's
markdown-HTML-passthrough terminate the raw HTML block early — CommonMark
ends an HTML block at a blank line. Everything after got parsed as a normal
markdown paragraph and rendered as literal visible CSS text on the page.
Confirmed live before fixing, not assumed. Logical properties sidestep the
whole bug class by never needing a rule to disappear, only a property value
to change. Known accepted limitation: pydeck's map and Streamlit's native
chart/dataframe internals do not mirror — flagged in the UI itself when
Arabic is selected.

**Same bug class, second sighting (review pass, 2026-09-10):** a trace
detail with a paragraph break (`agent.py` builds the ASSESS detail as
`reading\n\nreasoning\n\n…`) also ends the raw-HTML block, so everything
after the blank line went through the markdown parser and came out as
`<p>` elements — invisible today, but a model line starting with `*`, `#`
or `1.` would have rendered as emphasis, a heading or a list. `app.py`'s
`html_text()` escapes free text and turns newlines into `<br>` so every
model/exception string reaches `st.markdown` as one uninterrupted HTML
block. Confirmed in the DOM before and after (`.trace-detail` children:
two `<p>` → only `<br>`). Route any new free-text render through it.

## Operating modes

- `live` — Nokia NaC only; raises on failure
- `replay` — fixtures only; **works with no credentials at all**
- `hybrid` *(default)* — try live, fall back to fixture, **declare it in the trace**

**Cached data is never disguised as live.** Every trace entry carries
`Source.LIVE` or `Source.CACHE`. This is an honesty guarantee — do not weaken it.

**Fail closed:** no model → no QoD elevation. Refusing a medic is recoverable;
handing an impersonator priority spectrum is not.

## Current status (updated 2026-09-10)

- ✅ 7 CAMARA APIs verified live in the portal playground
- ✅ LangGraph agent executes end-to-end: 14 calls, 5 API families
- ✅ 53 tests passing (confidence weighting, scheduler, brain validation, camara modes, i18n parity, agent resilience) — `ruff check .` clean, CI on every push
- ✅ Streamlit console renders the live trace
- ✅ **Replay mode fixed (2026-07-17).** `fixtures/*.json` recorded from live
  calls covering everything `agent.cycle()` actually touches: congestion,
  location, reachability for both sensors; sim_swap (check + date), roaming,
  location.verify, reachability for both responders; one QoD create_session
  (on the clean device, released immediately after). Geofencing has no fixture
  yet — it isn't wired into the cycle until Stage 3. `SAKINA_MODE=replay
  python run_cycle.py jamarat-bridge` runs end-to-end with zero credentials.
- ✅ Idea Capture .docx drafted (needs name/team/contact)
- ✅ **S1.1 done (2026-07-16): live Nokia NaC verified with a real RapidAPI
  key.** 3/7 APIs exercised live (congestion_insights, location, device_status)
  via `run_cycle.py jamarat-bridge`. Root cause of the initial 404s was a
  missing/wrong `rapidapi_host` constructor arg — see Auth section above, fixed
  in `camara.py`.
- ✅ **QoD elevation verified live (2026-07-17).** Real session created and
  released against the clean device (+99999991001). Two bugs fixed along the
  way — the `ipv4address` key-spelling issue and the `ParsingError` response
  bug — both documented in Payload shapes above.
- ✅ **S1.2 model fixed (2026-07-17): `PRIMARY_MODEL` now
  `gemini-flash-lite-latest`.** `gemini-2.5-flash` and `gemini-2.5-flash-lite`
  both 404 for new API keys ("no longer available to new users") despite still
  appearing in `ListModels`; `gemini-2.0-flash` is listed and callable but its
  free-tier quota was already exhausted (429) on first use. Live cycle now
  produces evidence-grounded reasoning via Gemini directly (no fallback
  needed) — cited real confidence/congestion numbers, correctly read a
  falling-congestion + improving-confidence window as genuine dispersal.
  Groq fallback path separately confirmed working (fired automatically before
  this fix, valid output).
- ✅ Pitch deck (EN/AR), Idea Capture doc, demo video (narrated, English-only cut, 3:17) — in `../submission-kit/`, outside the repo

## Conventions

- Python 3.11+, type hints, `from __future__ import annotations`
- Docstrings explain **why**, not what
- No new deps outside the Guide
- Every CAMARA call goes through `CamaraTools._invoke` — never call the SDK
  directly from a node
- Run `ruff check .` and `python -m pytest tests/ -q` before every commit (CI runs both)
- Secrets only in `.env` (gitignored). Never commit a key. Never paste a key into
  a chat or a commit message.

## Working agreements

- **Verify, don't assume.** This project has already been burned by a
  confidently-wrong SDK guess. When unsure about an API shape, introspect it or
  hit the playground — do not pattern-match from training data.
- **Solo constraints are real.** Suggest less, not more.
- Update this file when a fact changes. It is the memory.

## Streamlit Community Cloud renders the app inside an iframe

Verified 2026-09-10. The hosted page at `sakina.streamlit.app` is a shell; the
actual app lives in `<iframe src="https://sakina.streamlit.app/~/+/">`
(same-origin). Any automation against the hosted URL — Playwright locators,
`wait_for_selector`, accessibility-tree reads — must target **that frame**;
page-level selectors never see the app and time out looking for the Run
button. Locally (`streamlit run`) there is no iframe. `scratchpad/
capture_hosted.py` shows the pattern (`page.frames` → url contains `/~/+/`).
Screenshots via `page.screenshot()` still capture the whole thing, and
`page.mouse.wheel` scrolls whatever is under the cursor, so those don't need
the frame. Also: `curl` on the hosted URL returns a 303 to
`share.streamlit.io/-/auth/app` — that's the anonymous session-cookie
handshake, not a private-app login wall; the app is public.

## Environment gotcha: tool sandbox is filesystem-isolated from the real desktop

Found during the S3.2 ngrok demo, 2026-07-17. Claude Code's Bash/PowerShell
tools run somewhere that reports the **same** username and path strings as
the user's real desktop (`C:\Users\pc\...`) but is a **different
filesystem** — `ngrok config add-authtoken` run in the user's own terminal
window produced a real, working config on their machine, while every check
from inside these tools (`ngrok config check`, `Test-Path` via PowerShell,
even invoking the exact same `ngrok.exe`) reported the config file missing,
repeatedly, across multiple retries.

**Consequence:** any setup step that writes to the user's profile/AppData
from *their own* terminal (auth tokens, app configs, credential files) will
not be visible to tool calls in this session, no matter how many times it's
retried. Don't loop on "did you run it yet?" — the retry itself can't work
by construction. Instead, get the *artifact* the step produces (a public
URL, an exported file, a printed value) and hand that across explicitly, the
way the ngrok public forwarding URL was used directly as a `sink` value here
without ever needing the authtoken to be visible on this side.
