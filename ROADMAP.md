# SAKINA — Roadmap

From today (2026-07-15) to final submission (2026-09-13). Solo developer.

Task IDs are stable — reference them in commits (`git commit -m "S1.2: ..."`).
Check boxes as you go. This file is the plan of record; update it when reality
disagrees.

---

## Stage 0 — Port into Claude Code · *do this first, ~20 min*

- [x] **S0.1** Create the repo and move the existing code in

  ```bash
  mkdir sakina && cd sakina
  git init
  # copy the delivered project in (it is already complete and verified)
  git add -A
  git commit -m "S0.1: initial commit — SAKINA agent scaffold"
  ```

  **Do not rebuild from scratch.** The SDK archaeology in `CLAUDE.md` cost a full
  session. Porting preserves it; rewriting reintroduces the guessing.

- [x] **S0.2** Environment

  ```bash
  python -m venv .venv
  source .venv/bin/activate        # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  cp .env.example .env             # then fill in keys
  ```

- [x] **S0.3** Confirm the port is intact

  ```bash
  python -m pytest tests/ -q       # expect: 21 passed
  SAKINA_MODE=replay python run_cycle.py jamarat-bridge
  ```

  Both must pass before touching anything else. If they don't, the port is broken —
  fix that, don't build on it.

---

## Stage 1 — Close the two blockers · *this week*

Everything downstream is unverified until these land. Do not start Stage 2 first.

- [x] **S1.1** 🔴 **Verify live Nokia NaC from Python** — done 2026-07-16/17.
  Root cause of every 404 was a missing/wrong `rapidapi_host` constructor arg,
  not the expected failure modes below (none of which were the actual issue —
  see CLAUDE.md Auth section for what really happened). 3 families exercised
  in the base cycle (congestion_insights, location, device_status); sim_swap
  and qod separately verified live during fixture recording and QoD elevation
  testing. All 5 API families the current agent actually calls are now live-
  verified. Geofencing (6th family in `camara.py`) isn't wired into
  `agent.cycle()` yet — deferred to S3.2 — so it's untested against live.

  ~~**Expected failure modes:**~~ (none of these were it — kept for history)
  - 401/403 → wrong key type (portal key instead of RapidAPI key)
  - 422 on congestion → device dict needs `ipv4_address`
  - 422 on location verify → area shape; check nested `center`
  - 404 → simulator numbers differ on your account; pull real ones from the portal

  **Definition of done:** ✅ trace shows `LIVE` not `CACHE`; fixtures re-recorded
  from live responses (2026-07-17), replay mode now runs clean too.

- [x] **S1.2** 🔴 **See real LLM output** — done 2026-07-17.

  `config.PRIMARY_MODEL` was `gemini-2.5-flash`, which 404s for new API keys
  despite still being listed by `ListModels`. Switched to
  `gemini-flash-lite-latest` (verified reliable across repeated calls).

  **Definition of done:** ✅ 5 consecutive live cycles, all valid JSON, all via
  Gemini, all citing real evidence numbers (confidence %, weighted/naive means)
  — no hallucinated figures, no schema violations.

- [x] **S1.3** Force the Groq fallback and confirm it works — done 2026-07-17.
  Forced via `GEMINI_API_KEY=<bad>` env-var override (doesn't touch `.env`,
  since `load_dotenv()` doesn't override already-set vars). Trace showed the
  `⚠ gemini unavailable` degrade event with the real error, then completed via
  Groq with valid, evidence-grounded reasoning.

- [x] **S1.4** Fill in `SAKINA_Idea_Capture.docx` — done 2026-07-17. Submitter
  MhmoodHmmam, team SAKINA, contact mhmood.hmmam@gmail.com, submission date
  20 Aug 2026 (the internal target, not the 23 Aug hard deadline).

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
