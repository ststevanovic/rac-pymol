"""Tests for the engine API and controller."""


def test_save_list_load(tmp_path):
    """BackendController list_scenes / load_scene round-trip via DBController."""
    from engine.controller import DBController

    db = DBController(path=tmp_path / "scenography.db")
    db.connect()
    db.init_schema()

    record = db.make_scene_record("test1", meta="{}", view="[]", size="[]")
    sid = db.ingest_scene(record, [])
    assert sid == 1

    scenes = db._list_scenes()
    assert scenes[0]["name"] == "test1"

    loaded = db._load_scene(sid)
    assert loaded is not None
    assert loaded["name"] == "test1"

    db.close()
