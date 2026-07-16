# SAKINA — Roadmap

From today (2026-07-15) to final submission (2026-09-13). Solo developer.

Task IDs are stable — reference them in commits (`git commit -m "S1.2: ..."`).
Check boxes as you go. This file is the plan of record; update it when reality
disagrees.

---

## Stage 0 — Port into Claude Code · *do this first, ~20 min*

- [ ] **S0.1** Create the repo and move the existing code in

  ```bash
  mkdir sakina && cd sakina
  git init
  # copy the delivered project in (it is already complete and verified)
  git add -A
  git commit -m "S0.1: initial commit — SAKINA agent scaffold"
  ```

  **Do not rebuild from scratch.** The SDK archaeology in `CLAUDE.md` cost a full
  session. Porting preserves it; rewriting reintroduces the guessing.

- [ ] **S0.2** Environment

  ```bash
  python -m venv .venv
  source .venv/bin/activate        # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  cp .env.example .env             # then fill in keys
  ```

- [ ] **S0.3** Confirm the port is intact

  ```bash
  python -m pytest tests/ -q       # expect: 21 passed
  SAKINA_MODE=replay python run_cycle.py jamarat-bridge
  ```

  Both must pass before touching anything else. If they don't, the port is broken —
  fix that, don't build on it.

---

## Stage 1 — Close the two blockers · *this week*

Everything downstream is unverified until these land. Do not start Stage 2 first.

- [ ] **S1.1** 🔴 **Verify live Nokia NaC from Python**

  The whole project has only ever run against fixtures. The playground working
  does **not** prove the SDK + your key works.

  1. Subscribe to Network-as-Code on **RapidAPI** (see `CLAUDE.md` → Auth)
  2. Put the RapidAPI key in `.env` as `NAC_API_KEY`
  3. `SAKINA_MODE=live python run_cycle.py jamarat-bridge`

  **Expected failure modes:**
  - 401/403 → wrong key type (portal key instead of RapidAPI key)
  - 422 on congestion → device dict needs `ipv4_address`
  - 422 on location verify → area shape; check nested `center`
  - 404 → simulator numbers differ on your account; pull real ones from the portal

  **Definition of done:** at least 5 of 7 APIs return live data, and the trace
  shows `LIVE` not `CACHE`. Re-record fixtures from live responses if they differ
  from what's checked in.

- [ ] **S1.2** 🔴 **See real LLM output**

  Prompts in `brain.py` were tuned against **fabricated** model responses. The real
  ones may be worse, may not respect the JSON schema, may hallucinate numbers.

  1. Free Gemini key: https://aistudio.google.com/apikey → `.env`
  2. Free Groq key: https://console.groq.com/keys → `.env`
  3. `python run_cycle.py jamarat-bridge` and read the trace closely

  **Watch for:** numbers cited that aren't in the evidence · `risk_score` that
  ignores the confidence trend · contradictions field left empty when SMS-only
  disagrees with congestion · JSON that won't parse.

  **Definition of done:** 5 consecutive cycles produce valid JSON and reasoning
  that cites actual numbers from the evidence block. Iterate on `ASSESS_SYSTEM`
  until true.

- [ ] **S1.3** Force the Groq fallback and confirm it works

  Temporarily set a bad `GEMINI_API_KEY`. The trace must show the degrade event
  and complete via Groq. This is a scored line item (graceful degradation).

- [ ] **S1.4** Fill in `docs/SAKINA_Idea_Capture.docx` — name, team name, contact,
  submission date.

---

## Stage 2 — Phase 1 deliverables · *→ Aug 20*

Deadline is Aug 23. Target Aug 20. Do not use the buffer.

- [ ] **S2.1** Architecture diagram

  Excalidraw+AI or Eraser AI (both Guide §9). Must show: LangGraph nodes ·
  conditional edges · each CAMARA API as an agent tool · the live/cache/degrade
  path. This goes in both the deck and the README.

- [ ] **S2.2** Pitch deck

  Build sections against the **Phase 1 rubric** — Relevance, Impact, Innovation,
  Complexity. Required by the submission spec:
  - Problem statement and context
  - Proposed solution and API usage
  - **AI agent design and orchestration approach, incl. tools from the Resource &
    Tooling Guide** ← explicitly required; name LangGraph/Gemini/Groq/Streamlit
  - Technical architecture
  - Business model and monetization
  - Demo screenshots or video links
  - Team bios and roles

  **The slide that wins Phase 1:** heuristic vs LLM on the same window. The rule
  engine scored **0.69** off a window whose most trustworthy reading (97%) says
  *Low* — it weighted a 16%-confidence Medium as real evidence. That is a
  demonstrated failure, not a claim. Show both traces side by side.

- [ ] **S2.3** Business model section

  Weakest area — engineering is ahead of commercial. Needs real thinking:
  - Buyer: Saudi Ministry of Hajj & Umrah? operators (STC/Mobily/Zain)? event
    insurers?
  - Pricing: per-pilgrim-season licence? per-zone? per-API-call passthrough?
  - Why an operator sells this rather than builds it
  - TAM beyond Hajj: Umrah year-round, stadiums, Expo, Ramadan markets

- [ ] **S2.4** Submit Phase 1 **Aug 20**

---

## Stage 3 — Prototype hardening · *Aug 24 → Sep 8*

Start Aug 24 — assume Phase 1 passes. 17 days is not enough to start from zero.

- [ ] **S3.1** Multi-zone concurrent monitoring — agent picks which zone to poll
  next based on its own risk assessment. Strengthens the autonomy story.
- [ ] **S3.2** Geofencing subscription demo via ngrok — one live subscription
  proving the event model is understood. Keep polling as the main loop.
- [ ] **S3.3** Map view in Streamlit (`st.map` or pydeck) — zones + risk colour.
- [ ] **S3.4** Cycle history — show risk evolving over time, not just a snapshot.
- [ ] **S3.5** Harden error paths: network timeout, malformed LLM JSON, empty
  congestion, all-providers-down. Each should degrade visibly, never crash.
- [ ] **S3.6** Deploy to Streamlit Community Cloud (Guide §6). Judges may click.
- [ ] **S3.7** **Feature freeze Sep 8.** No exceptions.

---

## Stage 4 — Demo + submission · *Sep 8 → Sep 12*

- [ ] **S4.1** Demo script — 3 min hard cap. Suggested beats:
  - 0:00–0:20 Mina 2015. 2,000 dead. Density is invisible until it's lethal.
  - 0:20–0:50 The confidence insight. Show the four buckets. "A rule engine reads
    Low and stands down."
  - 0:50–1:50 **Live agent cycle.** UI left, reasoning trace + API log right. Agent
    catches the SMS-only contradiction, escalates on its own.
  - 1:50–2:30 Identity gate. Alpha blocked (SIM swap + roaming + position FALSE).
    Bravo cleared. **QoD fires live.**
  - 2:30–3:00 7 APIs, one agent, business impact.

- [ ] **S4.2** Record it. **Split screen: UI + live API log.** The log proving real
  NaC traffic is what separates a prototype from a mockup. "Functionality and
  stability of the prototype" is a scored line.

- [ ] **S4.3** Repo ready: README polished, no secrets in history
  (`git log -p | grep -i "api_key"`), clean commit history dated inside the window.

- [ ] **S4.4** Submission package: demo description · **API usage synopsis** ·
  **commercial value summary** · **business impact statement** · GitHub link.
  All four are explicitly required.

- [ ] **S4.5** Submit **Sep 12**. Resubmit freely — last counts.

- [ ] **S4.6** Rehearse the live Phase 2 presentation. Separate skill from the
  recording. Practice out loud, timed.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| RapidAPI key doesn't work / NaC subscription blocked | 🔴 high | S1.1 **now** — everything depends on it |
| Real LLM output much worse than fabricated | 🔴 high | S1.2 now; heuristic fallback keeps the demo alive regardless |
| Simulator numbers differ on your account | 🟡 med | Pull from portal, re-record fixtures, update `config.py` |
| Solo bandwidth in the 17-day window | 🟡 med | Thin slice done in Stage 1-2; Stage 3 is polish only |
| Live API fails during the recording | 🟢 low | `hybrid` mode + fixtures already handle this |
| Business model thin vs technical depth | 🟡 med | S2.3 — do not leave to the last week |

---

## Session-start checklist for Claude Code

```bash
source .venv/bin/activate
python -m pytest tests/ -q                        # 21 passed
SAKINA_MODE=replay python run_cycle.py jamarat-bridge
```

Then read `CLAUDE.md` § "Verified facts" before touching any SDK call.

---

## First prompt to give Claude Code

> Read CLAUDE.md and ROADMAP.md. We're at Stage 1. I have my RapidAPI key and
> Gemini key in .env. Start with S1.1: get a live Nokia NaC call working from
> Python and show me the trace. If calls fail, diagnose against the verified facts
> in CLAUDE.md — do not guess at SDK shapes.
