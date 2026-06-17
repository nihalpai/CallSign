"""
Provider adapter stubs — remediation.md §RealExecutor.

Each adapter wraps a single infrastructure provider and is used exclusively
by RealExecutor. No adapter or provider SDK is ever imported by the engine,
routes, or brain — they stay behind this package boundary.

Planned adapters (not implemented):
    VercelAdapter   — promote a previous deployment via Vercel REST API
    RenderAdapter   — deploy a previous service revision via Render API
    RailwayAdapter  — revert a service via Railway GraphQL API
    ShellAdapter    — SSH + runbook commands for bare-metal / VM targets

To add a real adapter:
    1. Create app/remediation/adapters/<provider>.py
    2. Implement run(action, target) -> dict and verify(incident, alert) -> bool
    3. Wire it into RealExecutor.__init__ via a PROVIDER env var or config key
    4. Never import provider SDKs above this package
"""
