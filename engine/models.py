"""Data model definitions for the sqlite backend.

Schema ontology
---------------
scenes
    meta   → global renderer settings (backend encodes as it sees fit)
    view   → camera / view matrix
    size   → viewport / canvas dimensions

scene_objects
    base_type → one of the BaseType constants below
    payload   → backend-specific JSON fragment for the object

BaseType constants are shared across backends so the SQL store is consistent
regardless of which renderer produced the scene.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# BaseType — renderer-agnostic object classification
# ---------------------------------------------------------------------------

class BaseType:
    """String constants for the base_type column in scene_objects.

    Organic        – small molecule / ligand (sticks, lines)
    Inorganic      – metal cluster, crystal packing, unclassified solid
    Macromolecular – protein or nucleic acid chain (cartoon / ribbon)
    Special        – solvent, ions, pseudo-atoms, axes
    Chains         – selection / chain-group pseudo-objects
    """
    ORGANIC        = "organic"
    INORGANIC      = "inorganic"
    MACROMOLECULAR = "macromolecular"
    SPECIAL        = "special"
    CHAINS         = "chains"


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
    payload: str     # backend-specific JSON fragment


# ---------------------------------------------------------------------------
# Legacy / model-registry dataclasses (kept for future use)
# ---------------------------------------------------------------------------

@dataclass
class ModelEntry:
    id: int
    path: str
    score: float
    tag: str

@dataclass
class MetricsEntry:
    model_id: int
    sasa: float
    max_dist: float

@dataclass
class RenderEntry:
    id: int
    scene: str
    model_ids: str
    settings_hash: str
    output_path: str
    timestamp: str




