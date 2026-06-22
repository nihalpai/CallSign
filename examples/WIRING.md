# Wiring the real don-drapor GEO agent to CallSign

This doc gives the ~10-line snippet you paste into your actual GEO agent in the
don-drapor project to gate the "Generate LLMs.txt" action behind a human approval.

## 1. Install the SDK

```bash
# From the don-drapor project root, point pip at the local CallSign SDK:
pip install -e /path/to/CallSign/sdk

# Or, once the SDK is published to PyPI:
pip install callsign
```

## 2. Set environment variables

```bash
export APPROVAL_API_KEY=<your shared key from CallSign backend .env>
export CALLSIGN_BASE_URL=https://<your-callsign-backend-url>   # or http://localhost:8000
```

The approval notification goes to **your Slack** when `SLACK_ENABLED=true` is set on
the CallSign backend and your Slack app is configured.  You can also approve from the
dashboard (http://localhost:3000) without Slack.

> **Slack interactivity note:** the Approve/Deny buttons in the Slack card require the
> backend to be publicly reachable so Slack can POST back.  Run `ngrok http 8000` and
> set `CALLSIGN_BASE_URL` to the ngrok URL on the backend.  The dashboard Approve button
> works without ngrok.

## 3. The snippet — paste into your GEO agent

Find the place in don-drapor's GEO agent where it calls Lyzr Studio to generate
`LLMs.txt`, then wrap it like this:

```python
import os
from callsign import approve, CallSignError

def run_geo_agent():
    try:
        decision = approve(
            "Generate LLMs.txt (GEO agent)",
            api_key=os.environ["APPROVAL_API_KEY"],
            base_url=os.environ.get("CALLSIGN_BASE_URL", "http://localhost:8000"),
            context="Prompted to regenerate the site's LLMs.txt for don-drapor",
            estimated_tokens=3500,          # your agent's realistic token estimate
            dangers=[
                "Spends ~3,500 Lyzr credits",
                "Overwrites the existing public/llms.txt",
                "Content is published publicly",
            ],
            mode="callback",                # you run the action yourself on approval
            timeout=300,
            requester={"source": "agent", "name": "geo-agent"},
        )
    except CallSignError as exc:
        print(f"CallSign error: {exc}")
        return

    if decision:
        # --- YOUR EXISTING LYZR CALL GOES HERE ---
        generate_llms_txt_with_lyzr()
    else:
        print("Denied — skipped LLMs.txt generation, saved the credits.")
```

That's it.  The call blocks until a human decides (up to `timeout` seconds).
`decision` is truthy on approve, falsy on deny or timeout.

## 4. What the human sees

When the agent calls `approve(...)`, a request card appears in:

- **CallSign dashboard** (http://localhost:3000 → Approvals queue):
  action, context, dangers list, estimated tokens, and who requested it.
- **Slack** (if `SLACK_ENABLED=true` on the backend):
  a card in the configured channel or DM with Approve/Deny buttons.

One click (or curl) resolves the request, the `approve()` call returns, and the
agent proceeds or skips accordingly.
