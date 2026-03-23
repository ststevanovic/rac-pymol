#!/usr/bin/env bash
# curl_wrapper.sh — Resolve scenography DB for ghpage Render workflow.
#
# Usage:
#   bash curl_wrapper.sh [<scenography_input>]
#
# Behaviour:
#   1. If <scenography_input> is empty → use default gh/db/scenography.db
#      (relative to repo root, already present in the checkout)
#   2. If <scenography_input> is a URL (http:// or https://) → curl download
#      to local/<basename>.db
#   3. If <scenography_input> is a local path → treat as-is (validation only)
#
# After this script completes the environment variable SCENOGRAPHY_DB_PATH
# is written to $GITHUB_ENV so subsequent steps can consume it.
# If running locally (no $GITHUB_ENV) the path is just printed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEFAULT_DB="${REPO_ROOT}/db/scenography.db"
LOCAL_DIR="${REPO_ROOT}/local"

INPUT="${1:-}"

log() { echo "[curl-wrapper] $*"; }

write_env() {
    local path="$1"
    if [[ -n "${GITHUB_ENV:-}" ]]; then
        echo "SCENOGRAPHY_DB_PATH=${path}" >> "$GITHUB_ENV"
    fi
    log "SCENOGRAPHY_DB_PATH=${path}"
}

mkdir -p "${LOCAL_DIR}"

if [[ -z "${INPUT}" ]]; then
    # ── default: use committed db/scenography.db from the repo checkout ─────
    log "No scenography input — using repo default: ${DEFAULT_DB}"
    if [[ ! -f "${DEFAULT_DB}" ]]; then
        log "ERROR: db/scenography.db not found in checkout."
        log "       This file must be committed to the repo and contain at least one scene."
        log "       Run enzyme.py locally and commit the resulting db/scenography.db first."
        exit 1
    fi
    write_env "${DEFAULT_DB}"

elif [[ "${INPUT}" =~ ^https?:// ]]; then
    # ── remote URL — curl download ──────────────────────────────────────────
    BASENAME="$(basename "${INPUT}" | sed 's/[?#].*//')"
    # Ensure .db extension
    [[ "${BASENAME}" != *.db ]] && BASENAME="${BASENAME}.db"
    DEST="${LOCAL_DIR}/${BASENAME}"
    log "Downloading scenography from ${INPUT} → ${DEST}"
    curl -fsSL --max-time 60 --retry 3 --retry-delay 5 \
         -o "${DEST}" "${INPUT}"
    log "Download complete: $(du -sh "${DEST}" | cut -f1)"
    write_env "${DEST}"

else
    # ── local path ──────────────────────────────────────────────────────────
    ABS_PATH="${INPUT}"
    if [[ ! "${INPUT}" = /* ]]; then
        ABS_PATH="${REPO_ROOT}/${INPUT}"
    fi
    if [[ ! -f "${ABS_PATH}" ]]; then
        log "ERROR: local scenography path not found: ${ABS_PATH}"
        exit 1
    fi
    log "Using local scenography: ${ABS_PATH}"
    write_env "${ABS_PATH}"
fi
