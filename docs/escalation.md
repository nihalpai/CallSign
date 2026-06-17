# Escalation

> Scope: what happens when the [remediation engine](remediation.md) decides a human is
> needed — selecting the on-call engineer and reaching them across Slack + voice. Channel
> specifics are in [slack.md](slack.md) and [voice.md](voice.md); shapes in
> [data-contracts.md](data-contracts.md) §8 (on-call) and §9 (Slack card).

## When escalation fires

The engine escalates when **any** of:
- the next plan step is `autonomy: "human"`, or
- all `auto` steps ran and `verify()` never cleared the alert, or
- the severity gate tripped (incident ≥ `AUTO_REMEDIATE_MAX_SEVERITY`).

At that point `incident.status → escalated` and this pipeline runs.

## Step 1 — select the on-call engineer

`app/escalation.py :: select_engineer()` reads the static registry (§8) and applies:

```
awake_and_available(e) =
    e.status == "active"
    AND local_now(e.timezone) ∈ [e.shift_start, e.shift_end)   # handles midnight wrap
first match wins (registry order = priority); tie-break by order.
fallback: if nobody matches, pick the first "active" engineer and log "[SYSTEM] off-hours —
          paging <name> anyway".
```

Set `incident.assigned_engineer` (§5) and emit a `log` (source `SYSTEM`):
`"Escalating to Priya (on-call, 02:14 local)."`

## Step 2 — fan out to the engineer's channels

Driven by config toggles (`SLACK_ENABLED`, `VOICE_ENABLED`). Both can be on; they're
independent and converge on the same `/execute` (§6).

```
selected engineer
   ├─ if SLACK_ENABLED → post incident card (§9) to engineer's slack_id  → see slack.md
   │      emits log (source SLACK): "Posted incident to #oncall / @priya"
   └─ if VOICE_ENABLED → Lyzr voice agent calls engineer.phone with plan.script → see voice.md
          emits log (source VOICE): "Calling Priya (+1…) — reading approval script"
```

The Slack card and the voice call **both** carry the same `incident_id`, `action`, `target`
so whichever the engineer responds through resolves the incident. The CallSign UI link in
the Slack card is the third path (engineer clicks → approves in the UI).

## Step 3 — resolution

The first channel to produce a decision wins and POSTs `/execute` (§6) with the right
`actor` (`voice`, the `engineer_id` for a UI/Slack click). The engine runs the approved
action via the active executor. Late responses on other channels hit the idempotency guard
(no-op). Emit a closing `log` and an updated `incident` (`resolved`), and post a Slack
thread reply ("✅ Resolved by Priya — rolled back to dpl_8e1").

## Autonomy boundary (state it plainly)

CallSign **never** performs a `human`-tagged or above-severity action without an explicit
engineer approval arriving via `/execute`. Auto-remediation is limited to `auto`-tagged,
reversible, below-gate steps. Escalation is the seam between machine autonomy and human
authority.

## What lives where (for the build)

- `app/escalation.py` — `select_engineer()` + `escalate(incident)` orchestration.
- On-call registry loaded from `data/on_call.json` (§8) at startup.
- Slack + voice are invoked through their integration modules; escalation only *coordinates*.

## Out of scope now
- Rotation schedules beyond a single static shift window, paging retries/acks, multi-tier
  escalation ladders. One selected engineer per incident is enough for the demo.
