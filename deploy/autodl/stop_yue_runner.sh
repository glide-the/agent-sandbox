#!/usr/bin/env bash
# [Input] YuE Runner PID file plus the owned main/worker process group.
# [Output] Stops only the validated YuE Runner main process and all of its owned descendants.
# [Pos] AutoDL Runner shutdown entry; unrelated Python, Dream, Admin, and model processes are untouched.
# [Sync] 2026-09-19: stop the dedicated process group and support the previous direct-child topology.
set -euo pipefail

PID_FILE=/root/LaunchTool311/yue-runner.pid
CONFIG_FILE=/root/autodl-tmp/agent-sandbox/deploy/autodl/sandbox.yue.yaml
for command_name in pgrep ps; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$command_name" >&2
    exit 1
  }
done

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

worker_pids=()
while IFS= read -r child_pid; do
  [[ "$child_pid" =~ ^[0-9]+$ ]] || continue
  [[ -r "/proc/$child_pid/cmdline" ]] || continue
  child_command=$(tr '\0' ' ' <"/proc/$child_pid/cmdline")
  if [[ "$child_command" == *"sandbox.start.start"* ]] \
    && [[ "$child_command" == *"--mode web_runner"* ]] \
    && [[ "$child_command" == *"--speakers-config-file $CONFIG_FILE"* ]]; then
    worker_pids+=("$child_pid")
  fi
done < <(pgrep -P "$pid" 2>/dev/null || true)

pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
if [[ "$pgid" =~ ^[0-9]+$ ]] && [[ "$pgid" == "$pid" ]]; then
  kill -TERM -- "-$pgid"
else
  for worker_pid in "${worker_pids[@]}"; do
    kill -TERM "$worker_pid" 2>/dev/null || true
  done
  kill -TERM "$pid"
fi

for _ in $(seq 1 30); do
  running=0
  for target_pid in "$pid" "${worker_pids[@]}"; do
    kill -0 "$target_pid" 2>/dev/null && running=1
  done
  [[ "$running" == 0 ]] && break
  sleep 1
done

for target_pid in "$pid" "${worker_pids[@]}"; do
  if kill -0 "$target_pid" 2>/dev/null; then
    printf 'YuE Runner process %s did not stop within 30 seconds.\n' "$target_pid" >&2
    exit 1
  fi
done
rm -f "$PID_FILE"
printf 'YuE Runner stopped.\n'
