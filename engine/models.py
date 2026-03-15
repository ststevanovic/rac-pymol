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

Global view types (AbstractViewCommons and concrete dataclasses) provide a
renderer-agnostic physical-state representation for the "Stage" (background,
lighting, fog, rendering quality).  Backend-specific modules translate between
their native setting keys and these canonical structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Tuple


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
# AbstractViewCommons — The "Stage" ABC
# ---------------------------------------------------------------------------

class AbstractViewCommons(ABC):
    """Renderer-agnostic interface for the global visual environment.

    Each tool integration (PyMOL, ChimeraX, VMD, …) subclasses this and maps
    the canonical fields to its own set/display/lighting commands.

    Environment
    -----------
    background_rgb   : RGB tuple in [0, 1] range.
    projection_mode  : ``'perspective'`` or ``'orthographic'``.
    field_of_view    : Camera field of view in degrees.

    Depth & Fog
    -----------
    depth_cue_enabled : Whether depth-cueing / fog is active.
    depth_cue_params  : ``{"start": float, "end": float, "density": float}``.

    Lighting (Physical Model)
    -------------------------
    lights            : List of light descriptors, e.g.
                        ``[{"vector": (x, y, z), "intensity": float,
                           "type": "key"}]``.
                        One entry for PyMOL; N entries for ChimeraX/VMD.
    ambient_occlusion : Ambient-occlusion flag (ChimeraX has it; PyMOL does
                        not).

    Rendering Logic
    ---------------
    shadow_style      : ``'none'``, ``'hard'``, or ``'soft'``.
    antialiasing_level: Global sampling rate (int).
    """

    # --- Environment ---
    background_rgb: Tuple[float, float, float]
    projection_mode: str             # 'perspective' | 'orthographic'
    field_of_view: float             # In degrees

    # --- Depth & Fog ---
    depth_cue_enabled: bool
    depth_cue_params: Dict           # { "start": float, "end": float,
    #                                    "density": float }

    # --- Lighting (Physical Model) ---
    lights: List[Dict]               # [{ "vector": (x,y,z),
    #                                    "intensity": float, "type": "key" }]
    ambient_occlusion: bool

    # --- Rendering Logic ---
    shadow_style: str                # 'none' | 'hard' | 'soft'
    antialiasing_level: int

    @abstractmethod
    def apply(self) -> None:
        """Push this physical state to the live rendering session."""


# ---------------------------------------------------------------------------
# Physical-state dataclasses (the canonical DB representation)
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentState:
    """Canonical representation of the scene environment."""
    bg_color: Tuple[float, float, float]
    fog: Dict  # {"enabled": bool, "start": float, "end": float}


@dataclass
class LightingState:
    """Canonical representation of the lighting model."""
    model: str                             # e.g. 'standard_three_point'
    ambient: float
    diffuse: float
    specular: float
    light_vector: Tuple[float, float, float]
    power: float


@dataclass
class RenderingState:
    """Canonical representation of rendering quality settings."""
    mesh_density: float
    shadows: bool
    transparency_cut: float


@dataclass
class GlobalViewState:
    """Aggregates all three physical-state components.

    Stored in ``scenes.meta`` as serialised JSON so any backend can reconstruct
    the Stage from the database without knowledge of the originating renderer.
    """
    environment: EnvironmentState
    lighting: LightingState
    rendering: RenderingState

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "environment": {
                "bg_color": list(self.environment.bg_color),
                "fog": self.environment.fog,
            },
            "lighting": {
                "model": self.lighting.model,
                "ambient": self.lighting.ambient,
                "diffuse": self.lighting.diffuse,
                "specular": self.lighting.specular,
                "light_vector": list(self.lighting.light_vector),
                "power": self.lighting.power,
            },
            "rendering": {
                "mesh_density": self.rendering.mesh_density,
                "shadows": self.rendering.shadows,
                "transparency_cut": self.rendering.transparency_cut,
            },
        }

