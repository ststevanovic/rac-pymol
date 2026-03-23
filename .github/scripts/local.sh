#!/usr/bin/env bash
# .github/scripts/local.sh — local runner for RAC-PyMOL
#
# Usage:
#   bash .github/scripts/local.sh [scene_id]   # default: 9ax6
#   bash .github/scripts/local.sh 9ax6 --dry
#
# Starts an API + static file server on :8091, opens the browser to
# http://127.0.0.1:8091/.github/index.html, then waits.
# The Render button in the UI POSTs to /api/run — no terminal interaction needed.
#
# API:
#   POST /api/run    {scene_id}  → spawns batch.py, returns {run_tag}
#   GET  /api/status             → {state, run_tag, slides}
#   GET  /api/log?since=N        → {lines: [...], total: N}  (batch stdout/stderr)
#   GET  /*                      → static files from repo root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

SCENE_ID="${1:-9ax6}"
DRY="${2:-}"

# ── resolve Python ────────────────────────────────────────────────────────────
if [[ -x ".venv-batch/bin/python" ]]; then
  PYTHON=".venv-batch/bin/python"
elif command -v conda &>/dev/null && conda env list | grep -q "pymol-ci"; then
  PYTHON="conda run -n pymol-ci python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "[local] ERROR: no Python found."
  exit 1
fi

echo "[local] Python  : ${PYTHON}"
echo "[local] Scene ID: ${SCENE_ID}"
echo "[local] UI      : http://127.0.0.1:8091/.github/index.html"

[[ "$DRY" == "--dry" ]] && { echo "[local] --dry: exiting."; exit 0; }

# ── evict any process already bound to :8091 ─────────────────────────────────
if command -v fuser &>/dev/null; then
  fuser -k 8091/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
  lsof -ti tcp:8091 | xargs -r kill -9 2>/dev/null || true
fi
sleep 0.2

# ── start API + static server on :8091 ───────────────────────────────────────
$PYTHON - "$REPO_ROOT" "$PYTHON" <<'PYEOF' &
import http.server, socketserver, json, subprocess, threading, os, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT    = sys.argv[1]
PYTHON  = sys.argv[2]
RANDOM  = Path(ROOT) / ".rendering" / "random"

_state  = {"state": "idle", "run_tag": None, "slides": None}
_log    = []
_lock   = threading.Lock()

def _append_log(line: str):
    with _lock:
        _log.append(line.rstrip("\n"))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *_): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors(); self.end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/run":
            self._json(404, {"error": "not found"}); return
        if _state["state"] == "running":
            self._json(409, {"error": "already running"}); return
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b'{}')
        scene  = body.get("scene_id", "9ax6")

        import datetime
        run_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        (RANDOM / run_tag).mkdir(parents=True, exist_ok=True)
        with _lock:
            _log.clear()
        _state.update(state="running", run_tag=run_tag, slides=None)

        def _run():
            env = os.environ.copy()
            env["BATCH_RUN_TAG"]    = run_tag
            env["RAC_LOCAL_UI"]     = "0"
            env["BATCH_N_SUBJECTS"] = env.get("BATCH_N_SUBJECTS", "3")
            cmd = PYTHON.split() + ["pymol-workshop/batch.py", scene]
            proc = subprocess.Popen(
                cmd, env=env, cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            for line in proc.stdout:
                _append_log(line)
            proc.wait()
            slides = f"http://127.0.0.1:8091/.rendering/random/{run_tag}/slides.html"
            _state.update(state="done", slides=slides)
            _append_log(f"[server] done — {slides}")

        threading.Thread(target=_run, daemon=True).start()
        self._json(202, {"run_tag": run_tag})

    def do_GET(self):
        if self.path == "/api/status":
            self._json(200, dict(_state))
        elif self.path.startswith("/api/log"):
            qs    = parse_qs(urlparse(self.path).query)
            since = int(qs.get("since", ["0"])[0])
            with _lock:
                chunk = list(_log[since:])
                total = len(_log)
            self._json(200, {"lines": chunk, "total": total})
        else:
            super().do_GET()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", 8091), Handler) as s:
    s.serve_forever()
PYEOF
SERVER_PID=$!
trap 'echo; echo "[local] stopping server (pid $SERVER_PID)…"; kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null; exit 0' EXIT INT TERM

sleep 0.5
xdg-open "http://127.0.0.1:8091/.github/index.html" 2>/dev/null || true
echo "[local] server up  — http://127.0.0.1:8091/.github/index.html"
echo "[local] toggle --local in the UI and click Render."
echo "[local] Ctrl+C to stop."
wait $SERVER_PID
