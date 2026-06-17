# Architecture

> Scope: system-wide design. Exact shapes in [data-contracts.md](data-contracts.md);
> per-area detail in the other docs.

> **v1 is the foundation; v2 extends it.** v1 proved: alert → 2-agent brain → button
> approval → state flip, streamed over SSE. v2 keeps all of that and adds: a real source
> (Datadog), an **ordered remediation plan**, **autonomous safe-step execution with
> verification**, and **escalation to an on-call engineer over Slack + voice**. None of
> this changes the core seams — it slots into the existing channel + state + SSE design.

## The v2 flow

```
Don Draper (prod) incident ──Datadog webhook──► POST /webhook/trigger
                                                      │ map → Alert (§1)
                                                      ▼
                                    Brain (Lyzr Studio agents · Agent API)
                                            ├─ Agent 1 Diagnostician → Diagnosis (§3)
                                            └─ Agent 2 Strategist    → Plan + script (§4)
                                                      ▼
                                       ┌──── Remediation Engine ─────┐
                                       │ policy: auto-fix safe steps │
                                       │ verify after each step      │
                                       └──────────────┬──────────────┘
                                  resolved ◄──────────┤────────► escalate
                                  (auto-fix worked)   │          (needs a human)
                                                      ▼
                                              Escalation
                                              ├─ select on-call engineer (§8)
                                              ├─ Slack card + buttons (§9) ──┐ same incident
                                              └─ voice agent (future)  ──────┤
                                                      │             │
                          ┌───────────────────────────┼─────────────┘
                          │ stream log/state/incident  │ "approve" from ANY channel
                          ▼ (SSE)                       ▼
                    Next.js UI ◄──────────────  POST /execute ──► Remediation Engine
                    (live war-room)                              (executor: simulate|real)
```

## Two processes, one channel

- **`backend/`** — FastAPI. Owns alert intake + Datadog mapping, the brain, the remediation
  engine + executor, escalation, in-memory state, and the SSE stream.
- **`frontend/`** — Next.js. Pure view + trigger. HTTP POSTs out, SSE in. No authoritative state.

The browser never pushes in real time, so we use **SSE, not WebSockets** (one-way, built-in
`EventSource`, no handshake lib, free). Browser→backend is ordinary POSTs only.

## The approval/escalation-channel abstraction (the key design idea)

The brain, the engine, and the UI know nothing about *how* a human approves — only that an
**incident** is opened and later **resolved**. A **channel** is anything that turns human
intent into a `/execute` call (§6).

```
Incident lifecycle (backend-owned, channel-agnostic):
  OPEN → (auto-remediation) → RESOLVE   OR   OPEN → ESCALATE → (human) → RESOLVE
```

| Channel | How it resolves | Status |
|---------|-----------------|--------|
| **Auto-remediation** | engine POSTs `/execute` itself (`actor: auto`) for `auto` steps | ✅ active |
| **UI button** | browser POSTs `/execute` | ✅ active |
| **Slack** | DM card with Approve/Deny buttons → `/execute` (`actor: <slack_user_id>`) | ✅ active (primary escalation channel) |
| **Lyzr text agent** | `resolve_incident` tool → `/execute` (`actor: voice`) | configured, `VOICE_ENABLED=false` |
| **Lyzr voice agent** | voice + `resolve_incident` tool → `/execute` (`actor: voice`) | future — needs voice premium |
| **Phone call** | Twilio outbound + voice agent → `/execute` | future |

Adding/removing a channel never touches the brain, engine, state, or contracts. **Build the
UI-button channel first; it proves everything**, exactly as in v1.

## The Executor toggle (simulate ⇄ real)

Remediation actions run through a single `RemediationExecutor` interface with
`SimulatedExecutor` (default, in-memory) and a future `RealExecutor(provider)`. **Switching
to real infra is `EXECUTION_MODE=real` + creds — no other change.** Full detail in
[remediation.md](remediation.md). This is a hard architectural rule: provider SDKs live only
inside adapters.

## State model

`infrastructure_state.json` (§2) and `deployments.json` (§2b) load into memory at startup,
mutate in place; every mutation emits a `state` SSE event. No DB, no cross-restart
persistence — intentional for a PoC (restart resets the demo).

Server status lifecycle:
```
healthy ──(incident)──► compromised | degraded ──(remediation)──► isolated | rolled_back ──(verify)──► recovered
```

Incident status lifecycle (§5):
```
received → diagnosing → remediating → verifying → resolved
                                            └────► escalated → awaiting_approval → resolved | failed
```

## SSE event contract (summary)

`GET /stream` emits named events; the UI routes on name. Full payloads in §7.
- `log` — a terminal line (sources: `SYSTEM | AGENT | REMEDIATION | SLACK | VOICE`)
- `state` — the full infra state (UI re-renders tiles)
- `incident` — the full incident object on every transition (drives all incident UI)

Whole-state on each event (it's tiny) — simpler and robust to late-joining browsers.

## Failure & latency posture (PoC)

- The brain is an **external HTTP dependency on Lyzr Studio** (Agent API). Any brain error —
  no key, API timeout, non-2xx, unparseable reply — falls back to the deterministic engine (a
  static diagnosis/plan/script) and logs it; the loop must still run. Executor defaults to
  **simulate** so nothing real breaks. So Lyzr Studio is the brain in the real demo, but
  nothing *hard*-depends on it.
- One incident at a time; no queue.
- Agents run sequentially (Strategist consumes Diagnostician).

## Why these choices

- **SSE over WebSocket:** no bidirectional need; less code; free.
- **In-memory state:** PoC; restart resets the demo (convenient).
- **Channel + executor abstractions:** demo today (button + simulate), upgrade to voice /
  Slack / real infra later — same backend throughout.
