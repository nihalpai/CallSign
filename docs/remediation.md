# Remediation engine

> Scope: how CallSign turns a remediation **plan** ([data-contracts.md](data-contracts.md) §4)
> into action — what it runs itself, what it escalates, and how "simulate today / real
> tomorrow" is a single toggle. This is the heart of v2.

## Mental model

```
plan (§4 steps)  ──►  Remediation Engine  ──►  Executor (simulate | real)  ──►  infra
                          │ policy: "auto-fix safe, escalate rest"
                          │ verify after each auto step
                          └─► escalate (see escalation.md) when needed
```

The engine is **channel-agnostic and executor-agnostic**. It decides *what* to attempt and
*when to involve a human*; the Executor decides *how* an action actually happens.

## The Executor toggle (the design principle that must not be compromised)

A single interface, selected by the `EXECUTION_MODE` config (default `simulate`):

```
RemediationExecutor (interface / Protocol)
    run(action: str, target: str) -> ExecResult     # ExecResult: {ok, detail}
    verify(incident) -> bool                          # did the alert clear?

  ├─ SimulatedExecutor   (EXECUTION_MODE=simulate)  ← default, the only one built now
  │     mutates §2 status + §2b deployments in memory, emits events, touches nothing real
  │     verify(): scriptable outcome (see "Verification" below)
  │
  └─ RealExecutor(provider)   (EXECUTION_MODE=real)  ← future, not built yet
        delegates to a provider adapter:
          VercelAdapter  · RenderAdapter · RailwayAdapter · ShellAdapter · …
        verify(): re-query Datadog / a health endpoint
```

**Switching to real infra = set `EXECUTION_MODE=real` + provider creds. No engine, brain,
UI, or contract changes.** Provider specifics live *only* inside an adapter. Never let a
provider SDK leak into the engine, routes, or brain.

### Simulate-mode behavior per action (§4b)

| action | SimulatedExecutor does |
|--------|------------------------|
| `rollback_deployment` | swap `current`↔`previous` in §2b; set service `status: rolled_back` |
| `restart_service` | brief `degraded` → `recovered` transition; log it |
| `isolate_service` | `status: isolated` |
| `scale_up` | log added capacity; status unchanged |
| `disable_feature` | log feature off; status unchanged |
| `isolate_container` / `quarantine_host` | `status: isolated` (v1 security path) |
| `revoke_keys` | log key revoked; status unchanged |

The **real** behavior for each (Vercel promote, container restart, LB deregister, etc.) is
documented as a stub in the future RealExecutor section and intentionally **not built now**.

## Autonomy policy — "auto-fix safe, escalate rest"  (user-confirmed)

For each incident, the engine walks `plan.steps` in order:

```
for step in plan.steps:
    if step.autonomy == "human":          → STOP, escalate (a human must approve this step)
    if step.autonomy == "auto":
        run(step.action, step.target)      → record attempt (actor="auto")
        if verify(incident):               → RESOLVED. status=resolved. notify Slack "auto-resolved". DONE.
        else:                              → continue to next step
end of steps without resolution            → escalate
```

So CallSign **only ever auto-runs steps explicitly tagged `auto`** (safe + reversible), and
**always escalates** the moment it hits a `human` step, exhausts the auto steps, or a
severity gate trips (see below). This matches the user's "if none of that works, flag an
engineer."

### Severity gate
A config `AUTO_REMEDIATE_MAX_SEVERITY` (default `SEV-2`) caps autonomy: incidents at or above
the cap (e.g. `SEV-1`) skip auto-remediation and escalate immediately, even if steps are
tagged `auto`. Conservative by default; tune per demo.

## Verification

After an `auto` step the engine asks the Executor "did the alert clear?".
- **Simulate mode:** deterministic and **scriptable for demos** via a field on the alert/
  fixture (e.g. `sim_resolves_after: "restart_service"` → verify returns false until that
  step runs). This lets a demo show *auto-fix succeeds* OR *auto-fix fails → escalate* on
  purpose. Default fixture: rollback "fails" so the call-the-engineer flow is shown.
- **Real mode:** re-query the Datadog monitor status or hit a service health endpoint;
  treat "recovered for N seconds" as cleared.

## Incident status transitions driven here

`remediating` (running an auto step) → `verifying` (checking) → `resolved`
(cleared) **or** `escalated` (handed to [escalation.md](escalation.md)). Every transition
emits a `log` (source `REMEDIATION`) and an updated `incident` SSE event (§7).

## What lives where (for the build)

- `app/remediation/engine.py` — the policy loop above.
- `app/remediation/executor.py` — the `RemediationExecutor` interface + `SimulatedExecutor`.
- `app/remediation/adapters/` — future `RealExecutor` + provider adapters (empty stubs now).
- Engine is called from `trigger.py` (auto phase) and `execute.py` (human-approved step).
  Keep it HTTP-free and unit-testable, like the brain.

## Out of scope now
- Any `RealExecutor` / provider adapter implementation (documented, not built).
- Multi-incident concurrency — one incident at a time is fine for the demo.
