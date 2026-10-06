#!/bin/bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_NAME="$(basename "${PLUGIN_DIR}")"
SETTINGS_FILE="/home/fpp/media/config/plugin.${PLUGIN_NAME}.json"
PYTHON_BIN="$(command -v python3 || true)"

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found on PATH"
  exit 1
fi

FPP_URL="http://127.0.0.1/api/configfile/schedule.json"
DAYS="3"
AUTH_MODE="auto"
DRY_RUN="${DRY_RUN:-0}"

if [[ -f "${SETTINGS_FILE}" ]]; then
  if command -v jq >/dev/null 2>&1; then
    FPP_URL="$(jq -r '.fpp_url // "http://127.0.0.1/api/configfile/schedule.json"' "${SETTINGS_FILE}")"
    DAYS="$(jq -r '.days // 3' "${SETTINGS_FILE}")"
    AUTH_MODE="$(jq -r '.fpp_auth // "auto"' "${SETTINGS_FILE}")"
    export FPP_USERNAME
    export FPP_PASSWORD
    export FPP_TOKEN
    FPP_USERNAME="$(jq -r '.fpp_username // ""' "${SETTINGS_FILE}")"
    FPP_PASSWORD="$(jq -r '.fpp_password // ""' "${SETTINGS_FILE}")"
    FPP_TOKEN="$(jq -r '.fpp_token // ""' "${SETTINGS_FILE}")"
  else
    echo "jq not found, using built-in defaults and environment variables."
  fi
fi

ARGS=( "--fpp-url" "${FPP_URL}" "--days" "${DAYS}" "--fpp-auth" "${AUTH_MODE}" )
if [[ "${DRY_RUN}" == "1" ]]; then
  ARGS+=( "--dry-run" )
fi

exec "${PYTHON_BIN}" "${PLUGIN_DIR}/fpp_game_scheduler_sync.py" "${ARGS[@]}"
