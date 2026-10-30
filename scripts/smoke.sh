#!/usr/bin/env bash
# Bash Smoke Test Script for ASHA Diary API
# Starts the API, polls /api/health, runs a conversation via /api/turn,
# checks persistence via /api/entries, and terminates the server.

set -euo pipefail

PORT="${PORT:-8000}"
TIMEOUT="${TIMEOUT:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"

echo "=== ASHA Diary API Smoke Test (Bash) ==="
echo "Repository root: $REPO_ROOT"

# Resolve Python executable
if [ -f "$API_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$API_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
else
    PYTHON_EXE="python"
fi
echo "Using Python: $PYTHON_EXE"

TEMP_DB="$(mktemp -t asha_smoke_XXXXXX.db)"
TEMP_DB_URL="sqlite:///$TEMP_DB"
echo "Temporary DB: $TEMP_DB"

SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo "Stopping API server (PID $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        echo "Server stopped."
    fi
    if [ -f "$TEMP_DB" ]; then
        rm -f "$TEMP_DB"
        echo "Cleaned up temporary database."
    fi
}
trap cleanup EXIT INT TERM

echo "Starting API server on port $PORT..."
(
    cd "$API_DIR"
    DATABASE_URL="$TEMP_DB_URL" RATE_LIMIT_PER_MINUTE=1000 "$PYTHON_EXE" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
) &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

HEALTH_URL="http://127.0.0.1:$PORT/api/health"
TURN_URL="http://127.0.0.1:$PORT/api/turn"
ENTRIES_URL="http://127.0.0.1:$PORT/api/entries"

echo "Waiting for server to become healthy at $HEALTH_URL..."
READY=0
for _ in $(seq 1 "$TIMEOUT"); do
    if curl -s -f "$HEALTH_URL" | grep -q '"ok"'; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "ERROR: Server failed to start within $TIMEOUT seconds."
    exit 1
fi
echo "[OK] Server is healthy."

SESSION_ID="smoke_$RANDOM"

echo ""
echo "--- Turn 1: Report initial entry ---"
RESP1="$(curl -s -X POST "$TURN_URL" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"text\": \"aaj Rina ANC visit korlam\"}")"
echo "Response: $RESP1"
if ! echo "$RESP1" | grep -q '"ask_field"'; then
    echo "ERROR: Expected ui_hint 'ask_field' on Turn 1"
    exit 1
fi
echo "[OK] Turn 1 prompted for missing count."

echo ""
echo "--- Turn 2: Provide count ---"
RESP2="$(curl -s -X POST "$TURN_URL" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"text\": \"2 jon\"}")"
echo "Response: $RESP2"
if ! echo "$RESP2" | grep -q '"confirm"'; then
    echo "ERROR: Expected ui_hint 'confirm' on Turn 2"
    exit 1
fi
echo "[OK] Turn 2 prompted for confirmation."

echo ""
echo "--- Turn 3: Confirm entry ---"
RESP3="$(curl -s -X POST "$TURN_URL" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION_ID\", \"text\": \"hyan\"}")"
echo "Response: $RESP3"
if ! echo "$RESP3" | grep -q '"saved"'; then
    echo "ERROR: Expected ui_hint 'saved' on Turn 3"
    exit 1
fi
echo "[OK] Turn 3 saved the entry."

echo ""
echo "--- Verifying persistence via GET /api/entries ---"
ENTRIES_RESP="$(curl -s "$ENTRIES_URL")"
echo "Entries response: $ENTRIES_RESP"
if ! echo "$ENTRIES_RESP" | grep -q '"antenatal_visit"' || ! echo "$ENTRIES_RESP" | grep -q '"confirmed"'; then
    echo "ERROR: Saved entry not found in entries list"
    exit 1
fi
echo "[OK] Entry confirmed and verified in database!"

echo ""
echo "=========================================="
echo "=== SMOKE TEST PASSED SUCCESSFULLY ==="
echo "=========================================="

