#!/usr/bin/env bash
# trigger_incident.sh — POSTs the canned bad_deploy alert to /webhook/trigger.
#
# Exercises: the incident vertical (Datadog-shaped payload → enrichment → Slack
# card → human approve/deny → gate executor).
#
# Usage:
#   APPROVAL_API_KEY=cs_test_key ./harness/trigger_incident.sh
#
# Env vars (all optional, sensible defaults):
#   CALLSIGN_BASE_URL  — backend URL (default: http://localhost:8000)
#   APPROVAL_API_KEY   — shared API key

set -euo pipefail

BASE_URL="${CALLSIGN_BASE_URL:-http://localhost:8000}"
API_KEY="${APPROVAL_API_KEY:-}"

if [[ -z "$API_KEY" ]]; then
  echo "ERROR: APPROVAL_API_KEY env var is not set." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALERT_FILE="$SCRIPT_DIR/../backend/data/mock_alerts/bad_deploy.json"

if [[ ! -f "$ALERT_FILE" ]]; then
  echo "ERROR: Alert file not found: $ALERT_FILE" >&2
  exit 1
fi

echo "[trigger_incident] Firing alert to $BASE_URL/webhook/trigger …"
echo "[trigger_incident] Payload: $ALERT_FILE"
echo

curl --fail-with-body \
  --silent \
  --show-error \
  --request POST \
  --url "$BASE_URL/webhook/trigger" \
  --header "Content-Type: application/json" \
  --header "X-API-Key: $API_KEY" \
  --data "@$ALERT_FILE" \
  | python3 -m json.tool 2>/dev/null || true

echo
echo "[trigger_incident] Done. Watch the dashboard (http://localhost:3000) and Slack for the approval card."
