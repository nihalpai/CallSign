# CallSign — External Setup Guide

What you need to provide **externally** (accounts, API keys, config) to light up each
capability. **Everything runs today in simulate mode with ZERO external accounts** — this
guide is the upgrade path. Single-tenant for now (one `APPROVAL_API_KEY`, your own Slack). All
secrets go in `backend/.env` (gitignored); see `backend/.env.example` for the full list.

---

## 0. Run it right now (nothing required)

```
cd backend && .venv/bin/uvicorn app.main:app --port 8000     # :8000
cd frontend && npm run dev                                    # :3000
```
Open http://localhost:3000 → "Simulate Alert" → FIRE. The brain uses the deterministic
fallback, remediation is simulated, Slack/voice/Datadog are disabled-but-logged. **No keys.**

Debug logs stream to `backend/logs/callsign.log` (rotating) and the console.

---

## A. External agent setup (how others hook up) — *the v3 gate*

Connect *any* AI agent so it pauses for a human before a risky action. See
`docs/sdk.md` + `docs/approval-api.md`.

1. Set a shared key in `backend/.env` (single-tenant for now):
   ```
   APPROVAL_API_KEY=cs_live_...        # callers send it as the X-API-Key header
   ```
2. The caller installs the client (`pip install callsign`) or just POSTs to `/approvals`.
3. One call before the risky action — and, optionally, attach `diagnostics` (logs) so the
   request arrives pre-diagnosed and routed to the right expert:
   ```python
   decision = approve(api_key="cs_live_...", base_url="https://<your-backend>",
                      action="Refund $5,000 to customer 8831",
                      context="Disputed duplicate charge", mode="callback", timeout=300)
   if decision.approved: issue_refund()
   ```
Without `APPROVAL_API_KEY` set, `/approvals` rejects with 401. Multi-tenant signup / per-customer
key issuance is **future**.

## B. Ownership map (expertise routing) — *no code access*

Route approvals to the engineer who **owns** the affected area, not just whoever's on-call.
See `docs/triage.md`.

1. In `backend/data/on_call.json`, give each engineer an **`owns`** list (service ids, service
   names, or route prefixes — §8):
   ```json
   { "id": "eng-02", "name": "Priya", "slack_id": "U02PRIYA", "owns": ["payment-gw", "Payments", "/api/checkout"], "...": "shift fields" }
   ```
2. Turn it on: `EXPERTISE_ROUTING=true` in `backend/.env`.
3. Behavior: a diagnosed area is matched to an owner; if none matches (or they're unavailable) it
   **falls back** to the on-call rule. Best-effort by design.

Boosters — **deploy metadata** (caller-sent), **read-only Git/CODEOWNERS**, and **past-incident
memory** — are *future*; the uploaded ownership map needs zero code access.

---

## 1. Lyzr Studio brain (Diagnostician + Strategist) — *uses your Lyzr credits*

Optional **enrichment** — blast radius, risk, a clear summary, log-based diagnosis — replacing the
deterministic fallback with real AI. It never decides approve/deny. See `docs/agents.md`.

1. In **Lyzr Studio**, create **two agents**:
   - **Diagnostician** — paste the system prompt from `docs/agents.md` (Agent 1). Attach the
     `backend/runbooks/*.md` files as its **Knowledge Base**.
   - **Strategist** — paste the system prompt from `docs/agents.md` (Agent 2).
2. Copy each agent's **agent id** and your Studio **API key** (`x-api-key`).
3. Put in `backend/.env`:
   ```
   LYZR_API_KEY=sk-...
   LYZR_DIAGNOSTICIAN_AGENT_ID=...
   LYZR_STRATEGIST_AGENT_ID=...
   # LYZR_API_BASE defaults to https://agent-prod.studio.lyzr.ai
   ```
Without these the brain silently falls back (and logs a `[SYSTEM]` warning). Confirm the
exact Agent API field names at **docs.lyzr.ai** if a call fails.

## 2. Lyzr Studio voice agent — *uses your Lyzr credits + a public URL*

The phone call on escalation. See `docs/voice.md`.

1. Create a **third** Studio agent: a **voice agent**, *Agent Speaks First*, lowest-latency
   engine. Add a custom tool **`resolve_incident`** that POSTs to
   `{PUBLIC_BACKEND_URL}/execute` (body: incident_id, decision, action, target, actor:"voice").
2. `backend/.env`:
   ```
   LYZR_VOICE_AGENT_ID=...
   VOICE_ENABLED=true
   PUBLIC_BACKEND_URL=https://<your-ngrok>.ngrok-free.app
   ```
3. **Confirm per-call context injection** in Studio (the one open risk) — how the script +
   incident ids reach the call. See `docs/voice.md`.
4. Real outbound phone calls (Tier 2) additionally need **Twilio + Deepgram/ElevenLabs** —
   future, optional.

## 3. ngrok (free) — public URL so Lyzr/Datadog/Slack can reach your local backend

```
ngrok http 8000
```
Use the `https://…` URL as `PUBLIC_BACKEND_URL`. The backend already allows ngrok origins in CORS.

## 4. Slack bot — *needs a Slack app*

Posts the incident card to the on-call engineer. See `docs/slack.md`.

1. Create a Slack app; add a **Bot Token** with scopes `chat:write`, `chat:write.public`
   (+ `commands`/`interactivity` only if you enable in-Slack Approve/Deny buttons).
2. `backend/.env`:
   ```
   SLACK_ENABLED=true
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_SIGNING_SECRET=...
   # SLACK_INTERACTIVE=true   # optional: enable /slack/interactions Approve/Deny buttons
   ```
3. Put real Slack user ids in `backend/data/on_call.json` (`slack_id`).
4. **Note:** Slack *huddles* can't be started via API — the bot posts a message + the Lyzr
   voice agent calls. (`SLACK_CALL_MODE` is a documented future toggle, not built.)

## 5. Datadog — *Pro trial + your monitored app ("Don Draper")*

Real alerts instead of the Simulate button. See `docs/datadog.md`.

1. Build/test **without Datadog first** — POST a Datadog-shaped body to
   `{PUBLIC_BACKEND_URL}/webhook/trigger` (the mapper handles it).
2. When ready: Datadog **Pro trial** → instrument Don Draper (Agent/APM) → create a Monitor
   → add a **Webhook** whose URL is `{PUBLIC_BACKEND_URL}/webhook/trigger` and whose payload
   body is the template in `docs/data-contracts.md` §1b → notify it from the monitor.
3. Tag the monitor with `service:` `host:` `route:` `deploy:` so the brain can locate the issue.

## 6. Real remediation (flip simulate → real) — *provider creds*

Make actions actually affect infra. See `docs/remediation.md`.

```
EXECUTION_MODE=real          # default is "simulate"
```
This requires implementing **one provider adapter** (e.g. Vercel rollback) under
`app/remediation/adapters/` — currently a documented **stub** (raises NotImplementedError).
Until an adapter exists, keep `EXECUTION_MODE=simulate`. Plus the provider's own creds
(e.g. `VERCEL_TOKEN`). This is milestone **M6**.

---

## Quick reference — `.env` toggles

| Capability | Keys to set | Toggle |
|---|---|---|
| External agent gate (`/approvals`) | `APPROVAL_API_KEY` | (required for the public front door) |
| Enrichment (brain on a request) | — | `ENRICH_REQUESTS=true` (default) |
| Expertise routing | `owns` in `on_call.json` | `EXPERTISE_ROUTING=true` |
| Opt-in auto-approve | — | `AUTO_REMEDIATE=true` (**default off**) |
| Real AI brain | `LYZR_API_KEY`, `LYZR_DIAGNOSTICIAN_AGENT_ID`, `LYZR_STRATEGIST_AGENT_ID` | (auto when set) |
| Voice call (future channel) | `LYZR_VOICE_AGENT_ID`, `PUBLIC_BACKEND_URL` | `VOICE_ENABLED=true` |
| Slack | `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` | `SLACK_ENABLED=true` |
| Datadog | (webhook config in Datadog) + `PUBLIC_BACKEND_URL` | — |
| Real infra actions (gate mode) | provider creds + an adapter | `EXECUTION_MODE=real` |

Leave everything unset → full simulate demo, no accounts, nothing real touched, every action
waits for a human.
