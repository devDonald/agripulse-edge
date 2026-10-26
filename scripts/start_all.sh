#!/usr/bin/env bash
# AgriPulse Edge — 1-click launcher for hackathon demo + judging.
#   bash scripts/start_all.sh            # launch all 3 services (foreground, Ctrl+C stops all)
#   bash scripts/start_all.sh --test     # boot all 3, health-check, then shut down (CI/verify)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
DASH_PORT="${DASH_PORT:-8501}"
PWA_PORT="${PWA_PORT:-8502}"
export MOCK_MODE="${MOCK_MODE:-true}"

PIDS=()
TEST_MODE=0
[[ "${1:-}" == "--test" ]] && TEST_MODE=1

cleanup() {
  echo ""
  echo "🛑 Stopping AgriPulse Edge services..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "✅ All services stopped."
}
trap cleanup SIGINT SIGTERM EXIT

wait_for() { # wait_for <url> <label> <tries>
  local url="$1" label="$2" tries="${3:-40}" i=0
  while [ $i -lt $tries ]; do
    if curl -sf -m 3 "$url" >/dev/null 2>&1; then
      echo "✅ $label is up ($url)"
      return 0
    fi
    sleep 1; i=$((i + 1))
  done
  echo "❌ $label failed to start ($url)"
  return 1
}

echo "🌿 AgriPulse Edge — starting all services (MOCK_MODE=$MOCK_MODE)"
echo "──────────────────────────────────────────────"

echo "▶ 1/3 FastAPI backend → http://localhost:$BACKEND_PORT (docs: /docs)"
MOCK_MODE="$MOCK_MODE" nohup python3 -m uvicorn backend.main:app --port "$BACKEND_PORT" > /tmp/agripulse_backend.log 2>&1 &
PIDS+=($!)

echo "▶ 2/3 Cooperative Web Dashboard → http://localhost:$DASH_PORT"
nohup python3 -m streamlit run frontend/app.py --server.headless true --server.port "$DASH_PORT" > /tmp/agripulse_dash.log 2>&1 &
PIDS+=($!)

echo "▶ 3/3 Farmer Mobile PWA → http://localhost:$PWA_PORT"
BACKEND_URL="http://localhost:$BACKEND_PORT" nohup python3 -m streamlit run frontend/mobile_farmer.py --server.headless true --server.port "$PWA_PORT" > /tmp/agripulse_pwa.log 2>&1 &
PIDS+=($!)

FAIL=0
wait_for "http://localhost:$BACKEND_PORT/health" "Backend API" 45 || FAIL=1
wait_for "http://localhost:$DASH_PORT/" "Coop Dashboard" 60 || FAIL=1
wait_for "http://localhost:$PWA_PORT/" "Farmer PWA" 60 || FAIL=1

echo "──────────────────────────────────────────────"
if [ $FAIL -ne 0 ]; then
  echo "❌ One or more services failed. Logs:"
  echo "   tail /tmp/agripulse_backend.log /tmp/agripulse_dash.log /tmp/agripulse_pwa.log"
  exit 1
fi

echo "🎬 DEMO VIDEO — open these 3 tabs:"
echo "   1. Backend API:      http://localhost:$BACKEND_PORT/docs"
echo "   2. Coop Dashboard:   http://localhost:$DASH_PORT  (Offline Edge → Cassava preset → Diagnose → SAM 2 slider → Voice → WhatsApp → Edge)"
echo "   3. Farmer PWA:       http://localhost:$PWA_PORT  (phone on same Wi-Fi via laptop IP; 2 taps: CHECK MY LEAF → play voice)"
echo ""
echo "📱 Expo app: cd mobile && npx expo start  (set BACKEND_URL in mobile/src/api.js to laptop LAN IP)"
echo "──────────────────────────────────────────────"

if [ $TEST_MODE -eq 1 ]; then
  echo "🧪 --test mode: all 3 services boot cleanly. Shutting down…"
  exit 0
fi

echo "Press Ctrl+C to stop all services."
wait
