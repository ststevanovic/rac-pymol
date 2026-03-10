"""Tests for the engine API and controller."""



def test_save_list_load(tmp_path):
    """DBController.save_scene / list_scenes / load_scene round-trip."""
    from pymol.controller import PyMOLController

    ctrl = PyMOLController(path=tmp_path / "scenography.db")
    ctrl.connect()
    ctrl.init_schema()

    sid = ctrl.save_scene("test1", meta="{}", view="[]", size="[]")
    assert sid == 1

    scenes = ctrl.list_scenes()
    assert scenes[0]["name"] == "test1"

    record = ctrl.load_scene(sid)
    assert record is not None
    assert record["name"] == "test1"

    ctrl.close()
