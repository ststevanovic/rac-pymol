"""PyMOL-specific implementation of AbstractViewCommons.

This module is responsible for **recreating** the canonical GlobalViewState
from the raw ``global_settings`` dict that PyMOL exports (the endpoint output
in ``tests/data/visual_system_state.json``), and for **applying** that state
back to a live PyMOL session.

Mapping (PyMOL raw key → physical state field)
----------------------------------------------
bg_rgb                   → environment.bg_color
fog / fog_start / fog_end → environment.fog
ambient                  → lighting.ambient
direct                   → lighting.diffuse
reflect                  → lighting.specular
light                    → lighting.light_vector
power                    → lighting.power
ray_shadow               → rendering.shadows
min_mesh_spacing         → rendering.mesh_density
ray_transparency_spec_cut → rendering.transparency_cut

Usage
-----
::

    import json
    from engine.pymol_integration import PyMOLViewCommons

    with open("visual_system_state.json") as f:
        doc = json.load(f)

    view = PyMOLViewCommons.from_global_settings(doc["global_settings"])
    state_dict = view.to_dict()   # store in DB
    view.apply()                  # push back to live PyMOL (optional)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from engine.models import (
    AbstractViewCommons,
    EnvironmentState,
    GlobalViewState,
    LightingState,
    RenderingState,
)

# ---------------------------------------------------------------------------
# Named-colour table (subset used by PyMOL backgrounds)
# ---------------------------------------------------------------------------

_PYMOL_NAMED_COLORS: Dict[str, Tuple[float, float, float]] = {
    "black":      (0.000, 0.000, 0.000),
    "white":      (1.000, 1.000, 1.000),
    "grey":       (0.500, 0.500, 0.500),
    "gray":       (0.500, 0.500, 0.500),
    "light_grey": (0.827, 0.827, 0.827),
    "light_gray": (0.827, 0.827, 0.827),
    "dark_grey":  (0.200, 0.200, 0.200),
    "dark_gray":  (0.200, 0.200, 0.200),
    "blue":       (0.000, 0.000, 1.000),
    "red":        (1.000, 0.000, 0.000),
    "green":      (0.000, 1.000, 0.000),
    "yellow":     (1.000, 1.000, 0.000),
    "cyan":       (0.000, 1.000, 1.000),
    "magenta":    (1.000, 0.000, 1.000),
}

# Default field-of-view used by PyMOL (no direct setting equivalent)
_DEFAULT_FOV = 20.0
# PyMOL does not expose an antialiasing level setting in the same way
_DEFAULT_AA = 1

# ---------------------------------------------------------------------------
# Private parsing helpers
# ---------------------------------------------------------------------------


def _parse_float(value: object, default: float = 0.0) -> float:
    """Coerce a string or numeric setting to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: object, default: bool = False) -> bool:
    """Coerce a PyMOL on/off string or numeric value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    return s in {"1", "on", "true", "yes"}


def _parse_rgb_string(raw: str) -> Optional[Tuple[float, float, float]]:
    """Parse a PyMOL vector string such as ``'[ -0.4, -0.4, -1.0 ]'``.

    Returns a 3-tuple of floats or *None* if parsing fails.
    """
    numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", raw)
    if len(numbers) >= 3:
        return (float(numbers[0]), float(numbers[1]), float(numbers[2]))
    return None


def _resolve_bg_color(
    raw: str,
) -> Tuple[float, float, float]:
    """Convert a PyMOL bg_rgb value to an RGB float tuple.

    Handles:
    - Named colours (e.g. ``'light_grey'``)
    - Vector strings (e.g. ``'[ 0.8, 0.8, 0.8 ]'``)
    - Plain numeric string (treated as greyscale intensity)
    """
    raw = str(raw).strip()

    # Named colour lookup
    if raw in _PYMOL_NAMED_COLORS:
        return _PYMOL_NAMED_COLORS[raw]

    # Vector / list notation
    if "[" in raw or "," in raw:
        result = _parse_rgb_string(raw)
        if result is not None:
            return result

    # Single float → greyscale
    try:
        v = float(raw)
        return (v, v, v)
    except ValueError:
        pass

    # Fallback: light grey (PyMOL default)
    return _PYMOL_NAMED_COLORS["light_grey"]


def _parse_light_vector(
    raw: str,
) -> Tuple[float, float, float]:
    """Parse a PyMOL ``light`` setting into a float 3-tuple."""
    result = _parse_rgb_string(str(raw))
    if result is not None:
        return result
    return (-0.4, -0.4, -1.0)  # PyMOL default


# ---------------------------------------------------------------------------
# Public integration class
# ---------------------------------------------------------------------------


class PyMOLViewCommons(AbstractViewCommons):
    """Concrete AbstractViewCommons for PyMOL.

    Wraps a :class:`~engine.models.GlobalViewState` and provides:

    * :meth:`from_global_settings` – factory that builds an instance from the
      raw ``global_settings`` dict exported by ``scene.export_visual_system_state``.
    * :meth:`apply` – pushes the physical state back to the live PyMOL session
      via ``pymol.cmd.set``.
    * :meth:`to_dict` – returns the canonical ``GlobalViewState`` as a
      JSON-serialisable dict for database storage.
    """

    def __init__(self, global_state: GlobalViewState) -> None:
        self._state = global_state

        # --- Populate AbstractViewCommons fields from the physical state ---
        env = global_state.environment
        lit = global_state.lighting
        ren = global_state.rendering

        self.background_rgb: Tuple[float, float, float] = env.bg_color
        self.projection_mode: str = "perspective"  # PyMOL default
        self.field_of_view: float = _DEFAULT_FOV

        fog = env.fog
        self.depth_cue_enabled: bool = bool(fog.get("enabled", False))
        self.depth_cue_params: Dict = {
            "start":   fog.get("start", 0.45),
            "end":     fog.get("end", 1.0),
            "density": fog.get("density", 1.0),
        }

        self.lights: List[Dict] = [
            {
                "vector":    lit.light_vector,
                "intensity": lit.diffuse,
                "type":      "key",
            }
        ]
        self.ambient_occlusion: bool = False  # PyMOL does not support AO

        self.shadow_style: str = "hard" if ren.shadows else "none"
        self.antialiasing_level: int = _DEFAULT_AA

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_global_settings(
        cls,
        settings: Dict,
    ) -> "PyMOLViewCommons":
        """Build a :class:`PyMOLViewCommons` from the raw PyMOL export dict.

        Parameters
        ----------
        settings:
            The ``global_settings`` sub-dict from a
            ``visual_system_state.json`` export.

        Returns
        -------
        PyMOLViewCommons
            Instance whose physical state reflects the provided settings.
        """
        # --- Environment ---
        bg_color = _resolve_bg_color(settings.get("bg_rgb", "light_grey"))

        fog_enabled = _parse_bool(settings.get("depth_cue", False))
        fog_start   = _parse_float(settings.get("fog_start", 0.45))
        fog_end     = _parse_float(settings.get("fog_end", 1.0))
        fog_density = _parse_float(settings.get("fog", 1.0))

        environment = EnvironmentState(
            bg_color=bg_color,
            fog={
                "enabled": fog_enabled,
                "start":   fog_start,
                "end":     fog_end,
                "density": fog_density,
            },
        )

        # --- Lighting ---
        ambient   = _parse_float(settings.get("ambient",  0.40))
        diffuse   = _parse_float(settings.get("direct",   0.45))
        specular  = _parse_float(settings.get("reflect",  0.45))
        power     = _parse_float(settings.get("power",    1.0))
        lv_raw    = settings.get("light", "[ -0.4, -0.4, -1.0 ]")
        light_vec = _parse_light_vector(str(lv_raw))

        lighting = LightingState(
            model="standard_three_point",
            ambient=ambient,
            diffuse=diffuse,
            specular=specular,
            light_vector=light_vec,
            power=power,
        )

        # --- Rendering ---
        mesh_density     = _parse_float(
            settings.get("min_mesh_spacing", 0.6), default=0.6
        )
        shadows          = _parse_bool(settings.get("ray_shadow", False))
        transparency_cut = _parse_float(
            settings.get("ray_transparency_spec_cut", 0.9), default=0.9
        )

        rendering = RenderingState(
            mesh_density=mesh_density,
            shadows=shadows,
            transparency_cut=transparency_cut,
        )

        state = GlobalViewState(
            environment=environment,
            lighting=lighting,
            rendering=rendering,
        )
        return cls(state)

    # ------------------------------------------------------------------
    # AbstractViewCommons interface
    # ------------------------------------------------------------------

    def apply(self) -> None:
        """Apply the physical state to the live PyMOL session.

        Translates each canonical field back to the corresponding PyMOL
        ``cmd.set`` call.  Requires PyMOL to be importable.

        Raises
        ------
        RuntimeError
            If PyMOL is not available in the current environment.
        """
        try:
            from pymol import cmd  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "PyMOL is not available; cannot apply view state."
            ) from exc

        self._apply_environment(cmd)
        self._apply_lighting(cmd)
        self._apply_rendering(cmd)

    def _apply_environment(self, cmd) -> None:  # type: ignore[no-untyped-def]
        """Push environment settings (background, fog) to PyMOL."""
        env = self._state.environment

        r, g, b = env.bg_color
        try:
            cmd.bg_color(f"[{r:.4f},{g:.4f},{b:.4f}]")
        except Exception:
            cmd.set("bg_rgb", f"[{r:.4f},{g:.4f},{b:.4f}]")

        fog = env.fog
        cmd.set("depth_cue",  int(bool(fog.get("enabled", False))))
        cmd.set("fog_start",  fog.get("start",   0.45))
        cmd.set("fog",        fog.get("density", 1.0))

    def _apply_lighting(self, cmd) -> None:  # type: ignore[no-untyped-def]
        """Push lighting settings to PyMOL."""
        lit = self._state.lighting

        cmd.set("ambient",  lit.ambient)
        cmd.set("direct",   lit.diffuse)
        cmd.set("reflect",  lit.specular)
        cmd.set("power",    lit.power)
        lx, ly, lz = lit.light_vector
        cmd.set("light", f"[{lx:.5f},{ly:.5f},{lz:.5f}]")

    def _apply_rendering(self, cmd) -> None:  # type: ignore[no-untyped-def]
        """Push rendering quality settings to PyMOL."""
        ren = self._state.rendering

        cmd.set("min_mesh_spacing",          ren.mesh_density)
        cmd.set("ray_shadow",                int(ren.shadows))
        cmd.set("ray_transparency_spec_cut", ren.transparency_cut)

    # ------------------------------------------------------------------
    # Serialisation helper
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return the canonical physical state as a JSON-serialisable dict."""
        return self._state.to_dict()
