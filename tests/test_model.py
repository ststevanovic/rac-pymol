"""Tests for engine/models.py global-view types and engine/.pymol_integration."""
import importlib.util
import json
from pathlib import Path

import pytest

from engine.models import (
    AbstractViewCommons,
    EnvironmentState,
    GlobalViewState,
    LightingState,
    RenderingState,
)

# Load the dot-prefixed formatter module via importlib
_INTEGRATION_PATH = Path(__file__).parent.parent / "engine" / ".pymol_integration.py"
assert _INTEGRATION_PATH.exists(), f"formatter not found: {_INTEGRATION_PATH}"
_spec = importlib.util.spec_from_file_location("_pymol_integration", _INTEGRATION_PATH)
assert _spec is not None, "importlib failed to build spec"
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

pymol_to_abc = _mod.pymol_to_abc
abc_to_pymol = _mod.abc_to_pymol
_parse_color = _mod._parse_color
_parse_vec3  = _mod._parse_vec3
_to_float    = _mod._to_float
_as_bool     = _mod._as_bool

_SAMPLE = Path(__file__).parent / "data" / "visual_system_state.json"


# ---------------------------------------------------------------------------
# Helper / parser tests
# ---------------------------------------------------------------------------

def test_to_float_string():
    assert _to_float("0.60000") == pytest.approx(0.6)


def test_to_float_invalid_uses_default():
    assert _to_float("not_a_number", default=1.5) == pytest.approx(1.5)


def test_as_bool_on_off():
    assert _as_bool("on") is True
    assert _as_bool("off") is False


def test_as_bool_numeric():
    assert _as_bool(1) is True
    assert _as_bool(0) is False


def test_parse_color_vector_string():
    assert _parse_color("[ 0.1, 0.2, 0.3 ]") == pytest.approx((0.1, 0.2, 0.3))


def test_parse_color_unknown_returns_tuple():
    rgb = _parse_color("totally_unknown_color")
    assert len(rgb) == 3


def test_parse_vec3():
    assert _parse_vec3("[ -0.40000, -0.40000, -1.00000 ]") == pytest.approx(
        (-0.4, -0.4, -1.0)
    )


def test_parse_vec3_fallback():
    assert len(_parse_vec3("bad input")) == 3


# ---------------------------------------------------------------------------
# AbstractViewCommons is abstract
# ---------------------------------------------------------------------------

def test_abstract_view_commons_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractViewCommons()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# GlobalViewState.to_dict
# ---------------------------------------------------------------------------

def test_global_view_state_to_dict_structure():
    state = GlobalViewState(
        environment=EnvironmentState(
            bg_color=(0.827, 0.827, 0.827),
            fog={"enabled": True, "start": 0.2, "end": 0.8},
        ),
        lighting=LightingState(
            model="standard_three_point",
            ambient=0.40,
            diffuse=0.45,
            specular=0.45,
            light_vector=(-0.4, -0.4, -1.0),
            power=1.0,
        ),
        rendering=RenderingState(
            mesh_density=0.60,
            shadows=False,
            transparency_cut=0.90,
        ),
    )
    d = state.to_dict()
    assert set(d) == {"environment", "lighting", "rendering"}
    assert d["environment"]["fog"]["enabled"] is True
    assert d["lighting"]["ambient"] == pytest.approx(0.40)
    assert d["rendering"]["mesh_density"] == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# B→A: pymol_to_abc from the sample endpoint output
# ---------------------------------------------------------------------------

def test_pymol_to_abc_lighting_values():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    state = pymol_to_abc(gs)
    assert state.lighting.ambient   == pytest.approx(0.40, abs=0.01)
    assert state.lighting.diffuse   == pytest.approx(0.45, abs=0.01)
    assert state.lighting.specular  == pytest.approx(0.45, abs=0.01)
    assert state.lighting.power     == pytest.approx(1.0,  abs=0.01)
    assert state.lighting.light_vector == pytest.approx((-0.4, -0.4, -1.0), abs=0.01)


def test_pymol_to_abc_rendering_values():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    state = pymol_to_abc(gs)
    assert state.rendering.mesh_density     == pytest.approx(0.60, abs=0.01)
    assert state.rendering.transparency_cut == pytest.approx(0.90, abs=0.01)
    assert state.rendering.shadows is False


def test_pymol_to_abc_bg_color():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    state = pymol_to_abc(gs)
    assert len(state.environment.bg_color) == 3
    # light_grey resolves to ~(0.827, 0.827, 0.827) via PyMOL cmd
    assert all(0.0 <= c <= 1.0 for c in state.environment.bg_color)


# ---------------------------------------------------------------------------
# A→B: abc_to_pymol output format matches visual_system_state.json keys
# ---------------------------------------------------------------------------

def test_abc_to_pymol_keys():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    state = pymol_to_abc(gs)
    out = abc_to_pymol(state)
    for key in ("bg_rgb", "ambient", "direct", "reflect", "light", "power",
                "min_mesh_spacing", "ray_transparency_spec_cut"):
        assert key in out, f"Missing key: {key}"


def test_abc_to_pymol_string_values():
    """All output values must be strings in PyMOL format."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    out = abc_to_pymol(pymol_to_abc(gs))
    for k, v in out.items():
        assert isinstance(v, str), f"{k}: expected str, got {type(v)}"


def test_abc_to_pymol_numeric_format():
    """Numeric fields use 5 decimal places."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    out = abc_to_pymol(pymol_to_abc(gs))
    assert out["ambient"] == "0.40000"
    assert out["direct"]  == "0.45000"
    assert out["power"]   == "1.00000"
    assert out["min_mesh_spacing"] == "0.60000"
    assert out["ray_transparency_spec_cut"] == "0.90000"


def test_abc_to_pymol_light_vector_format():
    """Light vector uses '[ x, y, z ]' format."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    out = abc_to_pymol(pymol_to_abc(gs))
    assert out["light"] == "[ -0.40000, -0.40000, -1.00000 ]"


# ---------------------------------------------------------------------------
# Round-trip: pymol_to_abc → abc_to_pymol preserves key numeric values
# ---------------------------------------------------------------------------

def test_round_trip_numeric_values():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    out = abc_to_pymol(pymol_to_abc(gs))
    assert float(out["ambient"])  == pytest.approx(0.40, abs=1e-4)
    assert float(out["direct"])   == pytest.approx(0.45, abs=1e-4)
    assert float(out["reflect"])  == pytest.approx(0.45, abs=1e-4)
    assert float(out["min_mesh_spacing"]) == pytest.approx(0.60, abs=1e-4)


def test_round_trip_is_json_serialisable():
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]
    out = abc_to_pymol(pymol_to_abc(gs))
    recovered = json.loads(json.dumps(out))
    assert recovered["ambient"] == "0.40000"

