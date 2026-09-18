#!/usr/bin/env bash
set -euo pipefail

PID_FILE=/root/LaunchTool311/yue-runner.pid
if [[ ! -f "$PID_FILE" ]]; then
  printf 'No YuE Runner PID file exists.\n'
  exit 0
fi

pid=$(cat "$PID_FILE")
[[ "$pid" =~ ^[0-9]+$ ]] && [[ "$pid" -gt 1 ]]
if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  printf 'Recorded YuE Runner process is no longer running.\n'
  exit 0
fi

command_line=$(tr '\0' ' ' <"/proc/$pid/cmdline")
if [[ "$command_line" != *"sandbox.start.main"* ]] || [[ "$command_line" != *"sandbox.yue.yaml"* ]]; then
  printf 'PID %s does not belong to YuE Runner; refusing to stop it.\n' "$pid" >&2
  exit 1
fi

kill -TERM "$pid"
for _ in $(seq 1 30); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then
  printf 'YuE Runner did not stop within 30 seconds.\n' >&2
  exit 1
fi
rm -f "$PID_FILE"
printf 'YuE Runner stopped.\n'
