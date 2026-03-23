#!/usr/bin/env bash
# .github/scripts/remote.sh — GH Actions wrapper (mirrors local.sh contract)
#
# Responsibilities:
#   1. Pre-mint BATCH_RUN_TAG (YYYYMMDD_HHMMSS) — same format as local.sh —
#      so batch.py honours it and the run dir is predictable.
#   2. Run batch.py with all required env vars.
#   3. After batch completes, copy the run dir into the gh-pages orphan branch
#      checkout at .ghpagess/<run_tag>/ and update .ghpages/index.json (version
#      manifest) so the landing page can list all past runs.
#
# Called from ui.yml instead of invoking batch.py directly.
#
# Usage (in workflow YAML):
#   bash .github/scripts/remote.sh "${{ github.event.inputs.scene_id }}"
#
# ── TODO (gh-pages tag browser) ───────────────────────────────────────────────
# TODO: index.html --ghaction mode: add a "Browse" button next to [ tag: ] that
#       talks to the gh-pages branch via the GitHub Contents API to read
#       index.json, then shows a dropdown of all past run tags.
#       Selecting a tag + clicking "Load" sets [ tag: <datetag> ] and wires the
#       independent "Open HTML" button to:
#         https://<owner>.github.io/rac-pymol/<tag>/slides.html
#       No new render triggered — browse-only, independent of the Render flow.
#       Element needed: a small popover panel (reuse confirm-overlay style) with
#       a <select> populated from index.json["runs"] (newest first) + Load btn.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCENE_ID="${1:-9ax6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

# ── pre-mint run tag ──────────────────────────────────────────────────────────
export BATCH_RUN_TAG="$(date +%Y%m%d_%H%M%S)"
RUN_DIR=".rendering/random/${BATCH_RUN_TAG}"
mkdir -p "$RUN_DIR"

echo "[remote] run_tag : ${BATCH_RUN_TAG}"
echo "[remote] scene   : ${SCENE_ID}"
echo "[remote] run_dir : ${RUN_DIR}"

# ── run batch.py ──────────────────────────────────────────────────────────────
export BATCH_N_SUBJECTS="${BATCH_N_SUBJECTS:-2}"
# RAC_LOCAL_UI not set — no status HTTP server needed on CI

PYTHON="${REPO_ROOT}/.venv-batch/bin/python"
"$PYTHON" pymol-workshop/batch.py "$SCENE_ID"

# write tag for workflow GITHUB_OUTPUT
echo "$BATCH_RUN_TAG" > "${REPO_ROOT}/.rendering/.last_tag"

SLIDES="${RUN_DIR}/slides.html"
if [[ ! -f "$SLIDES" ]]; then
  echo "[remote] ERROR: slides.html not produced at ${SLIDES}"
  exit 1
fi
echo "[remote] slides  : ${SLIDES}"

# ── push run dir to gh-pages orphan branch ────────────────────────────────────
# Expects the gh-pages branch to already exist (created by the deploy workflow).
# We do a sparse checkout into .ghpages/ and copy only what we need.

GHP_DIR="${REPO_ROOT}/.ghpages"
GH_PAGES_BRANCH="gh-pages"

echo "[remote] cloning gh-pages branch → ${GHP_DIR}"
git clone \
  --branch "$GH_PAGES_BRANCH" \
  --single-branch \
  --depth 1 \
  "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" \
  "$GHP_DIR"

# Copy the run dir into gh-pages/<run_tag>/
DEST="${GHP_DIR}/${BATCH_RUN_TAG}"
mkdir -p "$DEST"
cp -r "${RUN_DIR}/." "$DEST/"
echo "[remote] copied ${RUN_DIR} → ${DEST}"

# Update (or create) index.json — version manifest listing all run tags
INDEX="${GHP_DIR}/index.json"
if [[ -f "$INDEX" ]]; then
  # Append this run_tag to the existing list (keep unique, newest last)
  python3 - <<PYEOF
import json, pathlib
p = pathlib.Path("${INDEX}")
data = json.loads(p.read_text())
runs = data.get("runs", [])
tag = "${BATCH_RUN_TAG}"
if tag not in runs:
    runs.append(tag)
data["runs"] = runs
data["latest"] = tag
p.write_text(json.dumps(data, indent=2))
print(f"[remote] index.json updated — {len(runs)} run(s) total")
PYEOF
else
  python3 -c "
import json, pathlib
pathlib.Path('${INDEX}').write_text(json.dumps({
    'runs': ['${BATCH_RUN_TAG}'],
    'latest': '${BATCH_RUN_TAG}'
}, indent=2))
print('[remote] index.json created')
"
fi

# Copy index.html to gh-pages root so https://<owner>.github.io/<repo>/ works
cp "${REPO_ROOT}/.github/index.html" "${GHP_DIR}/index.html"
echo "[remote] index.html → gh-pages root"

# Commit and push
cd "$GHP_DIR"
git config user.name  "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -A
git commit -m "render: ${BATCH_RUN_TAG}  scene=${SCENE_ID}"
git push origin "$GH_PAGES_BRANCH"
echo "[remote] pushed ${BATCH_RUN_TAG} → gh-pages"
