# Runbook: Bad Deploy Rollback

**Severity:** SEV-1 / SEV-2
**Applies to:** Any service showing elevated error rates or latency correlated with a recent deployment.

## Detection signature

- 5xx error rate or latency spike begins within minutes of a deploy event.
- Datadog alert tagged with `deploy:<deploy_id>` and `route:<affected_route>`.
- `alert_type: reliability`, priority P1 or P2.

## Blast radius

The affected service and any downstream services listed in `depended_on_by` are at risk.
For `payment-gw`, a checkout failure directly impacts revenue and the `web-01` frontend.

## Required mitigation (in order)

1. **Roll back to the previous good deploy.** Recommended action: `rollback_deployment` on
   the affected service. Promotes the last known-good artifact (`dpl_8e1` for `payment-gw`).
   This is safe and reversible; the bad deploy artifact is retained for post-mortem.

2. **Restart the service workers.** Action: `restart_service` on the same target. Ensures
   workers pick up the rolled-back code cleanly without stale in-flight state.

3. **Isolate from the load balancer.** Action: `isolate_service`. Use only if rollback and
   restart both fail to clear the error rate. Requires human approval (`autonomy: human`).

## Decision the on-call must approve

Steps 1 and 2 are auto-remediable (safe, reversible). Step 3 requires explicit approval
because it removes the service from rotation and is customer-impacting until traffic is
re-routed.

## Notes

Rollback is non-destructive. The bad deploy artifact is not deleted; it is simply
de-promoted. If rollback itself introduces regressions, re-promote the previous artifact
and open a separate incident.
