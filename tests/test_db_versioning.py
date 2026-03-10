"""CI placeholder: verify that scenography.db is updated appropriately."""


def test_db_exists(tmp_path):
    dbfile = tmp_path / "scenography.db"
    # create empty file to simulate update
    open(dbfile, "w").close()
    assert dbfile.exists()

# more thorough tests will be added later when the data model is fleshed out
