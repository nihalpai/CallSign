# Escalation — routing an approval request to a human

> Scope: how CallSign selects the right approver and notifies them (Slack today; voice is future).
> Shapes: [data-contracts.md](data-contracts.md) §8 (ownership registry) and §9 (Slack card).

Routing to a human is the **default path** for every request. Auto-approve is opt-in and OFF.

## Expertise routing

When `EXPERTISE_ROUTING=true`, CallSign prefers the engineer who **owns** the diagnosed area over
whoever is simply on-call.

```
area = request.target  (or the area inferred from context)
owner = first available engineer whose `owns` (§8) matches area
if owner found → page the owner ("[SYSTEM] Routing to Priya — owns Payments")
else           → FALL BACK to the on-call rule below
```

The `owns` field in `data/on_call.json` (§8) is a list of service ids, service names, or route
prefixes this engineer owns.  Fill it in for the demos; the code matches against any element.

## On-call rule (default, and the fallback)

```
awake_and_available(e) =
    e.status == "active"
    AND local_now(e.timezone) ∈ [e.shift_start, e.shift_end)   # handles midnight wrap
first match wins (registry order = priority); tie-break by order.
fallback: if nobody matches, pick the first "active" engineer and log "[SYSTEM] off-hours —
          paging <name> anyway".
```

Routing is **best-effort** — it degrades to on-call gracefully when ownership data is missing.
An explicit `approvers` hint on the request (§10) overrides selection entirely.

## Notification channels

Driven by config toggles (`SLACK_ENABLED`, `VOICE_ENABLED`).  Both can be on independently; both
converge on the same `/execute` endpoint (§6).

```
selected engineer
   ├─ if SLACK_ENABLED → post approval card (§9) to engineer's slack_id  → see slack.md
   └─ if VOICE_ENABLED → Lyzr voice agent calls engineer.phone             (future; disabled)
```

The Slack card carries a link to the CallSign dashboard — the engineer can approve via the card
button (requires ngrok for Slack interactivity callback) or via the dashboard link.

## Resolution

The first response wins.  `/execute` (§6) fires the approved action (gate mode) or returns the
decision to the caller (callback mode).  Late responses on other channels hit the idempotency
guard.

## Autonomy boundary

By default CallSign performs **no** action without an explicit human approval. Auto-approve
(`AUTO_REMEDIATE`) is **opt-in and OFF**; even when enabled, it is limited to `auto`-tagged,
reversible steps.

## Implementation

- `app/escalation.py` — `select_engineer()`.
- On-call registry loaded from `data/on_call.json` (§8) at startup.
