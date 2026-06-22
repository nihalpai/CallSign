# Testing — full end-to-end without the other project

> Scope: how to exercise **every feature** of the approval gate end-to-end. The headline: because
> the system is **simulate-first / disabled-but-logged** (CLAUDE.md golden rules), you test the whole
> product with a tiny **fake-agent** driver — **no don-drapor, no cloud accounts.** The real project
> is only ever needed for the optional "make one action genuinely real" finale.

## The test driver: a fake agent

The thing calling the gate doesn't have to be a real app — it just makes an HTTP call. So the driver
is a ~20-line throwaway script that pretends to be a customer's agent: it `POST`s to `/approvals`
with a canned action (and optional canned logs), waits, and prints the decision. One script can drive
every code path. Keep a few of these under `harness/` (see below); they double as the **demo**.

## Three layers

1. **Automated (pytest)** — extend the existing suite (the 171 backend tests) with cases for
   `/approvals` blocking + callback, API-key auth (200/401), routing match + fallback, and
   log-diagnosis parsing. Fast, hermetic, zero accounts (`tests/conftest.py` already forces the
   deterministic brain + disabled integrations).
2. **Manual E2E (the harness)** — run the backend, run a fake-agent script, watch it flow through to
   a human and back. Slack either logs the card (`SLACK_ENABLED=false`) or posts for real to a **free
   throwaway Slack workspace** (not don-drapor). The browser shows the approvals dashboard live.
3. **Frontend E2E (Playwright)** — one happy-path journey: a request appears in the dashboard →
   Approve → it flips to approved.

## Feature coverage — how to trigger each, and what's real vs simulated

| Feature | How you trigger it | Real / simulated |
|---|---|---|
| Generic gate (`POST /approvals`) | fake-agent script posts an action | real call, sim everything else |
| Blocking wait | script calls, blocks, you approve, it returns | real |
| Callback / async | script passes a `callback_url` (a tiny local listener) | real |
| Gate execution mode | action is a §4b action; executor runs it | **simulated** infra |
| Callback execution mode | script runs its "own" action on `approved` | real (it's your script) |
| API-key auth | call with / without `X-API-Key` → 200 / 401 | real |
| Enrichment | `ENRICH_REQUESTS=true` → brain adds risk / blast radius | real brain (or deterministic fallback, no key) |
| Log-based diagnosis | script sends a canned `stack_trace` in `diagnostics` (§13b) | real diagnosis on fake logs |
| Expertise routing | seed `on_call.json` `owns`; send an action in that area | real routing logic |
| Routing fallback | send an action no one owns → on-call | real |
| Slack card + Approve/Deny | `SLACK_ENABLED=false` logs it, or a free Slack posts it | your choice |
| Approvals dashboard + SSE | watch the request appear / flip in the browser | real |
| Incident vertical | `curl` a canned Datadog-shaped payload at `/webhook/trigger` | real pipeline, sim infra |
| Opt-in auto-approve | flip `AUTO_REMEDIATE=true`, send a low-risk action | real |

That table is **100% of the product logic** — none of it needs the other project.

## A full E2E pass (one sitting)

1. Start the backend (simulate mode); set `APPROVAL_API_KEY`, `ENRICH_REQUESTS=true`,
   `EXPERTISE_ROUTING=true`; seed `on_call.json` with `owns` areas. Open the dashboard.
2. Run `harness/error_with_logs_bot` → it POSTs an action + a canned stack trace, blocking.
3. Watch: the request is **enriched** (location pinpointed from the trace), **routed** to the owning
   engineer, and a **Slack card** appears (logged or in your free Slack) — and shows on the dashboard.
4. Click **Approve** → the decision returns to the bot (blocking) → the request flips to approved live.
5. Repeat with `harness/refund_bot` (callback mode, no logs) and a `curl` at `/webhook/trigger` (the
   incident vertical) to cover the other paths. Flip `AUTO_REMEDIATE=true` once to see opt-in auto-approve.

## The harness (build alongside N3)

`harness/` — small fake-agent scripts, each exercising one path. Suggested set:
- `refund_bot` — callback mode, blocking, no diagnostics (the plain gate).
- `delete_bot` — callback mode, async + `callback_url` (a tiny local listener prints the outcome).
- `error_with_logs_bot` — gate mode, sends `diagnostics` (smart triage: diagnosis + routing).
- `trigger_incident.sh` — `curl`s a canned Datadog payload at `/webhook/trigger` (the vertical).

These are your manual E2E checklist **and** your demo script. Keep them out of the published SDK.

## When the other project (don-drapor) is actually needed

Only for the two **optional "genuinely real" showcases** — never to verify a feature works:

1. **Real Datadog monitor as the source** — instrument don-drapor so a real alert fires
   `/webhook/trigger`. Proves the "real alert" wow-moment; the curl proves the same path.
2. **Real executor (real rollback)** — deploy don-drapor (Render/Vercel) + one provider adapter, then
   `EXECUTION_MODE=real`. The one thing that touches real infra. A swapped adapter, not a new test setup.

Both are the finale, not the test plan. Everything else is covered by the harness in simulate mode.
