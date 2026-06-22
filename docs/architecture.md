# Architecture

> Scope: system-wide design. Exact shapes in [data-contracts.md](data-contracts.md);
> per-area detail in the other docs.

> **v1 is the foundation; v2 extends it.** v1 proved: alert → 2-agent brain → button
> approval → state flip, streamed over SSE. v2 keeps all of that and adds: a real source
> (Datadog), an **ordered remediation plan**, **autonomous safe-step execution with
> verification**, and **escalation to an on-call engineer over Slack + voice**. None of
> this changes the core seams — it slots into the existing channel + state + SSE design.

> **v3 reframes the core into a human-in-the-loop approval gate.** The product is no longer
> "an AI that auto-fixes incidents"; it's **a gate any external AI agent calls to get a human's
> yes/no before a high-stakes action.** The agent *already decided* what it wants to do — CallSign
> enriches the request (blast radius, risk, a clear summary — reusing the brain) and routes it to a
> human, who decides. **A human decides every high-stakes action by default; autonomy (auto-approve)
> is opt-in and OFF.** Incident response becomes one *requester* (one vertical) of this gate. None of
> this changes the seams either — it generalizes the front door (`/approvals`) and keeps the same
> approval-channel + executor + state + SSE design.

## The flow

Two distinct kinds of "channel" now: a **requester channel** (who *asks* for approval) and an
**approval channel** (who *answers*). Many requesters, one pipe, the same human-decides core:

```
REQUESTERS (who asks)                         CALLSIGN (the gate)                 APPROVAL CHANNELS (who answers)
─────────────────────                         ───────────────────                 ───────────────────────────────
External AI agent ──POST /approvals (§10)──┐
                                           ├─► 1. (optional) ENRICH               UI button ─┐
Incident pipeline ──/webhook/trigger───────┤      blast radius · risk             Slack card ─┤
  (Datadog/Alert §1 → §10)                 │      log-based diagnosis (§13)        voice (later)┤
                                           │      → suggested action               └──┬────────┘
                                           │   2. ROUTE to a human                    │ "approve"/"deny"
                                           │      expertise routing → owner (§8)       │ from ANY channel
                                           │      (fallback: on-call)                  ▼
                                           │   3. capture DECISION  ◄────────────  POST /execute (§6)
                                           └─► 4. DELIVER OUTCOME (§11):                (decision sink)
                                                 • gate mode    → run action via executor (simulate|real)
                                                 • callback mode→ POST outcome to caller; caller acts
                                                 • blocking → return on the open call · async → callback/poll

   live log/state/incident/approval events stream to the Next.js dashboard over SSE the whole time.
```

The incident path (Datadog → Alert §1 → mapped to an ApprovalRequest §10, enriched by the 2-agent
brain) is just the top-left "Incident pipeline" requester. An external agent skips the brain unless
it sends `diagnostics` for log-based diagnosis. Detail: [approval-api.md](approval-api.md),
[triage.md](triage.md).

## Two processes, one channel

- **`backend/`** — FastAPI. Owns alert intake + Datadog mapping, the brain, the remediation
  engine + executor, escalation, in-memory state, and the SSE stream.
- **`frontend/`** — Next.js. Pure view + trigger. HTTP POSTs out, SSE in. No authoritative state.

The browser never pushes in real time, so we use **SSE, not WebSockets** (one-way, built-in
`EventSource`, no handshake lib, free). Browser→backend is ordinary POSTs only.

## Two channel abstractions (the key design idea)

The brain, the engine, and the UI know nothing about *how* a request arrives or *how* a human
approves — only that an **approval request** is opened and later **decided**. Keep two distinct
abstractions apart:

- **Requester channel** = *who asks.* Anything that creates an ApprovalRequest (§10).
- **Approval channel** = *who answers.* Anything that turns human intent into a `/execute` call (§6).

```
Request lifecycle (backend-owned, channel-agnostic):
  CREATED → (optional enrich) → AWAITING_APPROVAL → (human) → APPROVED | DENIED | TIMED_OUT
                                                              → EXECUTED (gate) | RETURNED (callback)
```

**Requester channels (who asks):**

| Requester | How it asks | Status |
|-----------|-------------|--------|
| **External AI agent** | SDK/HTTP `POST /approvals` (§10) | 🔨 the v3 front door |
| **Incident pipeline** | `/webhook/trigger` → Alert (§1) → ApprovalRequest (§10), brain-enriched | ✅ active (the vertical) |
| **Datadog** | webhook → `/webhook/trigger` (mapped, §1b) | ✅ active source for the incident pipeline |

**Approval channels (who answers):**

| Channel | How it resolves | Status |
|---------|-----------------|--------|
| **Auto-approve** | engine POSTs `/execute` itself (`actor: auto`) — **opt-in, OFF by default** | ⚙️ opt-in |
| **UI button** | browser POSTs `/execute` | ✅ active |
| **Slack** | card with Approve/Deny buttons → `/execute` (`actor: <slack_user_id>`) | ✅ active (primary channel) |
| **Lyzr text agent** | `resolve_incident` tool → `/execute` (`actor: voice`) | configured, `VOICE_ENABLED=false` |
| **Lyzr voice agent** | voice + `resolve_incident` tool → `/execute` (`actor: voice`) | future — needs voice premium |
| **Phone call** | Twilio outbound + voice agent → `/execute` | future |

Adding/removing either kind of channel never touches the brain, engine, state, or contracts.
**The UI-button + Slack channels prove everything**, exactly as in v1/v2.

## Gate vs callback mode & blocking vs async wait

Two independent dimensions on every ApprovalRequest (§10), set by the caller:

- **Execution mode** — what happens on "approve":
  - **gate** — CallSign runs the `action` itself through the executor (simulate|real). Best for
    infra actions it has an adapter for. This is the v1/v2 behavior.
  - **callback** — CallSign runs *nothing*; it returns the decision and the caller executes its own
    action. Lets the gate broker a yes/no for things it has no executor for (refunds, deletes, emails).
- **Wait model** — how the caller gets the outcome (§11):
  - **blocking** — the caller's `POST /approvals` is held open until a human decides (or timeout),
    then returns the outcome. Simplest; great for demos.
  - **async** — returns `request_id` immediately; the outcome arrives via a `callback_url` POST or
    `GET /approvals/{id}` polling.

Mode and wait are orthogonal (e.g. callback+blocking, gate+async are both valid). See
[approval-api.md](approval-api.md).

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

Incident status lifecycle (§5) — the incident vertical's richer names for the generic request
lifecycle. By default it goes straight to a human (`escalated → awaiting_approval`); the
`resolved`-via-auto-remediation path only runs when auto-approve is explicitly enabled
(opt-in, off by default):
```
received → diagnosing → remediating → verifying → resolved   (only if auto-approve is enabled)
                                            └────► escalated → awaiting_approval → resolved | failed
```

## SSE event contract (summary)

`GET /stream` emits named events; the UI routes on name. Full payloads in §7.
- `log` — a terminal line (sources: `SYSTEM | AGENT | REMEDIATION | SLACK | VOICE`)
- `state` — the full infra state (UI re-renders tiles)
- `incident` — the full incident object on every transition (drives all incident UI)
- `approval` — a generic approval request (§10) created/updated; drives the approvals dashboard
  for requests that aren't incidents

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
- **Requester + approval-channel + executor abstractions:** one generic pipe, many front doors
  (agent API, incident pipeline) and many answer channels (button + simulate today; Slack, voice,
  callback, real infra later) — same backend throughout.
- **Human decides by default:** auto-approve is opt-in and off. The product's value is a fast,
  well-scoped *human* checkpoint — not autonomous action (which is risky and already commoditized).
