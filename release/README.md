# Release helper notes for RaC-pymol

This document describes the lightweight release process used by the project.
It is intentionally simple because the codebase is small and only a handful of
maintainers are involved.

## CI expectations

* The continuous integration pipeline should run all unit tests, including any
	checks against scenography database `sce.db`.  

TODO: A small script (see `tests/test_db_versioning.py`)
	can be extended to verify the schema when data changes. 

* When a release branch includes updates to the database schema or new scene
	data, the CI should validate that the schema migration is applied correctly
	and that no older commits break existing scenes.

## Publishing a release

1. Bump the version in the code (e.g. by running
	``python -m release.prepare``) and update `HISTORY.md` with a one- or
	two‑line entry describing the change.  ``prepare.py`` will also stage and
	commit the modified files and create a lightweight git tag.
2. Commit the changes and open a pull request; the CI must pass before merging.
3. After merge, push the branch and tags.  You can use
	``python -m release.push`` to send both the commit and its tags to the
	remote and, if you have the GitHub CLI installed, create a release
	automatically (it will add the `HISTORY.md` entry as the notes).

No special tooling is required; maintainers may script these steps later if
they become tedious.