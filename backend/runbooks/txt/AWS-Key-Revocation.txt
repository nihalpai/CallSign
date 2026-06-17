# Runbook: Leaked AWS Access Key Revocation

**Severity:** SEV-2
**Applies to:** Any host or service with attached IAM credentials.
**Trigger:** Static analysis or secret-scanner flags an exposed `AKIA…` key, or anomalous
API calls from an unexpected region.

## Detection signature

- GuardDuty / Datadog finding tagged `service:*`, body mentions credential exposure.
- API activity from an IP or region outside the known deployment footprint.

## Blast radius

A leaked key inherits the IAM role's permissions. Scope the radius to every resource the
role can touch — storage buckets, databases, and any downstream service in
`depended_on_by`.

## Required mitigation (in order)

1. **Revoke the exposed key immediately.** Recommended action: `revoke_keys` on the
   owning host. Deactivate, do not delete, so the audit trail survives.
2. Issue a replacement key and redeploy the affected service.
3. Audit CloudTrail for actions taken with the leaked key during the exposure window.

## Decision the on-call must approve

> Revoke the exposed access key now. This is a yes/no approval. Revocation may briefly
> interrupt the owning service until a replacement key is deployed.

## Notes

Revocation is reversible in the sense that a new key restores function; the leaked key
is never reactivated.
