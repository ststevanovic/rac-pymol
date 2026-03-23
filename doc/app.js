// ── app.js · RAC-PyMOL render dispatcher ─────────────────────
// Concerns: config, mode toggle, event log, CBE console,
//           confirm overlay, local mode, GH Actions dispatch, polling.

// ── config ────────────────────────────────────────────────────
const REPO        = "ststevanovic/rac-pymol";
const WORKFLOW_ID = "ui.yml";
const GH_API      = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`;

// ── bootstrap PAT from URL hash (e.g. #pat=ghp_xxx) ─────────
// Read once, store in sessionStorage, then clear the hash so
// the token never appears in browser history or referrer headers.
(function bootstrapPat() {
  const hash = location.hash.slice(1);
  const params = new URLSearchParams(hash);
  const pat = params.get("pat");
  if (pat) {
    sessionStorage.setItem("gh_pat", pat);
    history.replaceState(null, "", location.pathname + location.search);
  }
})();

// Hide --local toggle when not running on localhost
if (location.hostname !== "127.0.0.1" && location.hostname !== "localhost") {
  document.getElementById("local-toggle-label").style.display = "none";
}

let _runId      = null;
let _htmlArtUrl = null;
let _zipArtUrl  = null;
let _pollTimer  = null;

// ── mode toggle (--local / --ghaction) ────────────────────────
let _mode = "ghaction";

document.getElementById("toggle-local").addEventListener("change", function () {
  _mode = this.checked ? "local" : "ghaction";
  document.getElementById("mode-label").textContent = this.checked ? "--local" : "--ghaction";
  const sub = document.getElementById("form-subtitle");
  if (sub) sub.textContent = this.checked
    ? "Run batch.py locally via .github/scripts/local.sh."
    : "Dispatch a headless PyMOL render via GitHub Actions.";
  document.getElementById("local-tag-label").style.display  = this.checked ? "inline-flex" : "none";
  document.getElementById("local-slides-info").style.display = this.checked ? "block" : "none";
  document.getElementById("cta").classList.toggle("local", this.checked);
  if (this.checked) setTagLabel("—");
  log(`Mode → ${_mode}`, "info");
});

function setTagLabel(tag) {
  document.getElementById("local-tag").textContent = tag;
  const el = document.getElementById("local-slides-path");
  if (el) el.textContent = tag === "\u2014" ? "\u2026" : `.rendering/random/${tag}/slides.html`;
  window._localSlidesPath = tag === "\u2014"
    ? null
    : `http://127.0.0.1:8091/.rendering/random/${tag}/slides.html`;
}

// ── event log ─────────────────────────────────────────────────
function log(msg, cls = "") {
  const el   = document.getElementById("event-log");
  const line = document.createElement("div");
  line.className = "ev-line " + cls;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

// ── CBE console output ────────────────────────────────────────
function cbeWrite(text, cls = "") {
  const cbe = document.getElementById("cbe");
  document.getElementById("cbe-placeholder")?.remove();
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text + "\n";
  cbe.appendChild(span);
  cbe.scrollTop = cbe.scrollHeight;
}

function setStatus(txt) {
  const s = document.getElementById("cbe-status");
  if (s) s.textContent = txt;
}

// ── enable output buttons ─────────────────────────────────────
function enableButtons(htmlUrl, zipUrl) {
  _htmlArtUrl = htmlUrl;
  _zipArtUrl  = zipUrl;
  const actions = document.getElementById("cbe-actions");
  actions.style.display = "flex";
  document.getElementById("btn-html-view").disabled = false;
  document.getElementById("btn-download").disabled  = zipUrl ? false : true;
  log("Output ready — HTML View enabled.", "ok");
  cbeWrite("Output ready.", "prompt");
}

// ── confirm overlay ───────────────────────────────────────────
function onRenderClick() {
  const sceno = document.getElementById("f-scenography").value.trim();
  const scene = document.getElementById("f-scene-id").value.trim();
  if (!scene) { log("Scene ID is required.", "err"); return; }
  if (_mode === "local") { executeLocal(); return; }
  const summary = `Scenography : ${sceno || "(repo default)"}\nScene ID    : ${scene}`;
  document.getElementById("confirm-params-text").textContent = summary;
  document.getElementById("confirm-overlay").classList.add("show");
}

function closeConfirm() {
  document.getElementById("confirm-overlay").classList.remove("show");
}

// ── dispatch router ───────────────────────────────────────────
async function executeRender() {
  closeConfirm();
  if (_mode === "local") { executeLocal(); return; }
  executeGHAction();
}

// ── local mode ────────────────────────────────────────────────
// local.sh exposes:
//   POST /api/run    → {run_tag}
//   GET  /api/status → {state, run_tag, slides}
//   GET  /api/log?since=N → {lines:[…], total:N}

const LOCAL_API_RUN    = "http://127.0.0.1:8091/api/run";
const LOCAL_API_STATUS = "http://127.0.0.1:8091/api/status";
const LOCAL_API_LOG    = "http://127.0.0.1:8091/api/log";
let _localPollTimer = null;
let _localLogTimer  = null;

async function executeLocal() {
  const scene = document.getElementById("f-scene-id").value.trim();
  document.getElementById("cbe-actions").style.display = "none";
  document.getElementById("btn-download").style.display = "none";
  document.getElementById("cbe-wait").style.display = "none";
  document.getElementById("cta").disabled = true;
  setStatus("starting…");
  cbeWrite(`$ POST /api/run  scene=${scene}`, "prompt");

  let run_tag;
  try {
    const r = await fetch(LOCAL_API_RUN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: scene }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    ({ run_tag } = await r.json());
  } catch (e) {
    cbeWrite(`✘  Cannot reach local server.`);
    cbeWrite(`   Start it first:  bash .github/scripts/local.sh`, "prompt");
    log(`Local server not reachable: ${e.message}`, "err");
    setStatus("server offline");
    document.getElementById("cta").disabled = false;
    return;
  }

  setTagLabel(run_tag);
  cbeWrite(`  run_tag: ${run_tag}`);
  setStatus("running…");
  log(`Batch started — tag: ${run_tag}`, "info");
  document.getElementById("cbe-wait").style.display = "block";

  // stream batch stdout/stderr
  let _logOffset = 0;
  if (_localLogTimer) clearInterval(_localLogTimer);
  _localLogTimer = setInterval(async () => {
    try {
      const r = await fetch(`${LOCAL_API_LOG}?since=${_logOffset}`, { cache: "no-store" });
      if (!r.ok) return;
      const d = await r.json();
      if (d.lines.length > 0) { d.lines.forEach(l => cbeWrite(l)); _logOffset = d.total; }
    } catch (_) {}
  }, 800);

  // poll /api/status
  if (_localPollTimer) clearInterval(_localPollTimer);
  _localPollTimer = setInterval(async () => {
    try {
      const r = await fetch(LOCAL_API_STATUS, { cache: "no-store" });
      if (!r.ok) return;
      const s = await r.json();
      if (s.state === "done" && s.run_tag === run_tag) {
        clearInterval(_localPollTimer);
        clearInterval(_localLogTimer);
        try {
          const lr = await fetch(`${LOCAL_API_LOG}?since=${_logOffset}`, { cache: "no-store" });
          if (lr.ok) { const d = await lr.json(); d.lines.forEach(l => cbeWrite(l)); }
        } catch (_) {}
        document.getElementById("cbe-wait").style.display = "none";
        setTagLabel(run_tag);
        setStatus("done");
        cbeWrite(`✔  Done — click HTML View to open slides`, "prompt");
        log("Batch complete — HTML View ready.", "ok");
        enableButtons(s.slides, null);
        document.getElementById("cta").disabled = false;
      }
    } catch (_) {}
  }, 2000);
}

// ── GH Actions dispatch ───────────────────────────────────────
// PAT is supplied at runtime via sessionStorage prompt — never hardcoded.
async function executeGHAction() {
  const sceno = document.getElementById("f-scenography").value.trim();
  const scene = document.getElementById("f-scene-id").value.trim();

  document.getElementById("cta").disabled = true;
  setStatus("dispatching…");
  log("Dispatching workflow…", "info");
  cbeWrite(`$ github-actions dispatch  scene=${scene}  sceno=${sceno || "default"}`, "prompt");

  const token = sessionStorage.getItem("gh_pat") ||
    prompt("GitHub PAT (workflow:write scope) — stored in sessionStorage only:");
  if (token) sessionStorage.setItem("gh_pat", token);
  if (!token) {
    log("Cancelled — no PAT provided.", "err");
    document.getElementById("cta").disabled = false;
    return;
  }

  try {
    const resp = await fetch(GH_API, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { scenography: sceno, scene_id: scene },
      }),
    });

    if (resp.status === 204) {
      log("Workflow dispatched successfully.", "ok");
      setStatus("running");
      cbeWrite("Workflow queued. Polling for run ID…");
      const dispatchedAt = new Date().toISOString();
      pollForRunId(token, scene, dispatchedAt);
    } else {
      const body = await resp.text();
      log(`Dispatch failed: HTTP ${resp.status}`, "err");
      cbeWrite(`ERROR: ${resp.status}\n${body}`);
      document.getElementById("cta").disabled = false;
    }
  } catch (e) {
    log(`Network error: ${e.message}`, "err");
    cbeWrite(`Network error: ${e.message}`);
    document.getElementById("cta").disabled = false;
  }
}

// ── poll for run ID + completion ──────────────────────────────
async function pollForRunId(token, scene, dispatchedAt) {
  const runsUrl = `https://api.github.com/repos/${REPO}/actions/runs?per_page=10`;
  let attempts = 0;
  const MAX_ATTEMPTS = 60;           // 60 × 3s = 3 min ceiling

  _pollTimer = setInterval(async () => {
    attempts++;
    if (attempts > MAX_ATTEMPTS) {
      clearInterval(_pollTimer);
      log("Polling timed out after 3 min.", "err");
      cbeWrite("✘  Timed out — check https://github.com/" + REPO + "/actions", "prompt");
      setStatus("timeout");
      document.getElementById("cta").disabled = false;
      return;
    }

    try {
      const r = await fetch(runsUrl, {
        headers: { "Authorization": `Bearer ${token}`, "Accept": "application/vnd.github+json" }
      });
      if (!r.ok) {
        cbeWrite(`  poll ${attempts}: HTTP ${r.status}`, "");
        return;
      }
      const data = await r.json();

      // Match ANY workflow_dispatch run created after we dispatched.
      // Use 60s buffer — GH created_at lags behind real wall-clock.
      const cutoff = new Date(new Date(dispatchedAt).getTime() - 60000);
      const run = (data.workflow_runs || []).find(
        w => w.event === "workflow_dispatch" && new Date(w.created_at) >= cutoff
      );

      if (!run) {
        if (attempts % 5 === 0) cbeWrite(`  poll ${attempts}/${MAX_ATTEMPTS}: waiting for run…`);
        return;
      }

      if (!_runId) {
        _runId = run.id;
        log(`Run #${_runId} — ${run.status}`, "info");
        cbeWrite(`Run ID : ${_runId}`);
        cbeWrite(`Status : ${run.status}`);
        cbeWrite(`Logs   : https://github.com/${REPO}/actions/runs/${_runId}`);
      } else {
        // Update status on each tick so the user sees progress
        if (attempts % 3 === 0) cbeWrite(`  poll ${attempts}: ${run.status}…`);
      }

      if (run.status !== "completed") return;

      clearInterval(_pollTimer);
      const conclusion = run.conclusion;
      log(`Run #${_runId} → ${conclusion}`, conclusion === "success" ? "ok" : "err");
      setStatus(conclusion);
      cbeWrite(`\n── ${conclusion.toUpperCase()} ──`);

      if (conclusion === "success") {
        // gh-pages deploy takes a few seconds after the run completes.
        // Wait before reading index.json.
        cbeWrite("Waiting for gh-pages deploy…");
        await new Promise(r => setTimeout(r, 8000));
        await fetchArtifacts(token);
      }

      document.getElementById("cta").disabled = false;
    } catch (e) {
      cbeWrite(`  poll ${attempts}: ${e.message}`, "err");
    }
  }, 3000);
}

// ── resolve slides URL from gh-pages/index.json ───────────────
async function fetchArtifacts(token) {
  // Retry up to 4 times — gh-pages content API can be stale
  for (let retry = 0; retry < 4; retry++) {
    try {
      const indexUrl = `https://api.github.com/repos/${REPO}/contents/index.json?ref=gh-pages&_=${Date.now()}`;
      const r = await fetch(indexUrl, {
        cache: "no-store",
        headers: { "Authorization": `Bearer ${token}`, "Accept": "application/vnd.github+json" }
      });
      if (!r.ok) {
        cbeWrite(`  index.json attempt ${retry + 1}: HTTP ${r.status}`);
        await new Promise(r => setTimeout(r, 5000));
        continue;
      }
      const envelope = await r.json();
      const data = JSON.parse(atob(envelope.content.replace(/\n/g, "")));
      const tag  = data.latest;
      if (!tag) { log("index.json has no 'latest' field.", "err"); return; }

      const slidesUrl = `https://${REPO.split("/")[0]}.github.io/${REPO.split("/")[1]}/${tag}/slides.html`;
      log(`Slides → ${slidesUrl}`, "ok");
      cbeWrite(`\n✔  slides: ${slidesUrl}`, "prompt");
      enableButtons(slidesUrl, null);
      return;
    } catch (e) {
      cbeWrite(`  index.json attempt ${retry + 1}: ${e.message}`);
      await new Promise(r => setTimeout(r, 5000));
    }
  }
  log("Could not read index.json after 4 retries.", "err");
}

// ── artifact actions ──────────────────────────────────────────
function openHtmlView() { if (_htmlArtUrl) window.open(_htmlArtUrl, "_blank"); }
function downloadZip()  { if (_zipArtUrl)  window.open(_zipArtUrl,  "_blank"); }
