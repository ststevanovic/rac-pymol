"""Internal engine service — SQL persistence.

Owned entirely by the engine. No backend ever subclasses this directly.
All methods are private by convention (_store_*, _load_*, _list_*) and
are only called through BackendController's public facade.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SceneObject, SceneRecord

DB_PATH = Path(__file__).parent.parent / "db" / "scenography.db"


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

    def _list_scenes(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id,name,created FROM scenes ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def _load_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scenes WHERE id=?", (scene_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _load_scene_objects(self, scene_id: int) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scene_objects WHERE scene_id=? ORDER BY id",
            (scene_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Ingest — wires capture_scene output → SQL
    # ------------------------------------------------------------------

    def ingest_scene(self, record: SceneRecord, objects: List[SceneObject]) -> int:
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
