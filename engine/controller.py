"""Internal engine service — SQL persistence.

Owned entirely by the engine. No backend ever subclasses this directly.
All methods are private by convention (_store_*, _load_*, _list_*) and
are only called through BackendController's public facade.
"""

import os
import sqlite3
from pathlib import Path

from .models import SceneObject, SceneRecord

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "db" / "scenography.db"

def _resolve_db_path() -> Path:
    """Return DB path: env var SCENOGRAPHY_DB_PATH if set, else repo default."""
    env = os.environ.get("SCENOGRAPHY_DB_PATH", "").strip()
    return Path(env) if env else _DEFAULT_DB_PATH

DB_PATH = _resolve_db_path()


class DBController:
    """Concrete SQL persistence service. Not abstract — no implementation required."""

    def __init__(self, path: Path = None):
        self.path = path or DB_PATH
        self.conn = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self):
        """Open a connection to the sqlite database."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_schema(self):
        """Create renderer-agnostic tables."""
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenes (
                id      INTEGER PRIMARY KEY,
                name    TEXT,
                meta    TEXT,
                view    TEXT,
                size    TEXT,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scene_objects (
                id        INTEGER PRIMARY KEY,
                scene_id  INTEGER REFERENCES scenes(id),
                name      TEXT,
                base_type TEXT,
                payload   TEXT
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Write — private engine internals, called only by ingest_scene
    # ------------------------------------------------------------------

    def _store_scene(self, name: str, meta: str, view: str, size: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO scenes(name,meta,view,size) VALUES(?,?,?,?)",
            (name, meta, view, size),
        )
        self.conn.commit()
        return cursor.lastrowid

    def _store_scene_object(
        self,
        scene_id: int,
        name: str,
        base_type: str,
        payload: str,
    ) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO scene_objects(scene_id,name,base_type,payload)"
            " VALUES(?,?,?,?)",
            (scene_id, name, base_type, payload),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # Read — private engine internals
    # ------------------------------------------------------------------

    def _list_scenes(self) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id,name,created FROM scenes ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def _load_scene(self, scene_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scenes WHERE id=?", (scene_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _load_scene_objects(self, scene_id: int) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scene_objects WHERE scene_id=? ORDER BY id",
            (scene_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Scene management — not yet implemented
    # ------------------------------------------------------------------

    def scene_exists(self, name: str) -> bool:
        """Return True if a scene with *name* is already stored."""
        raise NotImplementedError

    def get_scene_by_name(self, name: str) -> dict | None:
        """Return the scene row for *name*, or None."""
        raise NotImplementedError

    def upsert_scene(
        self, record: SceneRecord, objects: list[SceneObject]
    ) -> int:
        """Re-ingest if name exists (delete + re-insert), else insert."""
        raise NotImplementedError

    def delete_scene(self, scene_id: int) -> None:
        """Remove scene row and all its scene_objects."""
        raise NotImplementedError

    def rename_scene(self, scene_id: int, new_name: str) -> None:
        """Rename a stored scene."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Ingest — wires capture_scene output → SQL
    # ------------------------------------------------------------------

    def ingest_scene(self, record: SceneRecord, objects: list[SceneObject]) -> int:
        """Persist a fully-mapped scene. Called automatically after capture_scene."""
        scene_id = self._store_scene(record.name, record.meta, record.view, record.size)
        for obj in objects:
            self._store_scene_object(scene_id, obj.name, obj.base_type, obj.payload)
        return scene_id

    # ------------------------------------------------------------------
    # Model builders — helpers for backends building capture output
    # ------------------------------------------------------------------

    @staticmethod
    def make_scene_record(name: str, meta: str, view: str, size: str) -> SceneRecord:
        """Construct a SceneRecord for persistence."""
        return SceneRecord(id=0, name=name, meta=meta, view=view, size=size, created="")

    @staticmethod
    def make_scene_object(name: str, base_type: str, payload: str) -> SceneObject:
        """Construct a SceneObject for persistence."""
        return SceneObject(
            id=0, scene_id=0, name=name, base_type=base_type, payload=payload
        )
