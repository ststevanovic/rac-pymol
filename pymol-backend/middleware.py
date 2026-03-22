"""pymol-backend/middleware.py - Raw session JSON -> staged BT payload.

Capture (DataPipeline)
----------------------
LayerE   live cmd, one object -> raw object dict
LayerD   atom_colors dict     -> NativePayload fields + drift special
LayerC   raw object dict      -> all-5-BT staged payload  (uses LayerD)
DataPipeline
  process(raw)        -> staged   transform a raw dict (file or template)
  capture_live()      -> (raw, staged)   read live cmd session then transform

Apply (ApplyPipeline)
---------------------
ApplyPipeline  staged BT payload + DB records -> pure cmd calls
  apply_object(obj_rec, live_objs)   restore one scene object
  replay_scene(scene, obj_recs)      replay global settings + view


  TODO: produces and consumers
"""

from __future__ import annotations

from collections import Counter, defaultdict

try:
    from pymol import cmd as _cmd
    import pymol.setting as _ps
    _HAVE_CMD = True
except Exception:
    _cmd = None
    _ps  = None
    _HAVE_CMD = False

# BT constants - match models.py BaseType values exactly.
_BT_MACRO     = "macromolecular"
_BT_ORGANIC   = "organic"
_BT_INORGANIC = "inorganic"
_BT_CHAINS    = "chains"
_BT_SPECIAL   = "special"

_SUFFIX_TO_BT: dict[str, str] = {
    "organics":   _BT_ORGANIC,
    "inorganics": _BT_INORGANIC,
}


# ---------------------------------------------------------------------------
# Layer E - live cmd -> raw object dict
# ---------------------------------------------------------------------------

class LayerE:
    """Reads one live PyMOL object via cmd and returns a raw dict.

    Raw object schema (all values are direct cmd output, nothing derived):
      representations : {rep_name: bool}
      atom_colors     : {"chain|resi|name|alt": int}   color index
      chains          : [str] | None
      color_index     : int
      object_matrix   : [float x 16]
      visibility      : bool | None
      object_settings : [[name, type, value], ...] | None
    """

    def process(self, obj: str, **ctx) -> dict:
        representations: dict[str, bool] = {}
        try:
            for rep in _cmd.repres:
                representations[rep] = _cmd.count_atoms(f"({obj}) and rep {rep}") > 0
        except Exception:
            pass

        atom_colors: dict[str, int] = {}
        try:
            _cmd.iterate(
                f"({obj})",
                "atom_colors[f'{chain}|{resi}|{name}|{alt}'] = color",
                space={"atom_colors": atom_colors},
            )
        except Exception:
            pass

        chains: list[str] = []
        try:
            chains = _cmd.get_chains(obj) or []
        except Exception:
            pass

        try:
            color_index = _cmd.get_object_color_index(obj)
        except Exception:
            color_index = 0

        try:
            object_matrix = list(_cmd.get_object_matrix(obj) or [])
        except Exception:
            object_matrix = []

        try:
            vis = _cmd.get_vis()
            visibility = vis[0].get(obj) if vis else None
        except Exception:
            visibility = None

        # Per-object settings that differ from the global value.
        # Stored as [name, type_int, raw_value] - no resolution.
        object_settings: list = []
        if _ps is not None:
            try:
                for sname in _ps.get_name_list():
                    try:
                        typ, (val,) = _cmd.get_setting_tuple(sname, obj)
                        _, (gval,) = _cmd.get_setting_tuple(sname)
                        if val != gval:
                            object_settings.append([sname, typ, val])
                    except Exception:
                        pass
            except Exception:
                pass

        return {
            "representations":  representations,
            "atom_colors":      atom_colors,
            "chains":           chains or None,
            "color_index":      color_index,
            "object_matrix":    object_matrix,
            "visibility":       visibility,
            "object_settings":  object_settings or None,
        }


# ---------------------------------------------------------------------------
# Layer D - atom_colors -> NativePayload fields + drift special
# ---------------------------------------------------------------------------

class LayerD:
    """atom_colors {pipe_key: cidx} -> NativePayload-conformant dict.

      atom_names   : {atom_name: dominant_cidx}
      color_counts : {str(cidx): count}
      color_ratios : {str(cidx): fraction}
      color_rgb    : {str(cidx): [r,g,b]}   resolved via cmd when available
      total_atoms  : int
      ratio        : 1.0
      special      : [{pipe_keys, color_index, color_rgb, ratio}, ...]
    """

    def process(self, atom_colors: dict, obj_name: str = "", bt: str = "") -> dict:
        if not atom_colors:
            return {
                "atom_names": {}, "color_counts": {}, "color_ratios": {},
                "color_rgb": {}, "total_atoms": 0, "ratio": 1.0, "special": [],
            }

        by_name: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for pipe_key, cidx in atom_colors.items():
            parts = pipe_key.split("|")
            aname = parts[2] if len(parts) > 2 else "?"
            by_name[aname].append((pipe_key, cidx))

        dominant: dict[str, int] = {
            aname: Counter(cidx for _, cidx in pairs).most_common(1)[0][0]
            for aname, pairs in by_name.items()
        }

        total = len(atom_colors)
        all_counts: Counter = Counter(atom_colors.values())
        color_counts = {str(k): v for k, v in all_counts.items()}
        color_ratios = {str(k): round(v / total, 6) for k, v in all_counts.items()}

        color_rgb: dict[str, list] = {}
        if _HAVE_CMD and _cmd is not None:
            for cidx in all_counts:
                try:
                    color_rgb[str(cidx)] = list(_cmd.get_color_tuple(cidx))
                except Exception:
                    pass

        drift_by_cidx: dict[int, list[str]] = defaultdict(list)
        for aname, pairs in by_name.items():
            dom = dominant[aname]
            for pipe_key, cidx in pairs:
                if cidx != dom:
                    drift_by_cidx[cidx].append(pipe_key)

        special: list[dict] = []
        for cidx, keys in drift_by_cidx.items():
            entry: dict = {
                "ratio":       round(len(keys) / total, 4),
                "color_index": cidx,
                "pipe_keys":   keys,
            }
            rgb = color_rgb.get(str(cidx))
            if rgb is not None:
                entry["color_rgb"] = rgb
            special.append(entry)

        return {
            "atom_names":   dominant,
            "color_counts": color_counts,
            "color_ratios": color_ratios,
            "color_rgb":    color_rgb,
            "total_atoms":  total,
            "ratio":        1.0,
            "special":      special,
        }


# ---------------------------------------------------------------------------
# Layer C - one raw object[name] dict -> (bt, native, special[, chains_data])
# ---------------------------------------------------------------------------

_ALL_BTS = (_BT_MACRO, _BT_ORGANIC, _BT_INORGANIC, _BT_CHAINS, _BT_SPECIAL)

_EMPTY_NATIVE = {
    "atom_names": {}, "color_counts": {}, "color_ratios": {},
    "color_rgb": {}, "total_atoms": 0, "ratio": 0.0,
}


class LayerC:
    """Owns one objects[name] dict level.

    Classifies BT from label, strips raw-only keys, delegates atom_colors
    to LayerD. Returns (bt, native, special).
    """
    _D_FIELDS = frozenset({
        "atom_names", "color_counts", "color_ratios",
        "color_rgb", "total_atoms", "ratio",
    })
    _SKIP = frozenset({"atom_colors", "base_type"})

    def __init__(self):
        self._layer_d = LayerD()

    def process(self, obj_dict: dict, label: str = "") -> tuple[str, dict, list]:
        bt     = obj_dict.get("base_type") or _classify_label(label)
        native = {k: v for k, v in obj_dict.items() if k not in self._SKIP}
        ac     = obj_dict.get("atom_colors") or {}

        d_out = self._layer_d.process(ac, obj_name=label, bt=bt)
        for field in self._D_FIELDS:
            native[field] = d_out[field]

        # Augment color_rgb with any color indices found in object_settings
        # (e.g. cartoon_color) that were not present in atom_colors.
        if _HAVE_CMD and _cmd is not None:
            rgb_map = native["color_rgb"]
            for entry in (obj_dict.get("object_settings") or []):
                if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                    cidx = entry[2]
                    if isinstance(cidx, int) and str(cidx) not in rgb_map:
                        try:
                            rgb_map[str(cidx)] = list(_cmd.get_color_tuple(cidx))
                        except Exception:
                            pass

        return bt, native, d_out["special"]


# ---------------------------------------------------------------------------
# DataPipeline - public facade
# ---------------------------------------------------------------------------

class DataPipeline:
    """Single entry point for all session capture and transform work.

      capture_live() -> (raw, staged)   read live cmd session + transform
      process(raw)   -> staged          transform a raw dict (file or template)
    """

    def __init__(self):
        self._layer_c = LayerC()

    def process(self, raw: dict) -> dict:
        """LayerA: copy root keys through, delegate objects to LayerB logic.

        Output schema (fixed):
          global_settings, view_matrix, viewport  -- passed through
          objects: {
            macromolecular: [{native}, {special}],
            organic:        [{native}, {special}],
            inorganic:      [{native}, {special}],
            special:        [{native}, {special}],
            chains:         {"A": [{native}, {special}], "B": ...},
          }
        """
        # LayerA -- root passthrough
        staged: dict = {k: raw[k] for k in ("global_settings", "view_matrix", "viewport", "camera_position") if k in raw}

        # LayerB -- aggregate all objects into the fixed BT slots
        objects_out: dict = {
            _BT_MACRO:     {"native": dict(_EMPTY_NATIVE), "special": []},
            _BT_ORGANIC:   {"native": dict(_EMPTY_NATIVE), "special": []},
            _BT_INORGANIC: {"native": dict(_EMPTY_NATIVE), "special": []},
            _BT_SPECIAL:   {"native": dict(_EMPTY_NATIVE), "special": []},
            _BT_CHAINS:    {},
        }

        # Keep raw atom_colors per label for the cross-reference pass below.
        raw_atom_colors: dict[str, dict] = {}

        for label, obj_dict in (raw.get("objects") or {}).items():
            bt, native, special = self._layer_c.process(obj_dict, label=label)
            raw_atom_colors[label] = obj_dict.get("atom_colors") or {}
            if bt == _BT_CHAINS:
                # chain letter = suffix after first "_" (e.g. "9ax6_A" -> "A")
                chain_key = label.split("_", 1)[1] if "_" in label else label
                objects_out[_BT_CHAINS][chain_key] = {"native": native, "special": special}
            else:
                objects_out[bt] = {"native": native, "special": special}

        # Processed natives keyed by label — used to pull color data into sub-blocks.
        processed_natives: dict[str, dict] = {}
        for label, obj_dict in (raw.get("objects") or {}).items():
            bt_check = _classify_label(label)
            if bt_check == _BT_SPECIAL:
                processed_natives[label] = objects_out[_BT_SPECIAL].get("native") or {}

        # ── special sub-block injection ───────────────────────────────────
        # For every raw object that landed in _BT_SPECIAL, cross-reference
        # its atom pipe_keys against each chain bucket (by chain+resi) and
        # against macromolecular (any chain, by resi).  When atoms overlap,
        # inject an entry into that bucket's `special` list:
        #   {"name": <raw_label>, "representations": {...}, "residues": [resi, ...]}
        #
        # "residues" are the matched resi values (molecule IDs) for that bucket.

        # Build per-chain residue sets from chain buckets' raw atom_colors.
        # Key: chain_letter -> set of resi strings present in that chain's atoms.
        chain_resi_sets: dict[str, set] = {}
        for label, obj_dict in (raw.get("objects") or {}).items():
            bt_check = _classify_label(label)
            if bt_check == _BT_CHAINS:
                chain_key = label.split("_", 1)[1] if "_" in label else label
                ac = obj_dict.get("atom_colors") or {}
                chain_resi_sets[chain_key] = {pk.split("|")[1] for pk in ac}

        # Also build a global resi set for macromolecular (union of all chains).
        macro_resi_set: set = set()
        for resis in chain_resi_sets.values():
            macro_resi_set |= resis

        for label, obj_dict in (raw.get("objects") or {}).items():
            bt_check = _classify_label(label)
            if bt_check != _BT_SPECIAL:
                continue

            sp_ac    = raw_atom_colors.get(label) or {}
            sp_reps  = obj_dict.get("representations") or {}
            active_reps = {k: v for k, v in sp_reps.items() if v}
            if not active_reps:
                continue

            # Color data from the processed special native for this label.
            sp_native   = processed_natives.get(label) or {}
            sp_color_rgb  = sp_native.get("color_rgb") or {}
            sp_atom_names = sp_native.get("atom_names") or {}

            # Build {chain: set(resi)} from this special object's pipe_keys.
            sp_by_chain: dict[str, set] = {}
            for pk in sp_ac:
                parts = pk.split("|")
                if len(parts) >= 2:
                    sp_by_chain.setdefault(parts[0], set()).add(parts[1])

            # Inject into each matching chain bucket.
            for chain_key, bucket in objects_out[_BT_CHAINS].items():
                # chain_key is the suffix letter; pipe_key chain field matches it.
                matched_resis = sorted(
                    sp_by_chain.get(chain_key, set()) & chain_resi_sets.get(chain_key, set()),
                    key=lambda r: int(r) if r.lstrip("-").isdigit() else r,
                )
                if matched_resis:
                    bucket["special"].append({
                        "name":            label,
                        "representations": active_reps,
                        "residues":        matched_resis,
                        "color_rgb":       sp_color_rgb,
                        "atom_names":      sp_atom_names,
                    })

            # Inject into macromolecular bucket if any atoms overlap.
            all_sp_resis = {r for rset in sp_by_chain.values() for r in rset}
            macro_matched = sorted(
                all_sp_resis & macro_resi_set,
                key=lambda r: int(r) if r.lstrip("-").isdigit() else r,
            )
            if macro_matched:
                objects_out[_BT_MACRO]["special"].append({
                    "name":            label,
                    "representations": active_reps,
                    "residues":        macro_matched,
                    "color_rgb":       sp_color_rgb,
                    "atom_names":      sp_atom_names,
                })

        staged["objects"] = objects_out
        return staged

    def capture_live(self) -> tuple[dict, dict]:
        """Read live PyMOL session and return (raw, staged)."""
        if not _HAVE_CMD:
            raise RuntimeError("PyMOL not available - cannot capture live session")
        layer_e  = LayerE()
        all_objs = _cmd.get_names("objects")
        session  = _cmd.get_session()
        raw = {
            "global_settings": {n: _cmd.get_setting_text(n) for n in _ps.get_name_list()},
            "view_matrix":     list(_cmd.get_view()),
            "camera_position": list(_cmd.get_position()),
            "viewport":        list(session.get("main", [])),
            "objects":         {obj: layer_e.process(obj) for obj in all_objs},
        }
        return raw, self.process(raw)


# ---------------------------------------------------------------------------
# build_raw_object - schema-enforced template/test constructor
# ---------------------------------------------------------------------------

def build_raw_object(
    representations: dict[str, bool],
    atom_colors: dict[str, int],
    chains: list[str] | None = None,
    object_settings: list | None = None,
    visibility: bool | None = None,
    color_index: int = 0,
    object_matrix: list | None = None,
) -> dict:
    """Build a raw object dict without a live PyMOL session.

    atom_colors values MUST be integer color indices.
    Use cmd.get_color_index("yellow") to resolve a name to an index first.
    DataPipeline resolves indices to RGB internally via LayerD.
    """
    bad = {k: v for k, v in atom_colors.items() if not isinstance(v, int)}
    if bad:
        raise TypeError(
            "atom_colors values must be int color indices; got: "
            + ", ".join(f"{k!r}={v!r}" for k, v in list(bad.items())[:3])
        )
    return {
        "representations":  representations,
        "atom_colors":      atom_colors,
        "chains":           chains or None,
        "color_index":      color_index,
        "object_matrix":    object_matrix or [],
        "visibility":       visibility,
        "object_settings":  object_settings or None,
    }


# ---------------------------------------------------------------------------
# BT classification helper
# ---------------------------------------------------------------------------

def _classify_label(label: str) -> str:
    """Classify an object label into a BT by suffix convention.

    9ax6            -> macromolecular  (no underscore)
    9ax6_A          -> chains          (single uppercase letter suffix)
    9ax6_organics   -> organic
    9ax6_inorganics -> inorganic
    9ax6_*          -> special
    """
    if "_" not in label:
        return _BT_MACRO
    suffix = label.split("_", 1)[1]
    if suffix in _SUFFIX_TO_BT:
        return _SUFFIX_TO_BT[suffix]
    if len(suffix) == 1 and suffix.isupper():
        return _BT_CHAINS
    return _BT_SPECIAL


# ---------------------------------------------------------------------------
# Apply pipeline — staged BT payload -> pure cmd calls
# ---------------------------------------------------------------------------

import json as _json

_BT_SELECTOR: dict[str, str] = {
    "macromolecular": "polymer",
    "organic":        "organic",
    "inorganic":      "inorganic",
    "special":        "solvent",
    "chains":         "",
}


class ApplyPipeline:
    """Translate staged BT payloads back into live PyMOL cmd calls.

    Public methods:
      apply_object(obj_rec, live_objs)  — restore one scene object
      replay_scene(scene, obj_recs)     — replay global settings + view

    All output is pure cmd calls — no DB access, no middleware transforms.
    """

    # ── color helpers ────────────────────────────────────────────────────

    def dominant_color(self, native: dict) -> str | None:
        """Register and return a cmd color name for the most prevalent color."""
        ratios  = native.get("color_ratios") or {}
        rgb_map = native.get("color_rgb")    or {}
        if not ratios:
            return None
        dominant_cidx = max(ratios, key=lambda k: ratios[k])
        rgb = rgb_map.get(dominant_cidx)
        if rgb is None:
            return None
        color_name = f"_rac_{dominant_cidx}"
        _cmd.set_color(color_name, list(rgb))
        return color_name

    def apply_atom_name_colors(self, native: dict, sele: str) -> None:
        """Color by dominant per-atom-name color index."""
        atom_names = native.get("atom_names") or {}
        rgb_map    = native.get("color_rgb")  or {}
        for aname, cidx in atom_names.items():
            rgb = rgb_map.get(str(cidx))
            if rgb is None:
                continue
            cname = f"_rac_atom_{cidx}"
            _cmd.set_color(cname, list(rgb))
            try:
                _cmd.color(cname, f"({sele}) and name {aname}")
            except Exception:
                pass

    def apply_drift(self, special: list, sele: str, rgb_map: dict) -> None:
        """Re-color drifted atoms by their exact pipe_key coordinates."""
        for entry in (special or []):
            pipe_keys = entry.get("pipe_keys") or []
            if not pipe_keys:
                continue  # skip special-subblock entries (they have "residues", not "pipe_keys")
            rgb = entry.get("color_rgb") or rgb_map.get(str(entry.get("color_index")))
            if rgb is None:
                continue
            cname = f"_rac_drift_{entry.get('color_index')}"
            _cmd.set_color(cname, list(rgb))
            atom_selectors = []
            for pk in pipe_keys:
                parts = pk.split("|")
                if len(parts) == 4:
                    chain, resi, aname, alt = parts
                    atom_selectors.append(
                        f"(({sele}) and chain {chain} and resi {resi} and name {aname})"
                    )
            if atom_selectors:
                try:
                    _cmd.color(cname, " or ".join(atom_selectors))
                except Exception:
                    pass

    def apply_special_subblocks(
        self, special: list, sele: str, chain_id: str | None = None
    ) -> None:
        """Apply special sub-block entries (residue-level representation overrides).

        Each entry: {"name", "representations", "residues", "color_rgb", "atom_names"}
        Selection scope: sele narrowed to matched residues (and chain if given).
        Colors are applied per atom-name using the stored atom_names + color_rgb.
        """
        for entry in (special or []):
            residues = entry.get("residues")
            if not residues:          # drift entry or empty — skip
                continue
            resi_str = "+".join(str(r) for r in residues)
            if chain_id:
                sub_sele = f"({sele}) and chain {chain_id} and resi {resi_str}"
            else:
                sub_sele = f"({sele}) and resi {resi_str}"
            try:
                if _cmd.count_atoms(sub_sele) == 0:
                    continue
            except Exception:
                continue
            self.apply_reps(entry.get("representations"), sub_sele)
            # Apply per-atom-name colors from the original special object.
            atom_names = entry.get("atom_names") or {}
            rgb_map    = entry.get("color_rgb")   or {}
            for aname, cidx in atom_names.items():
                rgb = rgb_map.get(str(cidx))
                if rgb is None:
                    continue
                cname = f"_rac_sp_{cidx}"
                _cmd.set_color(cname, list(rgb))
                try:
                    _cmd.color(cname, f"({sub_sele}) and name {aname}")
                except Exception:
                    pass

    def apply_reps(self, reps: dict | None, sele: str) -> None:
        """Replay exactly the stored rep state — no fallback defaults."""
        for rep, active in (reps or {}).items():
            try:
                if active:
                    _cmd.show(rep, sele)
                else:
                    _cmd.hide(rep, sele)
            except Exception:
                pass

    def color_and_drift(self, native: dict, special: list, sele: str) -> None:
        """Dominant base coat -> atom-name refinement -> drift."""
        dominant = self.dominant_color(native)
        if dominant:
            _cmd.color(dominant, sele)
        self.apply_atom_name_colors(native, sele)
        self.apply_drift(special, sele, native.get("color_rgb") or {})

    # ── per-BT appliers ──────────────────────────────────────────────────

    def apply_standard(self, native: dict, special: list, sele: str) -> None:
        """Shared apply for macromolecular, organic, and inorganic BTs."""
        self.apply_reps(native.get("representations"), sele)
        self.color_and_drift(native, special, sele)
        self.apply_special_subblocks(special, sele)

    def apply_special_bt(self, native: dict, special: list, sele: str) -> None:
        self.apply_reps(native.get("representations"), sele)
        dominant = self.dominant_color(native)
        if dominant:
            _cmd.color(dominant, sele)
        self.apply_drift(special, sele, native.get("color_rgb") or {})

    def apply_chains_obj(self, payload: dict, target: str) -> None:
        """Apply per-chain colors from chains BT sub-entries.

        chains BT is a dict keyed by chain letter, each {native, special}.
        Color comes from object_settings cartoon_color, not atom color index.
        """
        chains_bt = (payload.get("objects") or {}).get(_BT_CHAINS) or {}
        if not chains_bt:
            return
        for chain_id, bucket in chains_bt.items():
            native  = bucket.get("native") or {}
            special = bucket.get("special") or []
            sele = f"({target}) and polymer and chain {chain_id}"
            try:
                if _cmd.count_atoms(sele) == 0:
                    continue
            except Exception:
                continue
            _cmd.hide("everything", sele)
            self.apply_reps(native.get("representations"), sele)
            # Replay object_settings (cartoon_color etc.) on chain sub-selection.
            # Do NOT call cmd.color() — visual color is driven by cartoon_color,
            # not by the atom color index captured during iterate().
            # cartoon_color is a session-specific dynamic index — resolve via
            # color_rgb and register a named color before setting.
            rgb_map = native.get("color_rgb") or {}
            for entry in (native.get("object_settings") or []):
                if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                    sname, _stype, sval = entry[0], entry[1], entry[2]
                    if sname == "cartoon_color":
                        rgb = rgb_map.get(str(sval))
                        if rgb is not None:
                            cname = f"_rac_cc_{sval}"
                            _cmd.set_color(cname, list(rgb))
                            try:
                                _cmd.set("cartoon_color", cname, sele)
                            except Exception:
                                pass
                        continue
                    try:
                        _cmd.set(sname, sval, sele)
                    except Exception:
                        pass
            self.apply_drift(special, sele, native.get("color_rgb") or {})
            self.apply_special_subblocks(special, sele, chain_id=chain_id)

    _BT_APPLY_FN: dict[str, str] = {
        "macromolecular": "apply_standard",
        "organic":        "apply_standard",
        "inorganic":      "apply_standard",
        "special":        "apply_special_bt",
    }

    # ── object-level orchestration ───────────────────────────────────────

    def apply_object(self, obj_rec: dict, live_objs: list) -> None:
        """Restore representations and colours for one scene object."""
        obj_name  = obj_rec["name"]
        base_type = obj_rec["base_type"]
        payload   = _json.loads(obj_rec["payload"]) if isinstance(obj_rec["payload"], str) else obj_rec["payload"]

        cross_molecule = obj_name not in live_objs
        target = obj_name if not cross_molecule else (live_objs[0] if live_objs else None)
        if not target:
            return

        objects_node = payload.get("objects") or {}

        if base_type == "chains":
            self.apply_chains_obj(payload, target)
            return

        chem_kw = _BT_SELECTOR.get(base_type, "")
        method  = self._BT_APPLY_FN.get(base_type)
        if method is None:
            return

        sele = f"({target}) and {chem_kw}" if chem_kw else f"({target})"
        try:
            if _cmd.count_atoms(sele) == 0:
                return
        except Exception:
            return

        bt_bucket = objects_node.get(base_type) or {}
        native    = bt_bucket.get("native") or {}
        special   = bt_bucket.get("special") or []

        _cmd.hide("everything", sele)

        for entry in (payload.get("object_settings") or []):
            if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                try:
                    _cmd.set(entry[0], entry[2], target)
                except Exception:
                    pass

        getattr(self, method)(native, special, sele)

    # ── scene-level orchestration ─────────────────────────────────────────

    def replay_scene(
        self,
        scene: dict,
        obj_recs: list[dict],
        restore_view: bool = True,
    ) -> None:
        """Replay global settings, custom colors, viewport, and optionally view."""
        self._register_custom_colors(obj_recs)
        meta = _json.loads(scene["meta"])
        for setting_name, value in (meta.get("global_settings") or {}).items():
            try:
                _cmd.set(setting_name, value)
            except Exception:
                pass
        viewport = _json.loads(scene["size"])
        if viewport and any(v > 0 for v in viewport):
            _cmd.viewport(*viewport)
        if restore_view:
            view = _json.loads(scene["view"])
            if view:
                _cmd.set_view(view[:18])

    def _register_custom_colors(self, obj_recs: list[dict]) -> None:
        """Register custom colors from all DB payloads before settings replay."""
        for rec in obj_recs:
            payload = _json.loads(rec["payload"]) if isinstance(rec["payload"], str) else rec["payload"]
            for name, rgb in (payload.get("custom_colors") or {}).items():
                try:
                    _cmd.set_color(name, list(rgb))
                except Exception:
                    pass
