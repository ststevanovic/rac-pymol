"""Tests for engine.models global-view types and engine.pymol_integration."""
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
from engine.pymol_integration import (
    PyMOLViewCommons,
    _parse_bool,
    _parse_float,
    _parse_light_vector,
    _resolve_bg_color,
)

# Path to sample endpoint output
_SAMPLE = Path(__file__).parent / "data" / "visual_system_state.json"


# ---------------------------------------------------------------------------
# Helpers / parsing tests
# ---------------------------------------------------------------------------

def test_parse_float_string():
    assert _parse_float("0.60000") == pytest.approx(0.6)


def test_parse_float_invalid_uses_default():
    assert _parse_float("not_a_number", default=1.5) == pytest.approx(1.5)


def test_parse_bool_on_off():
    assert _parse_bool("on") is True
    assert _parse_bool("off") is False


def test_parse_bool_numeric():
    assert _parse_bool(1) is True
    assert _parse_bool(0) is False


def test_resolve_bg_color_named():
    rgb = _resolve_bg_color("light_grey")
    assert len(rgb) == 3
    assert rgb == pytest.approx((0.827, 0.827, 0.827), abs=1e-3)


def test_resolve_bg_color_vector_string():
    rgb = _resolve_bg_color("[ 0.1, 0.2, 0.3 ]")
    assert rgb == pytest.approx((0.1, 0.2, 0.3))


def test_resolve_bg_color_unknown_falls_back():
    rgb = _resolve_bg_color("totally_unknown_color")
    assert len(rgb) == 3  # should return a valid tuple


def test_parse_light_vector():
    vec = _parse_light_vector("[ -0.40000, -0.40000, -1.00000 ]")
    assert vec == pytest.approx((-0.4, -0.4, -1.0))


def test_parse_light_vector_fallback():
    vec = _parse_light_vector("bad input")
    assert len(vec) == 3  # fallback returns default


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

    assert "environment" in d
    assert "lighting" in d
    assert "rendering" in d

    assert d["environment"]["bg_color"] == pytest.approx(
        [0.827, 0.827, 0.827], abs=1e-3
    )
    assert d["environment"]["fog"]["enabled"] is True
    assert d["lighting"]["ambient"] == pytest.approx(0.40)
    assert d["lighting"]["diffuse"] == pytest.approx(0.45)
    assert d["rendering"]["mesh_density"] == pytest.approx(0.60)
    assert d["rendering"]["shadows"] is False


# ---------------------------------------------------------------------------
# PyMOLViewCommons.from_global_settings — round-trip from sample JSON
# ---------------------------------------------------------------------------

def test_from_global_settings_sample():
    """Parse the real endpoint output and verify canonical fields."""
    assert _SAMPLE.exists(), "sample scene JSON must exist"
    with open(_SAMPLE) as f:
        doc = json.load(f)

    gs = doc["global_settings"]
    view = PyMOLViewCommons.from_global_settings(gs)

    # AbstractViewCommons fields are populated
    assert len(view.background_rgb) == 3
    assert view.projection_mode == "perspective"
    assert view.field_of_view > 0
    assert isinstance(view.depth_cue_enabled, bool)
    assert isinstance(view.depth_cue_params, dict)
    assert isinstance(view.lights, list) and len(view.lights) > 0
    assert view.ambient_occlusion is False  # PyMOL does not support AO
    assert view.shadow_style in {"none", "hard", "soft"}
    assert isinstance(view.antialiasing_level, int)


def test_from_global_settings_lighting_values():
    """Lighting values are parsed from the sample settings."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]

    view = PyMOLViewCommons.from_global_settings(gs)
    state = view.to_dict()

    assert state["lighting"]["ambient"] == pytest.approx(0.40, abs=0.01)
    assert state["lighting"]["diffuse"] == pytest.approx(0.45, abs=0.01)
    assert state["lighting"]["specular"] == pytest.approx(0.45, abs=0.01)
    assert state["lighting"]["power"] == pytest.approx(1.0, abs=0.01)
    lv = state["lighting"]["light_vector"]
    assert lv == pytest.approx([-0.4, -0.4, -1.0], abs=0.01)


def test_from_global_settings_rendering_values():
    """Rendering values are parsed from the sample settings."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]

    view = PyMOLViewCommons.from_global_settings(gs)
    state = view.to_dict()

    assert state["rendering"]["mesh_density"] == pytest.approx(0.60, abs=0.01)
    assert state["rendering"]["transparency_cut"] == pytest.approx(0.90, abs=0.01)


def test_from_global_settings_bg_color_light_grey():
    """Background colour is correctly resolved from named 'light_grey'."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]

    view = PyMOLViewCommons.from_global_settings(gs)
    state = view.to_dict()

    bg = state["environment"]["bg_color"]
    assert bg == pytest.approx([0.827, 0.827, 0.827], abs=0.01)


def test_to_dict_is_json_serialisable():
    """to_dict output can be round-tripped through json.dumps / json.loads."""
    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]

    view = PyMOLViewCommons.from_global_settings(gs)
    d = view.to_dict()
    serialised = json.dumps(d)
    recovered = json.loads(serialised)
    assert recovered["environment"]["bg_color"] is not None
    assert recovered["lighting"]["model"] == "standard_three_point"


def test_apply_raises_without_pymol(monkeypatch):
    """apply() raises RuntimeError when PyMOL is not available."""
    import sys

    with open(_SAMPLE) as f:
        gs = json.load(f)["global_settings"]

    view = PyMOLViewCommons.from_global_settings(gs)

    # Block the 'pymol' import inside apply() by inserting a sentinel None
    # (Python treats a None entry in sys.modules as "not found / blocked").
    monkeypatch.setitem(sys.modules, "pymol", None)  # type: ignore[arg-type]
    with pytest.raises((RuntimeError, ImportError)):
        view.apply()
