# examples/

Runnable examples that show how to wire a real AI agent to the CallSign approval gate.

## geo_agent.py

A faithful mimic of the **GEO agent** from the don-drapor project.  That agent uses
Lyzr Studio to regenerate the site's `LLMs.txt` file — an action that spends real
credits and overwrites a public file.  Before generating, it asks CallSign for human
approval.

### What it does

1. Calls `callsign.approve(...)` — blocks until a human clicks **Approve** or **Deny**
   in the CallSign dashboard or Slack.
2. On **Approve**: writes a sample `LLMs.txt` to `examples/output/LLMs.txt` and prints
   a confirmation.  (In the real don-drapor agent, this is where Lyzr Studio runs and
   the actual file is published.)
3. On **Deny / timeout**: prints a skip message and writes nothing.

### Prerequisites

```bash
# 1. Start the CallSign backend (terminal 1)
cd backend
APPROVAL_API_KEY=demo-key-123 uvicorn app.main:app --reload

# 2. (Optional) start the dashboard to approve via UI (terminal 2)
cd frontend && npm run dev     # http://localhost:3000
```

### Run

```bash
export APPROVAL_API_KEY=demo-key-123
export CALLSIGN_BASE_URL=http://localhost:8000   # default — omit if this is your URL

python examples/geo_agent.py
```

The script blocks with "Requesting approval from CallSign …".

### Approve the request

**Via dashboard:** open http://localhost:3000 → find the pending "Generate LLMs.txt
(GEO agent)" request → click **Approve**.

**Via curl:**
```bash
# 1. Find the request_id
curl -s http://localhost:8000/approvals -H "X-API-Key: $APPROVAL_API_KEY" | python3 -m json.tool

# 2. Approve
curl -s -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $APPROVAL_API_KEY" \
  -d '{"request_id":"<id>","decision":"approve","actor":"you"}'
```

### Expected output (approved)

```
Requesting approval from CallSign …
  backend: http://localhost:8000

approved — generated LLMs.txt (would have spent credits)
  written to: /path/to/CallSign/examples/output/LLMs.txt
```

### Expected output (denied)

```
Requesting approval from CallSign …
  backend: http://localhost:8000

denied — skipped generation, saved the credits
```

### Notes

- The script exits non-zero if the backend is unreachable or the API key is wrong.
- `APPROVAL_API_KEY` is required; the script prints a clear error and exits if unset.
- For the real integration into don-drapor, see `examples/WIRING.md`.
