# Slack integration

> Scope: CallSign's Slack bot — the **primary active approval channel** while voice is
> unavailable. Posts the **approval card** to the routed approver as a DM with interactive
> Approve/Deny buttons. One approval channel under the channel abstraction
> ([architecture.md](architecture.md)); invoked by [escalation.md](escalation.md).
> Card shape in [data-contracts.md](data-contracts.md) §9.

> **v3:** the card generalizes from an *incident card* to an **approval card** that works for any
> request — an external agent's refund/delete as well as an incident. The incident card is one
> template of it. Single-tenant for now (one workspace); see *Multi-tenant* below.

## Current status

Slack is **fully wired and active**. The approve/deny buttons are enabled. Voice is
disabled (`VOICE_ENABLED=false`) — Slack is the sole escalation channel until voice
premium is available. See [voice.md](voice.md) for the upgrade path.

## What the bot does

1. **Post the approval card** to the routed approver's Slack DM via `chat.postMessage`.
   The card carries:
   - The **action** requested + **risk** (and, for incidents, severity + affected service)
   - **Context / blast radius** — and, when triage ran, the diagnosed **location + probable cause**
     ([triage.md](triage.md))
   - A short summary, and (incident vertical) the **Strategist's spoken script** — the ≤3-sentence
     approval prompt, displayed prominently so the approver has full context
   - **Approve** and **Deny** buttons (wired to `/slack/interactions`)
   - **Open CallSign** deep-link into the UI (`/incident/{id}` or the request view)

2. **Thread updates** as the incident progresses via `chat.postMessage` with `thread_ts`:
   - `✅ Resolved — rolled back to dpl_8e1`
   - `❌ Denied — staying escalated`

3. **Interactive approval** — Approve/Deny buttons POST to `/slack/interactions`. The
   handler verifies the Slack signing secret (HMAC-SHA256), derives the actor from the
   Slack user who clicked, and calls `/execute` (§6) with `actor: <slack_user_id>`.

## App setup

The Slack app is provisioned. Checklist for reference:

- [x] Slack app created at api.slack.com/apps
- [x] Bot Token scopes: `chat:write`, `chat:write.public`, `im:write`
- [x] App installed to workspace — `SLACK_BOT_TOKEN` (xoxb-…) in `.env`
- [x] `SLACK_SIGNING_SECRET` in `.env`
- [x] Interactivity enabled — Request URL: `{PUBLIC_BACKEND_URL}/slack/interactions`
- [x] Engineer `slack_id` values populated in `data/on_call.json`

## Multi-tenant (FUTURE)

Today this is **single-tenant**: one Slack workspace, its `SLACK_BOT_TOKEN`/`SLACK_SIGNING_SECRET`
in `.env`, and approver `slack_id`s hardcoded in `data/on_call.json`. The bot posts to that one
workspace only.

For real external customers, each would connect **their own** Slack workspace (Slack OAuth install
→ per-customer bot token) so their humans get pinged. That's **out of scope for the PoC** and depends
on the multi-tenant work (signup + per-customer key issuance, see [approval-api.md](approval-api.md)).

## Toggles

| Toggle | Current value | Effect |
|---|---|---|
| `SLACK_ENABLED` | `true` | Master switch — posts the incident card on escalation |
| `SLACK_INTERACTIVE` | `true` | Renders Approve/Deny buttons and enables `/slack/interactions` |
| `SLACK_CALL_MODE` | `off` | Future: Calls API "Join" button (not built) |

## Simulate-friendliness

When `SLACK_ENABLED=false`, the integration logs the card it *would* post as a `SLACK`
log event — no network call, no workspace needed. The whole escalation flow is still
demoable offline.

## What the card looks like

```
🚨 SEV-1 · payment-gw (payment-gw)

Where: `/api/checkout` · deploy `dpl_9f2` · (`a1b2c3d`)
What:  5xx on /api/checkout spiked to 40% after deploy dpl_9f2.

📞 Severity one: checkout is failing for forty percent of users right after
the last deploy to Payments. I can roll it back to the previous good version.
Do you approve the rollback?

[ Open CallSign ]  [ Approve ]  [ Deny ]
```

The 📞 block is `plan.script` — the exact text the voice agent would have spoken.

For a **generic agent request** (no incident/script), the card instead leads with the action, risk,
and context — e.g.:

```
🟠 Approval needed · support-refund-bot

Action: Refund $5,000 to customer 8831
Risk:   high · irreversible
Why:    Customer disputed a duplicate charge (agent confidence 0.72)

[ Open CallSign ]  [ Approve ]  [ Deny ]
```

## ngrok requirement

`PUBLIC_BACKEND_URL` must be set for:
- The **Open CallSign** deep-link in the card to point to the right UI
- Slack's interactivity POST to reach `/slack/interactions`

```bash
ngrok http 8000
# paste the https URL into PUBLIC_BACKEND_URL in .env
# and update the Request URL in your Slack app's Interactivity settings
```

Note: the ngrok URL changes on every restart (unless you have a paid fixed domain).
Update both `.env` and the Slack app Interactivity Request URL each time.

## What lives where

- `app/integrations/slack.py` — `post_incident(engineer, incident, log)`, `post_thread(...)`,
  no-op/log mode when `SLACK_ENABLED=false`. Card includes `plan.script` as the 📞 block.
- `app/routes/slack.py` — `POST /slack/interactions` — signature-verified, maps
  Slack button clicks to `/execute` calls.
- `app/escalation.py` — calls `slack_module.post_incident(...)` on every escalation.

## Out of scope

Huddles (no public Slack API), Slack slash commands, Calls API join button,
message edits/updates beyond thread replies.
