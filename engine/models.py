"""Data model definitions for the sqlite backend.

Schema ontology
---------------
scenes
    meta   → global renderer settings (backend encodes as it sees fit)
    view   → camera / view matrix
    size   → viewport / canvas dimensions

scene_objects
    base_type → one of the BaseType constants below
    payload   → JSON fragment conforming to BtPayload (see below)

Payload contract
----------------
Every backend must produce a payload that, for each base_type bucket,
conforms to BtPayload.  This is the sole accepted DB shape.
The contract is enforced by the TypedDicts below — not by runtime checks,
but by the type system and by LayerD.to_bt_payload() being the only
authorised constructor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


# ---------------------------------------------------------------------------
# BaseType — renderer-agnostic object classification
# ---------------------------------------------------------------------------

class BaseType:
    """String constants for the base_type column in scene_objects.

    Organic        - small molecule / ligand (sticks, lines)
    Inorganic      - metal cluster, crystal packing, unclassified solid
    Macromolecular - protein or nucleic acid chain (cartoon / ribbon)
    Special        - solvent, ions, pseudo-atoms, axes
    Chains         - selection / chain-group pseudo-objects
    """
    ORGANIC        = "organic"
    INORGANIC      = "inorganic"
    MACROMOLECULAR = "macromolecular"
    SPECIAL        = "special"
    CHAINS         = "chains"

    # Apply order contract (macro → micro, never change).
    # Each level refines without clobbering the previous.
    # See copilot-instructions.md § Apply Order Contract.
    APPLY_ORDER: dict[str, int] = {
        "macromolecular": 0,
        "chains":         1,
        "organic":        2,
        "inorganic":      3,
        "special":        4,
    }


# ---------------------------------------------------------------------------
# Payload contract — the only accepted DB shape for scene_objects.payload
# ---------------------------------------------------------------------------

class NativePayload(TypedDict, total=False):
    """The ``native`` sub-dict inside each BT bucket.

    Produced by LayerD.to_bt_payload() from raw atom_colors.
    All keys optional at construction time; validated at write time.

    atom_names   : {atom_name: dominant_color_index}  — flat, no nesting
    color_counts : {str(cidx): atom_count}
    color_ratios : {str(cidx): fraction_0_to_1}
    color_rgb    : {str(cidx): [r, g, b]}
    total_atoms  : total atom count in this BT slice
    ratio        : fraction of object atoms covered by this BT slice
    representations: {rep_name: bool}
    """
    atom_names:    dict
    color_counts:  dict
    color_ratios:  dict
    color_rgb:     dict
    total_atoms:   int
    ratio:         float
    representations: dict


class SpecialEntry(TypedDict, total=False):
    """One entry in the ``special`` list inside a BT bucket.

    Produced by LayerD drift detection.
    pipe_keys    : ["chain|resi|name|alt", ...]  — exact drifted atom keys
    color_index  : int
    color_rgb    : [r, g, b]
    ratio        : float  (len(pipe_keys) / total_bt_atoms)
    representations: {rep_name: bool}  — only present when rep drifted
    """
    pipe_keys:     list
    color_index:   int
    color_rgb:     list
    ratio:         float
    representations: dict


class BtPayload(TypedDict, total=False):
    """The value stored under each base_type key in scene_objects.payload.

    {"macromolecular": BtPayload, "organic": BtPayload, ...}

    native  : NativePayload   — baseline state
    special : list[SpecialEntry]  — drift on top of native
    """
    native:  NativePayload
    special: list


# ---------------------------------------------------------------------------
# Scene dataclasses (mirror the SQL schema)
# ---------------------------------------------------------------------------

@dataclass
class SceneRecord:
    """Maps to the ``scenes`` table."""
    id: int
    name: str
    meta: str   # serialised global settings
    view: str   # serialised view / camera state
    size: str   # serialised viewport
    created: str


@dataclass
class SceneObject:
    """Maps to the ``scene_objects`` table."""
    id: int
    scene_id: int
    name: str
    base_type: str   # one of BaseType.*
    payload: str     # JSON-serialised dict of {base_type: BtPayload, ...}

