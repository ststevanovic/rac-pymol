"""Test PyMOL backend ingestion of a visual_system_state export."""
from pathlib import Path
from engine.models import BaseType


def test_ingest(tmp_path):
    """PyMOLController.ingest_scene stores scene + typed objects."""
    # sample file shipped with tests
    src = Path(__file__).parent / "data" / "visual_system_state.json"
    assert src.exists(), "sample scene JSON must exist"

    from pymol_backend.controller import PyMOLController

    ctrl = PyMOLController(path=tmp_path / "scenography.db")
    ctrl.connect()
    ctrl.init_schema()

    sid = ctrl.ingest_scene(str(src), name="example")
    assert sid == 1

    # scene row present
    rows = ctrl.list_scenes()
    assert rows and rows[0]["name"] == "example"

    # at least one object stored
    objs = ctrl.load_scene_objects(sid)
    assert len(objs) > 0

    # every object has a known base_type
    valid_types = {BaseType.ORGANIC, BaseType.INORGANIC,
                   BaseType.MACROMOLECULAR, BaseType.SPECIAL, BaseType.CHAINS}
    for obj in objs:
        assert obj["base_type"] in valid_types, (
            f"Unknown base_type '{obj['base_type']}' for object '{obj['name']}'"
        )

    ctrl.close()
