# Architecture

> Scope: system-wide design. For exact data shapes see
> [data-contracts.md](data-contracts.md). For per-area detail see the other docs.

## The flow

```
 [Trigger button] ──POST canned alert──► FastAPI  POST /webhook/trigger
                                                │
                                                │ 1. parse alert
                                                │ 2. run Lyzr Automata brain
                                                ▼
                                      Lyzr Automata "brain"
                                      ├─ Agent 1  Forensic Synthesizer (RAG over runbooks)
                                      └─ Agent 2  Commander            (3-sentence script)
                                                │
                          ┌─────────────────────┼──────────────────────┐
                          │ stream log events    │ open an "incident"   │
                          ▼ (SSE)                ▼ awaiting approval     │
                    Next.js UI            Approval channel               │
                    ├ Left: live logs     (Tier 0 button / Tier 1 Lyzr  │
                    └ Right: server         voice / Tier 2 phone)        │
                       tiles                     │                       │
                          ▲                      │ "yes" → isolate       │
                          │ state event (SSE)    ▼                       │
                          └──────────────  POST /execute ◄───────────────┘
                                                │
                                         mutate in-memory infra state
                                         emit state event over SSE
```

## Two processes, one channel

- **`backend/`** — FastAPI. Owns the alert intake, the Lyzr brain, the in-memory
  infrastructure state, and the SSE stream.
- **`frontend/`** — Next.js. Pure view + trigger. Talks to the backend over HTTP
  (POSTs) and an SSE subscription (receives). It holds no authoritative state.

The browser **never** needs to push to the backend in real time, which is why we use
**SSE, not WebSockets**. SSE is one-way (server→browser), has a trivial built-in client
(`EventSource`), needs no handshake library, and is free. The only browser→backend
traffic is ordinary POSTs (trigger, and the Tier-0 approve button).

## The approval-channel abstraction (the key design idea)

The original plan wired the phone call deep into the flow. That couples the demo to
telephony we don't have. Instead, the brain and the UI know nothing about *how* a human
approves — they only care that an **incident** is opened and later **resolved**.

```
Incident lifecycle (backend-owned, channel-agnostic):
  OPEN(incident_id, server_id, action, script)
        │
        │  ← resolution arrives from SOME channel
        ▼
  RESOLVE(incident_id, decision: approve | deny)
```

A **channel** is anything that turns a human's intent into a `RESOLVE` call:

| Tier | Channel | How it calls RESOLVE | Deps |
|------|---------|----------------------|------|
| 0 | UI button | Browser POSTs `/execute` | none |
| 1 | Lyzr Studio voice (browser mic) | Lyzr tool `isolate_container` POSTs `/execute` | Lyzr Studio |
| 2 | Real phone call | same Lyzr tool, telephony front-end | Twilio + STT/TTS |

Moving up a tier swaps the channel only. `/webhook/trigger`, the brain, the state
machine, and the UI are unchanged. **Build Tier 0 first; it proves everything.**

## State model

`infrastructure_state.json` is loaded into memory at startup into a single module-level
object (see [backend.md](backend.md)). Mutations happen in place; every mutation emits a
`state` SSE event so all connected browsers stay in sync. No DB, no persistence across
restarts — intentional for a PoC.

Server status lifecycle for the demo:
```
healthy ──(alert fires)──► compromised ──(approval)──► isolated
```

## SSE event contract (summary)

The backend exposes `GET /stream` (SSE). It emits typed events; the UI routes on type.
Full payloads in [data-contracts.md](data-contracts.md). Types:

- `log`   — a line for the terminal panel (agent/system narration)
- `state` — the full current infrastructure state (UI re-renders tiles)
- `incident` — an incident opened / resolved (drives "awaiting approval" UI)

We send the **whole** state on each `state` event (it's tiny) rather than diffs — far
simpler and robust to a browser that connected late.

## Failure & latency posture (PoC)

- If the Lyzr brain errors, emit a `log` event with the error and fall back to a static
  script so the demo still runs.
- Latency target is "feels live," not a hard SLO. Read runbooks once at startup; run the
  two agents sequentially (Agent 2 needs Agent 1's output).
- One incident at a time is fine for the demo; don't build a queue.

## Why these choices

- **SSE over WebSocket:** no bidirectional need; less code; free.
- **In-memory state:** PoC; restart resets the demo, which is actually convenient.
- **Channel abstraction:** lets us demo today (button), upgrade to the impressive voice
  version without rework, and reach real telephony later — same backend throughout.
