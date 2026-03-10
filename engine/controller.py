"""Abstract database controller for scenography and versioning.

This module defines the renderer-agnostic interface only.  No backend-specific
knowledge (e.g. JSON structure, object types) belongs here.

Each rendering backend (PyMOL, Blender, etc.) must subclass ``DBController``
and implement the abstract methods.
"""

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent.parent / "db" / "scenography.db"


class DBController(ABC):
    """Abstract base — backend implementations must subclass this."""

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
        """Create renderer-agnostic tables.  Backends may extend this."""
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
    # Generic scene persistence (renderer-agnostic)
    # ------------------------------------------------------------------

    def save_scene(self, name: str, meta: str, view: str, size: str) -> int:
        """Persist the decomposed scene record.  Returns new scene id.

        Parameters
        ----------
        name : str
            Human-readable scene label.
        meta : str
            Opaque serialised global settings (backend-specific encoding).
        view : str
            Opaque serialised camera / view state.
        size : str
            Opaque serialised viewport / canvas size.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO scenes(name,meta,view,size) VALUES(?,?,?,?)",
            (name, meta, view, size),
        )
        self.conn.commit()
        return cursor.lastrowid

    def store_object(
        self,
        scene_id: int,
        name: str,
        base_type: str,
        payload: str,
    ) -> int:
        """Insert a single typed object into the scene_objects table."""
        cursor = self.conn.cursor()
        cursor.execute(
            (
                "INSERT INTO scene_objects(scene_id,name,"
                "base_type,payload) VALUES(?,?,?,?)"
            ),
            (scene_id, name, base_type, payload),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_scenes(self) -> List[Dict[str, Any]]:
        """Return all stored scenes (id, name, created)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id,name,created FROM scenes ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def load_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """Return the full scene record as a dict, or None if not found."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM scenes WHERE id=?", (scene_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def load_scene_objects(self, scene_id: int) -> List[Dict[str, Any]]:
        """Return all objects belonging to a scene."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scene_objects WHERE scene_id=? ORDER BY id",
            (scene_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Abstract — must be implemented by each backend
    # ------------------------------------------------------------------

    @abstractmethod
    def ingest_scene(self, filepath: str, name: str = None) -> int:
        """Parse a backend-specific scene export file and persist it.

        The implementation is responsible for:
          - reading the file in whatever format the backend produces
          - splitting it into meta / view / size / objects
          - classifying each object into a ``BaseType``
          - calling ``save_scene`` and ``store_object``

        Returns the new scene id.
        """
        raise NotImplementedError
