"""PyMOL driver — cmd-level entry points for save/apply.

Responsibilities:
  - save_scene:    capture the live session and persist to the shipped DB.
  - apply_scene:   reconstruct visual state in PyMOL using only native
                   PyMOL cmd calls, reading the staged BT schema from DB.
  - SceneSession:  consistent .rendering/ output (png, json, pse).
  - Register user-facing cmd.extend commands.
"""

import datetime as _dt
import json
from pathlib import Path

from pymol import cmd

from .adapter import PyMOLController
from engine.api import BaseType

# ---------------------------------------------------------------------------
# Controller — engine owns the DB; this module just holds the instance.
# ---------------------------------------------------------------------------

_controller: PyMOLController | None = None


def _controller_() -> PyMOLController:
    """Return the module-level controller, initialising on first access."""
    global _controller
    if _controller is None:
        _controller = PyMOLController()
    return _controller


# ---------------------------------------------------------------------------
# Save (capture + store)
# ---------------------------------------------------------------------------

def save_scene(name=None):
    """Capture the current PyMOL session and persist it to the database."""
    controller = _controller_()
    scene_id = controller.ingest_scene(source=None, name=name or "untitled_scene")
    print(f"[rac] saved scene '{name or 'untitled_scene'}' → id={scene_id}")
    return scene_id


# ---------------------------------------------------------------------------
# Apply pipeline — delegate all apply logic to middleware.ApplyPipeline
# ---------------------------------------------------------------------------

from . import middleware as _mw

_applier = _mw.ApplyPipeline()


def _resolve_scene(controller, scene_id, scene_name):
    if scene_id is not None:
        scene = controller.load_scene(scene_id)
    else:
        matches = [s for s in controller.list_scenes() if s["name"] == scene_name]
        if not matches:
            raise ValueError(f"Scene '{scene_name}' not found")
        scene = controller.load_scene(matches[-1]["id"])
    if not scene:
        raise ValueError(f"Scene {scene_id or scene_name!r} not found")
    return scene


def apply_scene(scene_id: int = None, scene_name: str = None):
    """Restore a scene from the database into the active PyMOL session.

    Apply order — macro to micro, no overwrites:
    ─────────────────────────────────────────────
    The order in which scene_objects are applied is NOT arbitrary.
    Each layer narrows scope and must not clobber the previous one:

      1. Global settings + custom colors  (bg, lighting, render params)
      2. Viewport + view matrix
      3. Per-object, sorted by specificity:

           macromolecular  → broadest — sets cartoon/polymer base
           chains          → sub-selections of macro, refine chain colors on top
           organic         → ligands on top of protein context
           inorganic       → metals/clusters
           special         → narrowest catch-all, always last
                              each base type can have its own special sub-bucket

    Chains come right after macromolecular — they are sub-selections of it.
    Special is always last — it is the catch-all and can exist within any
    other type’s context (e.g. solvent near organic, ions near inorganic).

    This is the correct replay contract — never change this order.
    ─────────────────────────────────────────────
    Does NOT call cmd.rebuild() — the caller owns the render cycle.
    """
    if scene_id is None and scene_name is None:
        raise ValueError("Provide scene_id or scene_name")

    controller = _controller_()
    scene = _resolve_scene(controller, scene_id, scene_name)

    all_obj_recs = controller.load_scene_objects(scene["id"])
    stored_names = {r["name"] for r in all_obj_recs}
    live_objs = cmd.get_names("objects")
    same_molecule = bool(stored_names & set(live_objs))

    _applier.replay_scene(scene, all_obj_recs, restore_view=same_molecule)
    if not same_molecule and live_objs:
        cmd.zoom(live_objs[0])
        cmd.orient(live_objs[0])

    obj_recs = sorted(
        all_obj_recs,
        key=lambda r: BaseType.APPLY_ORDER.get(r["base_type"], 5),
    )
    for obj_rec in obj_recs:
        _applier.apply_object(obj_rec, live_objs)

    print(f"[rac] applied scene id={scene['id']} name={scene['name']!r}")


# ---------------------------------------------------------------------------
# SceneSession — consistent .rendering/ output for workshop scripts
# ---------------------------------------------------------------------------

class SceneSession:
    """Manages reference ingest and per-subject apply with consistent output.

    Usage in a workshop script::

        from pymol_backend.driver import SceneSession

        session = SceneSession(output_dir, scene_name, script_tag)

        # Phase A — after styling the reference molecule:
        session.ingest_reference(ref_tag, cif_path)

        # Phase B — for each subject:
        session.apply_subject(tag, cif_path)

    Outputs written under *output_dir*:
      {ref}_loaded.png
      {ref}_staged.png / .pse
      {ref}_raw.json     — pre-middleware _extract_scene doc (scene.meta)
      {ref}_native.json  — DataPipeline output, all 5 BT buckets (pre-DB)
      {ref}_staged.json  — DB payloads keyed by object name (post-DB round-trip)
      {ref}_applied.png
      {ref}_applied.json — DB payloads read back after apply round-trip
      {subj}_applied.png
    """

    def __init__(self, output_dir: Path, scene_name: str, script_tag: str):
        self.output_dir  = Path(output_dir)
        self.scene_name  = scene_name
        self.script_tag  = script_tag          # e.g. "enzyme.py" / "simple.py"
        self._ctrl       = _controller_()
        self._scene_id: int | None = None

        self.output_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "template":      script_tag,
            "generated_at":  _dt.datetime.now().isoformat(timespec="seconds"),
        }
        with open(self.output_dir / ".source.json", "w") as fh:
            json.dump(meta, fh, indent=2)

    # ── reference ────────────────────────────────────────────────────────────

    def run_reference(self, ref_tag: str, cif_path: Path, style_fn) -> int:
        """Full reference flow: load → raw capture → render_loaded → style → ingest.

        Output order:
          loaded.png  — rendered from PyMOL default state, before style.
          style_fn()  — user style applied to the loaded object.
          raw.json    — pre-middleware _extract_scene() doc from DB meta.
                        Written after ingest; the full baseline for inspection.
          staged.json — middleware-processed payload (DB schema).

        Viewport is NOT set here — captured from the live session after
        style_fn runs and stored in the DB by ingest_reference().
        Returns the stored scene_id.
        """
        print(f"\n[{self.script_tag}] REFERENCE ── {ref_tag} ─────────────────────────")
        cmd.reinitialize()
        cmd.load(str(cif_path), ref_tag)
        self.render_loaded(ref_tag)
        style_fn(ref_tag)
        return self.ingest_reference(ref_tag)

    def render_loaded(self, tag: str) -> None:
        """Render and save {tag}_loaded.png (call before applying style)."""
        path = self.output_dir / f"{tag}_loaded.png"
        cmd.png(str(path), width=800, height=600, ray=1)
        print(f"  ✓ {path.name}")

    def ingest_reference(self, ref_tag: str) -> int:
        """Ingest styled reference → DB; write staged.png/.json/.pse.

        Call after the style block has been applied to *ref_tag*.
        Returns the stored scene_id.
        """
        # staged.png
        png = self.output_dir / f"{ref_tag}_staged.png"
        cmd.png(str(png), width=800, height=600, ray=1)
        print(f"  ✓ {png.name}")

        # staged.pse
        pse = self.output_dir / f"{ref_tag}_staged.pse"
        cmd.save(str(pse))
        print(f"  ✓ {pse.name}")

        # ingest → DB
        scene_id = self._ctrl.ingest_scene(name=self.scene_name)
        self._scene_id = scene_id
        print(f"  ✓ ingested → scene_id={scene_id}  name={self.scene_name}")

        # debug JSONs
        self._write_raw_json(f"{ref_tag}_raw.json", scene_id)       # pre-middleware
        self._write_native_json(f"{ref_tag}_native.json", scene_id) # post-DataPipeline
        self._write_staged_json(f"{ref_tag}_staged.json", scene_id) # post-DB round-trip

        return scene_id

    def apply_reference(self, ref_tag: str, cif_path: Path) -> None:
        """Reload reference, apply scene from DB, write applied.png/.json.

        Viewport is restored from DB by apply_scene() — not set here.
        """
        self._ensure_scene_id()
        cmd.reinitialize()
        cmd.load(str(cif_path), ref_tag)
        apply_scene(scene_name=self.scene_name)

        png = self.output_dir / f"{ref_tag}_applied.png"
        cmd.png(str(png), width=800, height=600, ray=1)
        print(f"  ✓ {png.name}")
        self._write_staged_json(f"{ref_tag}_applied.json", self._scene_id)  # post-apply round-trip

    # ── subjects ─────────────────────────────────────────────────────────────

    def apply_subject(self, tag: str, cif_path: Path) -> None:
        """Load subject, apply stored scene, write {tag}_applied.png.

        Viewport is restored from DB by apply_scene() — not set here.
        """
        self._ensure_scene_id()
        print(f"\n[{self.script_tag}] SUBJECT ── {tag}")
        cmd.reinitialize()
        cmd.load(str(cif_path), tag)
        apply_scene(scene_name=self.scene_name)
        png = self.output_dir / f"{tag}_applied.png"
        cmd.png(str(png), width=800, height=600, ray=1)
        print(f"  ✓ {png.name}")

    # ── internal ─────────────────────────────────────────────────────────────

    def _ensure_scene_id(self) -> None:
        if self._scene_id is None:
            raise RuntimeError("call ingest_reference() before apply_reference()/apply_subject()")

    def _write_raw_json(self, filename: str, scene_id: int) -> None:
        """Write pre-middleware _extract_scene doc (scene.meta) to JSON."""
        scene = self._ctrl.load_scene(scene_id)
        path  = self.output_dir / filename
        path.write_text(scene["meta"])
        print(f"  ✓ {path.name}")

    def _write_native_json(self, filename: str, scene_id: int) -> None:
        """Write DataPipeline output (all 5 BT buckets, pre-DB) to JSON."""
        from . import middleware as _mw
        scene = self._ctrl.load_scene(scene_id)
        raw   = json.loads(scene["meta"])
        native = _mw.DataPipeline().process(raw)
        path  = self.output_dir / filename
        with open(path, "w") as fh:
            json.dump(native, fh, indent=2)
        print(f"  ✓ {path.name}")

    def _write_staged_json(self, filename: str, scene_id: int) -> None:
        """Write DB payloads to JSON keyed by BT (post-DB round-trip).

        The DB stores each record as {"objects": {bt: bucket}} for apply().
        Here we unwrap that wrapper so the file reads as {bt: {native, special}}.
        """
        objs = self._ctrl.load_scene_objects(scene_id)
        out  = {}
        for o in objs:
            payload = json.loads(o["payload"])
            # unwrap the {"objects": {bt: bucket}} envelope
            objects_node = payload.get("objects") or {}
            bt = o["name"]
            out[bt] = objects_node.get(bt) or payload  # fallback: raw payload
        path = self.output_dir / filename
        with open(path, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"  ✓ {path.name}")


# ---------------------------------------------------------------------------
# BatchSession — apply a stored scene to RCSB-sourced candidates
# ---------------------------------------------------------------------------

import random as _random
import shutil as _shutil
import urllib.request as _urlreq


class BatchSession(SceneSession):
    """Extends SceneSession for batch / RCSB candidate runs.

    Adds:
      - locate_cif()      — tests/data → run-local cache → global cache → download
      - apply_candidate() — load a CIF by PDB ID, apply scene, write applied.png
      - finalize_meta()   — patch .source.json with final PDB list + RCSB URLs
      - rendered          — list of successfully rendered PDB IDs

    Usage::

        from pymol_backend.driver import BatchSession

        sess = BatchSession(run_dir, scene_id=1, ref_pdb="9ax6",
                            cif_cache=CACHE, fetch_timeout=15)
        sess.apply_reference_by_id(ref_pdb, ref_cif)
        for pdb_id in candidates:
            sess.apply_candidate(pdb_id)
        sess.finalize_meta(category="enzyme")
    """

    _RCSB_CIF  = "https://files.rcsb.org/download/{}.cif"
    _RCSB_ENTRY = "https://www.rcsb.org/structure/{}"
    _RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"

    def __init__(
        self,
        output_dir: Path,
        scene_id: int,
        ref_pdb: str,
        cif_cache: Path,
        fetch_timeout: int = 15,
    ):
        # scene_name resolved from DB; script_tag fixed
        ctrl = PyMOLController()
        scene_row = ctrl.load_scene(scene_id)
        if not scene_row:
            raise ValueError(f"scene_id={scene_id} not found in DB")
        scene_name = scene_row["name"]

        super().__init__(output_dir, scene_name, "batch.py")
        self._scene_id   = scene_id      # override — already known
        self.ref_pdb     = ref_pdb.lower()
        self.cif_cache   = Path(cif_cache)
        self.fetch_timeout = fetch_timeout
        self.rendered: list[str] = []    # populated by apply_candidate

        self.cif_cache.mkdir(parents=True, exist_ok=True)

    # ── CIF resolution ────────────────────────────────────────────────────

    def locate_cif(self, pdb_id: str) -> Path | None:
        """Return a CIF path: tests/data → run cache → global cache → download."""
        pid = pdb_id.lower()
        # 1. bundled test data
        local = self.output_dir.parent.parent.parent / "tests" / "data" / f"{pid}.cif"
        if local.exists():
            return local
        # 2. run-local dir
        run_copy = self.output_dir / f"{pid}.cif"
        if run_copy.exists():
            return run_copy
        # 3. global cache
        cached = self.cif_cache / f"{pid}.cif"
        if cached.exists():
            run_copy.write_bytes(cached.read_bytes())
            return run_copy
        # 4. download
        url = self._RCSB_CIF.format(pdb_id.upper())
        try:
            print(f"  [fetch]  {url}")
            with _urlreq.urlopen(url, timeout=self.fetch_timeout) as resp:
                data = resp.read()
            cached.write_bytes(data)
            run_copy.write_bytes(data)
            return run_copy
        except Exception as exc:
            print(f"  [WARN]   fetch failed for {pdb_id}: {exc}")
            return None

    @staticmethod
    def rcsb_url(pdb_id: str) -> str:
        return BatchSession._RCSB_ENTRY.format(pdb_id.upper())

    # ── rendering ─────────────────────────────────────────────────────────

    def apply_reference_by_id(self, pdb_id: str) -> bool:
        """Locate reference CIF, apply stored scene, write applied.png."""
        cif = self.locate_cif(pdb_id)
        if cif is None:
            print(f"[batch] ERROR: cannot locate reference CIF {pdb_id}")
            return False
        print(f"\n[batch] REFERENCE ── {pdb_id}")
        cmd.reinitialize()
        cmd.load(str(cif), pdb_id)
        cmd.viewport(800, 600)
        apply_scene(scene_id=self._scene_id)
        png = self.output_dir / f"{pdb_id}_applied.png"
        cmd.png(str(png), width=800, height=600, ray=1)
        print(f"  ✓ {png.name}")
        return True

    def apply_candidate(self, pdb_id: str) -> bool:
        """Locate candidate CIF, apply stored scene, write applied.png."""
        cif = self.locate_cif(pdb_id)
        if cif is None:
            return False
        print(f"\n[batch] CANDIDATE ── {pdb_id}")
        cmd.reinitialize()
        cmd.load(str(cif), pdb_id)
        cmd.viewport(800, 600)
        apply_scene(scene_id=self._scene_id)
        png = self.output_dir / f"{pdb_id}_applied.png"
        cmd.png(str(png), width=800, height=600, ray=1)
        print(f"  ✓ {png.name}")
        self.rendered.append(pdb_id)
        return True

    # ── meta ──────────────────────────────────────────────────────────────

    def write_initial_meta(self, category: str) -> None:
        """Write .source.json with run context (call before rendering)."""
        meta = {
            "template":      self.script_tag,
            "generated_at":  _dt.datetime.now().isoformat(timespec="seconds"),
            "category":      category,
            "scene":         self.scene_name,
            "rcsb_urls":     {self.ref_pdb.upper(): self.rcsb_url(self.ref_pdb)},
        }
        (self.output_dir / ".source.json").write_text(json.dumps(meta, indent=2))

    def finalize_meta(self, category: str) -> None:
        """Patch .source.json with final PDB list and all RCSB URLs."""
        src = self.output_dir / ".source.json"
        try:
            meta = json.loads(src.read_text())
        except Exception:
            meta = {}
        meta["PDB_codes"] = [self.ref_pdb] + self.rendered
        meta.setdefault("rcsb_urls", {})[self.ref_pdb.upper()] = self.rcsb_url(self.ref_pdb)
        for pid in self.rendered:
            meta["rcsb_urls"][pid.upper()] = self.rcsb_url(pid)
        src.write_text(json.dumps(meta, indent=2))
        print(f"  [meta]   .source.json updated ({len(self.rendered)} candidates)")


# ---------------------------------------------------------------------------
# cmd.extend registrations — user-facing PyMOL commands
# ---------------------------------------------------------------------------

cmd.extend("save_scene",  save_scene)
cmd.extend("apply_scene", apply_scene)
