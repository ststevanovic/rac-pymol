"""Public API layer — backend-agnostic facade over DBController.

The active backend is selected here.  To swap backends, change the import
in ``_make_controller`` only — nothing else in the codebase needs to know.
"""

from pathlib import Path
from typing import Optional

from .controller import DBController

# -- active backend selection ------------------------------------------------
# Only this import needs to change when a new backend is introduced.
from pymol_backend.controller import PyMOLController as _BackendController
# ----------------------------------------------------------------------------

_controller: Optional[DBController] = None


def _make_controller(path: Optional[Path] = None) -> DBController:
    c = _BackendController(path=path) if path else _BackendController()
    c.connect()
    c.init_schema()
    return c


def get_controller(db_path: Optional[Path] = None) -> DBController:
    """Return the shared controller, creating it if none exists.

    ``db_path`` may be supplied during testing to override the default
    location of ``scenography.db``.
    """
    global _controller
    if _controller is None:
        _controller = _make_controller(db_path)
    else:
        if db_path and _controller.path != db_path:
            _controller.close()
            _controller = _make_controller(db_path)
    return _controller


def save_scene(name: str, meta: str, view: str, size: str) -> int:
    return get_controller().save_scene(name, meta, view, size)


def ingest_scene(filepath: str, name: str = None) -> int:
    return get_controller().ingest_scene(filepath, name)


def list_scenes():
    return get_controller().list_scenes()


def load_scene(scene_id: int) -> Optional[dict]:
    return get_controller().load_scene(scene_id)


def load_scene_objects(scene_id: int):
    return get_controller().load_scene_objects(scene_id)
