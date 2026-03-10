"""Unit tests for the release helpers."""



from release import shared


def test_version_bump(tmp_path, monkeypatch):
    # copy a minimal pyproject.toml into the tempdir
    proj = tmp_path / "pyproject.toml"
    proj.write_text("""[project]
name = "foo"
version = "0.1.0"
"""
                   )
    monkeypatch.setattr(shared, "PYPROJECT", proj)

    assert shared.get_version() == "0.1.0"
    new = shared.bump_version("minor")
    assert new == "0.2.0"
    assert shared.get_version() == "0.2.0"


def test_history_append(tmp_path, monkeypatch):
    hist = tmp_path / "HISTORY.md"
    monkeypatch.setattr(shared, "HISTORY", hist)
    shared.append_history("test entry")
    contents = hist.read_text(encoding="utf-8")
    assert "test entry" in contents
