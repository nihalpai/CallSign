# Runbook: Error Spike Mitigation

**Severity:** SEV-2 / SEV-3
**Applies to:** Services showing sustained error rate increases without a correlated deploy event.

## Detection signature

- Error rate (5xx or application-level) climbs above threshold over 5–15 minutes.
- No recent deployment detected (distinguishes from a bad-deploy scenario).
- Datadog alert `alert_type: reliability`, tags include `service:` and `route:`.

## Blast radius

Downstream consumers in `depended_on_by` will see degraded responses. Assess which
dependent services are user-facing before choosing the mitigation path.

## Required mitigation (in order)

1. **Restart the service.** Action: `restart_service` on the affected service. Clears
   transient worker errors, connection pool exhaustion, and memory pressure.
   Safe and reversible. Run first.

2. **Disable the implicated feature flag.** Action: `disable_feature` on the affected
   service. If a recently-enabled feature flag correlates with the spike, toggle it off
   to shed load from the degraded code path. Safe and reversible.

3. **Isolate from the load balancer.** Action: `isolate_service`. Last resort — removes
   the service from rotation to stop user-facing errors while the root cause is
   investigated. Requires human approval (`autonomy: human`) due to customer impact.

## Decision the on-call must approve

Steps 1 and 2 are auto-remediable. Step 3 requires explicit approval because it is
disruptive to active user sessions and takes the service entirely offline.

## Notes

If the error rate does not clear after `restart_service` and `disable_feature`, escalate
to the owning team. Capture pod logs and error samples before isolating so forensics are
available in the post-mortem.
