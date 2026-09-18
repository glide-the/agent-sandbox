#!/usr/bin/env bash
# [Input] Existing AutoDL Admin, Dream, and YuE Runner deployments.
# [Output] Idempotently starts Admin, Dream, and YuE Runner, then verifies all local endpoints.
# [Pos] AutoDL one-command launcher; performs no build, migration, model load, restore, or GPU probe.
# [Sync] 2026-09-19: keep the launcher lock in this process instead of leaking it into long-lived services.
set -euo pipefail

INK_START_SCRIPT="${INK_START_SCRIPT:-/root/ink-autodl/start-ink-memory.sh}"
RUNNER_START_SCRIPT="${RUNNER_START_SCRIPT:-/root/autodl-tmp/agent-sandbox/deploy/autodl/start_yue_runner.sh}"
LOG_DIR="${START_ALL_LOG_DIR:-/root/LaunchTool311/log}"
LOG_FILE="${START_ALL_LOG_FILE:-${LOG_DIR}/ink-memory-yue-start.log}"
LOCK_FILE="${START_ALL_LOCK_FILE:-/root/LaunchTool311/ink-memory-yue-start.lock}"

log() { printf '[ink-memory-yue-start] %s\n' "$*"; }
fail() { printf '[ink-memory-yue-start:error] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || fail "Run this script as root."
for command_name in curl flock ss tee; do
  command -v "${command_name}" >/dev/null 2>&1 || fail "Missing command: ${command_name}"
done
[[ -x "${INK_START_SCRIPT}" ]] || fail "Ink & Memory launcher is missing: ${INK_START_SCRIPT}"
[[ -x "${RUNNER_START_SCRIPT}" ]] || fail "YuE Runner launcher is missing: ${RUNNER_START_SCRIPT}"

install -d -m 0700 "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1
exec 9>"${LOCK_FILE}"
flock -n 9 || fail "Another combined startup is already running."

log "Starting existing Admin and Dream releases."
"${INK_START_SCRIPT}" 9>&-

log "Starting the YuE Runner without loading model weights."
"${RUNNER_START_SCRIPT}" 9>&-

curl -fsS --max-time 5 http://127.0.0.1:6008/admin/login >/dev/null \
  || fail "Admin health check failed on port 6008."
curl -fsS --max-time 5 http://127.0.0.1:8765/api/health >/dev/null \
  || fail "Dream backend health check failed on port 8765."
curl -fsS --max-time 5 http://127.0.0.1:6006/api/health >/dev/null \
  || fail "Dream frontend health check failed on port 6006."
curl -fsS --max-time 5 http://127.0.0.1:10000/openapi.json >/dev/null \
  || fail "YuE Runner health check failed on port 10000."

for port_value in 6006 6008 8765 10000; do
  ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${port_value}$" \
    || fail "Expected listener is missing on port ${port_value}."
done

log "Admin, Dream, and YuE Runner are ready."
