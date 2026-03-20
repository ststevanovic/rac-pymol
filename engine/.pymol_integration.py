"""PyMOL ↔ engine.models bidirectional formatter.

pymol_to_abc(settings) -> GlobalViewState   (PyMOL global_settings → ABC types)
abc_to_pymol(state)    -> dict              (ABC types → PyMOL global_settings)
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from engine.models import (
    EnvironmentState,
    GlobalViewState,
    LightingState,
    RenderingState,
)


def pymol_to_abc(settings: Dict) -> GlobalViewState:
    """Convert a PyMOL global_settings dict to GlobalViewState."""
    return GlobalViewState(
        environment=EnvironmentState(
            bg_color=_parse_color(str(settings.get("bg_rgb", ""))),
            fog={
                "enabled": _as_bool(settings.get("depth_cue", False)),
                "start":   _to_float(settings.get("fog_start", 0.45)),
                "end":     _to_float(settings.get("fog_end",   1.0)),
                "density": _to_float(settings.get("fog",       1.0)),
            },
        ),
        lighting=LightingState(
            model="standard_three_point",
            ambient=_to_float(settings.get("ambient", 0.40)),
            diffuse=_to_float(settings.get("direct",  0.45)),
            specular=_to_float(settings.get("reflect", 0.45)),
            light_vector=_parse_vec3(str(settings.get("light", "[-0.4,-0.4,-1.0]"))),
            power=_to_float(settings.get("power", 1.0)),
        ),
        rendering=RenderingState(
            mesh_density=_to_float(settings.get("min_mesh_spacing", 0.6)),
            shadows=_as_bool(settings.get("ray_shadow", False)),
            transparency_cut=_to_float(settings.get("ray_transparency_spec_cut", 0.9)),
        ),
    )


def abc_to_pymol(state: GlobalViewState) -> Dict:
    """Convert GlobalViewState to a PyMOL global_settings dict."""
    env, lit, ren = state.environment, state.lighting, state.rendering
    r, g, b = env.bg_color
    lx, ly, lz = lit.light_vector
    fog = env.fog
    return {
        "bg_rgb":                    f"[ {r:.5f}, {g:.5f}, {b:.5f} ]",
        "ambient":                   f"{lit.ambient:.5f}",
        "direct":                    f"{lit.diffuse:.5f}",
        "reflect":                   f"{lit.specular:.5f}",
        "light":                     f"[ {lx:.5f}, {ly:.5f}, {lz:.5f} ]",
        "power":                     f"{lit.power:.5f}",
        "depth_cue":                 "on" if fog.get("enabled") else "off",
        "fog_start":                 f"{fog.get('start', 0.45):.5f}",
        "fog":                       f"{fog.get('density', 1.0):.5f}",
        "min_mesh_spacing":          f"{ren.mesh_density:.5f}",
        "ray_shadow":                "on" if ren.shadows else "off",
        "ray_transparency_spec_cut": f"{ren.transparency_cut:.5f}",
    }


def _parse_color(raw: str) -> Tuple[float, float, float]:
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", raw)
    if len(nums) >= 3:
        return (float(nums[0]), float(nums[1]), float(nums[2]))
    try:
        from pymol import cmd  # type: ignore[import]
        t = cmd.get_color_tuple(raw.strip())
        if t:
            return t
    except Exception:
        pass
    try:
        v = float(raw)
        return (v, v, v)
    except (ValueError, TypeError):
        return (0.827, 0.827, 0.827)  # PyMOL light_grey default


def _parse_vec3(raw: str) -> Tuple[float, float, float]:
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", raw)
    if len(nums) >= 3:
        return (float(nums[0]), float(nums[1]), float(nums[2]))
    return (-0.4, -0.4, -1.0)  # PyMOL default light direction


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "on", "true", "yes"}
