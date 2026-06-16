# CallSign AI — Build Plan (PoC)

**Voice-first AI incident response.** When a security alert fires, an AI agent reads
the runbook, scopes the blast radius, and gets a *spoken* yes/no from the on-call
engineer before executing a remediation action — with a live UI that reacts the
instant approval is given.

> **Demo money-shot:** click "Trigger Exploit" → watch agents reason in a terminal →
> a voice agent speaks the tailored script and asks for approval → say "yes" → a
> server tile flips `[COMPROMISED] → [ISOLATED]` in real time.

---

## Scope & constraints (this build)

- **Proof of concept**, not production. In-memory state, mock alerts, no auth, no DB.
- **Free tools first.** Costs deferred until they buy a demo improvement.
- **Lyzr Studio** account available now. **Deepgram / ElevenLabs / telephony** are
  *future* — the architecture must run end-to-end without them.

### Voice strategy (the key de-risking decision)

A real outbound call to a cell phone needs telephony (Twilio etc.) + STT/TTS keys we
don't have yet. So we build voice in three tiers and stop wherever the demo looks good:

| Tier | What it is | Needs | When |
|------|-----------|-------|------|
| **0 — Text approval** | Approve via a button / typed "yes" in the UI. Proves the whole loop. | Nothing | Build first |
| **1 — Browser voice** | Lyzr Studio voice agent talks through the laptop mic/speaker. *Sounds* like the phone demo without telephony. | Lyzr Studio (have it) | Build second |
| **2 — Real phone call** | Outbound call to an actual cell. | Twilio + Deepgram/ElevenLabs | Optional, later |

We design every interface so Tier 0 → 1 → 2 is a swap of the *approval channel*, not a
rewrite. The brain, state, and UI don't care how the "yes" arrives.

---

## Architecture

```
 [Trigger button] ──POST mock alert──► FastAPI /webhook/trigger
                                              │
                                              ▼
                                    Lyzr Automata "brain"
                                    ├─ Agent 1  Forensic Synthesizer  (RAG over runbooks)
                                    └─ Agent 2  Commander             (3-sentence voice script)
                                              │
                          ┌───────────────────┼────────────────────┐
                          │ (push logs)        │ (start approval)   │
                          ▼                    ▼                    │
                    Next.js UI          Approval channel            │
                    ├ Left: live logs   (Tier 0 button / Tier 1     │
                    └ Right: server       Lyzr voice / Tier 2 phone) │
                       tiles                   │                     │
                          ▲                    │ "yes"               │
                          │                    ▼                     │
                          └──push state──  FastAPI /execute ◄────────┘
                                              │
                                       mutate infra state
```

**The one thing the original plan glossed over:** how the *browser* learns that
`/execute` ran. Answer — **Server-Sent Events (SSE)** from FastAPI. One-way
server→browser, dead simple, no extra deps, free. (WebSocket is overkill here; we
never need browser→server push — the UI POSTs normally.)

---

## Tech stack (all free)

- **Backend:** FastAPI + Uvicorn. SSE via `sse-starlette` or a raw `StreamingResponse`.
- **Brain:** Lyzr Automata (Python SDK), 2 agents. RAG via Lyzr's built-in KB, or a
  local fallback (`runbooks/*.md` read straight into the prompt — only 3 files, fits
  in context, zero infra).
- **Voice:** Lyzr Studio voice agent (Tier 1).
- **Frontend:** Next.js + Tailwind. EventSource (SSE) client. No state lib needed.
- **State:** `infrastructure_state.json` loaded into memory, mutated in place.

---

## Phase 1 — The world the agents operate in

- `runbooks/` — three fake SOPs in Markdown:
  - `CVE-2026-Shellshock-Mitigation.md`
  - `AWS-Key-Revocation.md`
  - `Ransomware-Containment.md`
- `infrastructure_state.json` — the blast-radius graph: servers → services →
  dependencies → status. e.g. `auth-01` runs `Auth`, depended on by `payment-gw`,
  status `healthy`.
- `mock_alerts/shellshock.json` — a realistic Datadog webhook payload.
- **FastAPI skeleton** with `POST /webhook/trigger` accepting the payload and echoing
  back a parsed summary. Verify with `curl` before any AI is wired in.

**Done when:** `curl`-ing the mock alert at `/trigger` returns 200 with parsed fields.

## Phase 2 — The brain (text pipeline, no voice yet)

- **Agent 1 — Forensic Synthesizer:** input = alert payload + runbooks. Output =
  structured JSON `{severity, vulnerable_server, blast_radius, recommended_action}`.
  *Force JSON output* so Agent 2 and the UI can parse it deterministically.
- **Agent 2 — Commander:** input = Agent 1 JSON. Output = ≤3-sentence spoken script
  ending in a yes/no question. (Day-6 guardrails — sentence cap, fallback line —
  belong in *this* prompt from the start, not bolted on later.)
- Pipeline callable as a plain Python function: `alert_payload → script`.

**Done when:** running the pipeline on the mock alert prints a believable script.

## Phase 3 — Close the loop with Tier-0 (text) approval

- `/webhook/trigger` runs the pipeline and streams progress over **SSE** to the UI.
- `POST /execute` takes `{server_id, action}`, mutates in-memory state, pushes the new
  state over SSE.
- A temporary "Approve / Deny" button in the UI hits `/execute`.

**Done when:** click Trigger → logs stream → click Approve → server flips. *Full loop,
zero voice, zero external keys.* This is the real milestone — everything after is polish.

## Phase 4 — The Terminal UI (Next.js)

- **Left panel:** scrolling terminal of agent/system logs streamed via SSE
  (`[AGENT] Cross-referencing CVE with runbook…`, `[SYSTEM] Requesting approval…`).
- **Right panel:** server tiles from `infrastructure_state.json`; targeted server
  blinks red `[COMPROMISED]`, flips solid green `[ISOLATED]` on the SSE state event.
- The "Trigger Exploit" button POSTs the canned payload. (Nothing is actually
  exploited — it's a scripted alert.)

**Done when:** the demo runs purely from the browser, approval still via button.

## Phase 5 — Tier-1 voice (Lyzr Studio)

- Configure a Lyzr Studio voice agent: **Agent Speaks First**, lowest-latency engine
  available, custom tool `isolate_container` that POSTs to `/execute`.
- Inject the Commander's script per-incident. **Verify Lyzr supports per-call system-
  prompt / context injection at trigger time** — if not, fall back to passing the
  script as a tool/input variable. *(Confirm this early; it's the main integration
  risk.)*
- Swap the Tier-0 button for the voice agent as the approval channel.

**Done when:** browser voice agent speaks the script, you say "yes", server flips.

## Phase 6 — Guardrails & latency (if not already folded into Phase 2/5)

- Hard cap: script ≤ 3 sentences.
- Fallback: unknown question → *"I do not have that context. Escalating to tier 2."*
- Trim any obvious latency in the pipeline (parallelize, cache runbook reads).

## Phase 7 — The 90-second demo

1. Terminal UI on screen. Click **Trigger Exploit**.
2. Audience watches agents reason over the runbooks live.
3. Voice agent speaks the tailored script; you say **"Yes, isolate it."**
4. Server tile flips to `[ISOLATED]` instantly.

Record it. Don't just ship a GitHub link.

---

## Open questions to resolve before Phase 5

- Does Lyzr Studio's voice agent support **per-call prompt/context injection** from an
  external trigger? (Determines how the dynamic script reaches the voice layer.)
- Can a Lyzr custom tool POST to a **public URL**? (Local FastAPI will need a tunnel —
  `ngrok` free tier — so Lyzr's cloud can reach `/execute`.)
