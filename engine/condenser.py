"""engine/condenser.py — Payload colour compression by cardinality.

Stores colour distributions at two levels of granularity under each
chemistry bucket (base_type):

  1. Flat (whole bucket) — overall colour_counts / color_ratios / total_atoms
     across all atoms of this base_type.  Used as the fallback colouring
     pass when no per-atom-name data is available.

  2. Atom-name subtypes (``atom_names``) — per-atom-name colour distribution,
     stored only for atom names whose colour differs from the dominant colour
     of the whole bucket.  Allows faithful chain-by-chain / element-by-element
     colour restoration without storing every atom position.

Payload shape after compress_payload():

    {
        "macromolecular": {
            "color_counts":  {"11": 1240, "26": 890},
            "color_ratios":  {"11": 0.582, "26": 0.418},
            "total_atoms":   2130,
            "atom_names": {
                "CA": {
                    "color_ratios": {"11": 0.51, "26": 0.49},
                    "total_atoms":  412
                },
                "CB": {
                    "color_ratios": {"26": 1.0},
                    "total_atoms":  380
                }
                // ... only atom names with ≥ 2 distinct colours are stored
            }
        },
        "organic": {
            "color_counts": {"30": 44},
            "color_ratios": {"30": 1.0},
            "total_atoms":  44,
            "atom_names":   {}
        },
        "representations": {...},
        "object_settings": [...]
    }

Keys in color_counts / color_ratios are color-index strings (JSON requires
string keys).  Values are atom counts / fractions respectively.
Atom names that are perfectly monochromatic (single colour across all their
atoms) are omitted from ``atom_names`` to keep the payload compact.
"""

from collections import Counter, defaultdict


def compress_payload(payload: dict, base_type: str) -> dict:
    """Compress raw payload to per-chemistry colour cardinality + atom-name subtypes.

    Consumes ``atom_colors`` (pipe-keyed ``chain|resi|name|alt → color_index``)
    and ``color_rgb`` (``color_index_str → [r, g, b]``) if present, replacing
    them with the two-level structure described in the module docstring.
    RGB values are embedded into each bucket so apply_scene never needs to
    resolve colour indices against a live session.  Everything else is kept as-is.
    """
    out = {k: v for k, v in payload.items()
           if k not in ("atom_colors", "color_rgb")}

    atom_colors = payload.get("atom_colors")
    color_rgb   = payload.get("color_rgb", {})   # {str(cidx): [r, g, b]}

    if not atom_colors or not _is_pipe_keyed(atom_colors):
        return out

    # ── Level 1: flat bucket ─────────────────────────────────────────────────
    counts = Counter(atom_colors.values())
    total = sum(counts.values()) or 1
    bucket: dict = {
        "color_counts": {str(k): v for k, v in counts.items()},
        "color_ratios": {str(k): round(v / total, 6) for k, v in counts.items()},
        "color_rgb":    {str(k): color_rgb.get(str(k)) for k in counts
                         if color_rgb.get(str(k)) is not None},
        "total_atoms":  total,
    }

    # ── Level 2: per-atom-name subtypes ──────────────────────────────────────
    by_name: dict[str, list[int]] = defaultdict(list)
    for key, cidx in atom_colors.items():
        parts = key.split("|")
        atom_name = parts[2] if len(parts) >= 3 else "?"
        by_name[atom_name].append(cidx)

    atom_names: dict[str, dict] = {}
    for aname, cidx_list in by_name.items():
        sub_counts = Counter(cidx_list)
        if len(sub_counts) < 2:
            continue
        sub_total = len(cidx_list)
        atom_names[aname] = {
            "color_ratios": {str(k): round(v / sub_total, 6)
                             for k, v in sub_counts.items()},
            "color_rgb":    {str(k): color_rgb.get(str(k)) for k in sub_counts
                             if color_rgb.get(str(k)) is not None},
            "total_atoms":  sub_total,
        }

    bucket["atom_names"] = atom_names
    out[base_type] = bucket
    return out


def decompress_payload(compressed: dict, base_type: str) -> dict:
    """No-op — compressed format is the storage format."""
    return compressed


def _is_pipe_keyed(data: dict) -> bool:
    """True when majority of keys look like 'chain|resi|atom|alt'."""
    if not data:
        return False
    sample = list(data.keys())[:10]
    hits = sum(1 for k in sample if isinstance(k, str) and k.count("|") == 3)
    return hits > len(sample) * 0.8
