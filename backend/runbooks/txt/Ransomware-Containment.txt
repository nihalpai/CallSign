# Runbook: Ransomware / Host Compromise Containment

**Severity:** SEV-1
**Applies to:** Any host showing mass file encryption or known ransomware IOCs.
**Trigger:** EDR detects rapid file modification, ransom note artifacts, or a matched
ransomware hash.

## Detection signature

- Sudden spike in file-write/rename rate across a volume.
- Known ransomware process hash or C2 beacon, tag `alert_type: security`.

## Blast radius

Ransomware spreads over trusted internal paths. Quarantine the host before it reaches
shared storage or any service in `depended_on_by`. The **Primary Database** is the
highest-value target — protect it first.

## Required mitigation (in order)

1. **Quarantine the host immediately.** Recommended action: `quarantine_host` on the
   affected server. This cuts it off from the network while leaving it powered for
   forensics.
2. Identify patient zero and the encryption start time.
3. Restore affected data from the last known-good backup.
4. Rebuild the host from a clean image before returning it to service.

## Decision the on-call must approve

> Quarantine the affected host now to stop lateral spread. This is a yes/no approval.
> Default posture is **quarantine** for any confirmed ransomware detection.

## Notes

Quarantine isolates but does not wipe the host; forensic state is preserved.
