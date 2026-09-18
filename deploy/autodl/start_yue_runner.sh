#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/root/autodl-tmp/agent-sandbox
RUNNER_PYTHON=/root/autodl-tmp/envs/yue-runner/bin/python
CONFIG_FILE="$APP_ROOT/deploy/autodl/sandbox.yue.yaml"
LOG_DIR=/root/LaunchTool311/log
LOG_FILE="$LOG_DIR/yue-runner.log"
PID_FILE=/root/LaunchTool311/yue-runner.pid

for path in "$APP_ROOT" "$RUNNER_PYTHON" "$CONFIG_FILE"; do
  if [[ ! -e "$path" ]]; then
    printf 'Missing required path: %s\n' "$path" >&2
    exit 1
  fi
done

if ss -ltn | grep -q ':10000\b'; then
  printf 'Port 10000 is already listening; leaving the existing process unchanged.\n'
  exit 0
fi

install -d -m 700 "$LOG_DIR"
cd "$APP_ROOT"
nohup env PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 \
  "$RUNNER_PYTHON" -m sandbox.start.main \
  --mode web --speakers-config-file "$CONFIG_FILE" \
  >>"$LOG_FILE" 2>&1 &
pid=$!
printf '%s\n' "$pid" >"$PID_FILE"

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:10000/openapi.json >/dev/null 2>&1; then
    printf 'YuE Runner is ready (PID %s).\n' "$pid"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    printf 'YuE Runner exited during startup. See %s\n' "$LOG_FILE" >&2
    exit 1
  fi
  sleep 1
done

printf 'YuE Runner did not become ready within 60 seconds. See %s\n' "$LOG_FILE" >&2
exit 1
