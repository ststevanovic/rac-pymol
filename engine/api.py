"""Engine API — the single import surface for all backends.

Backends import ONLY from this module.

Usage in a backend
------------------
    from engine.api import BackendController

    class PyMOLController(BackendController):

        # --- molecular classification (one per slot) ---
        def is_macromolecular(self, name, data): ...
        def is_organic(self, name, data): ...
        def is_inorganic(self, name, data): ...
        def is_special(self, name, data): ...
        def is_chains(self, name, data): ...

        # --- scene capture ---
        def capture_scene(self, source, name=None):
            record = self.make_scene_record(name=name, meta=..., view=..., size=...)
            objects = [self.make_scene_object(name=n, base_type=self.classify_object(n, d), payload=...) ...]
            return record, objects
"""

from abc import abstractmethod
from typing import List, Tuple

from .controller import DBController
from .models import *  # noqa: F401, F403  — uniform re-export, never change this line
from .models import BaseType, SceneObject, SceneRecord

__all__ = ["BackendController", "BaseType", "SceneRecord", "SceneObject"]


# ---------------------------------------------------------------------------
# Scope 1: Molecular classification
# Abstract slots per BaseType — backend provides tool-native implementation.
# Engine wires them to BaseType constants; backend never references BaseType.
# ---------------------------------------------------------------------------

class MolecularClassifier:
    """Abstract molecular classification interface.

    One abstract method per BaseType slot. Implement each using
    the backend tool's native chemistry detection (selectors, heuristics).
    Priority order is enforced by classify_object().
    """

    @abstractmethod
    def is_chains(self, name: str, data: dict) -> bool:
        """Selection or chain-group pseudo-object (no atoms)."""
        raise NotImplementedError

    @abstractmethod
    def is_special(self, name: str, data: dict) -> bool:
        """Solvent, ions, pseudo-atoms, CGO axes."""
        raise NotImplementedError

    @abstractmethod
    def is_macromolecular(self, name: str, data: dict) -> bool:
        """Protein or nucleic acid chain."""
        raise NotImplementedError

    @abstractmethod
    def is_organic(self, name: str, data: dict) -> bool:
        """Small molecule / ligand."""
        raise NotImplementedError

    @abstractmethod
    def is_inorganic(self, name: str, data: dict) -> bool:
        """Metal cluster, crystal packing, unclassified solid."""
        raise NotImplementedError

    def classify_object(self, name: str, data: dict) -> str:
        """Return the BaseType string for an object (priority order).
        Concrete — do not override in backends.
        """
        if self.is_chains(name, data):       return BaseType.CHAINS
        if self.is_special(name, data):      return BaseType.SPECIAL
        if self.is_macromolecular(name, data): return BaseType.MACROMOLECULAR
        if self.is_organic(name, data):      return BaseType.ORGANIC
        if self.is_inorganic(name, data):    return BaseType.INORGANIC
        return BaseType.SPECIAL


# ---------------------------------------------------------------------------
# Scope 2: Scene persistence interface
# Helpers to build typed models + abstract capture_scene contract.
# Engine wires capture_scene → ingest_scene → SQL automatically.
# ---------------------------------------------------------------------------

class SceneBackend:
    """Pure abstract contract: backend must implement capture_scene.

    make_scene_record / make_scene_object / ingest_scene live on DBController.
    """

    @abstractmethod
    def capture_scene(self, source, name: str = None) -> Tuple[SceneRecord, List[SceneObject]]:
        """Capture backend state → (SceneRecord, List[SceneObject]).

        source : filepath, None for live session, or any backend input
        name   : scene label to store

        Use self.make_scene_record(), self.make_scene_object(), self.classify_object().
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Combined: BackendController
# Single class backends subclass. Inherits SQL storage, molecular
# classification interface, and scene persistence interface.
# ---------------------------------------------------------------------------

class BackendController(MolecularClassifier, SceneBackend):
    """The only class backends need to subclass.

    Aggregates DBController.
    Inherits abstract contracts from MolecularClassifier and SceneBackend.

    Public surface exposed to callers:
      ingest_scene()       — capture + persist
      list_scenes()        — enumerate stored scenes
      load_scene()         — fetch one scene record by id
      load_scene_objects() — fetch objects for a scene id
    """

    def __init__(self, path=None):
        self._db = DBController(path=path)

    def ingest_scene(self, source=None, name: str = None) -> int:
        """Capture and persist. Do not override in backends."""
        record, objects = self.capture_scene(source, name)
        return self._db.ingest_scene(record, objects)

    def make_scene_record(self, name: str, meta: str, view: str, size: str) -> SceneRecord:
        return self._db.make_scene_record(name, meta, view, size)

    def make_scene_object(self, name: str, base_type: str, payload: str) -> SceneObject:
        return self._db.make_scene_object(name, base_type, payload)

    def list_scenes(self):
        return self._db._list_scenes()

    def load_scene(self, scene_id: int):
        return self._db._load_scene(scene_id)

    def load_scene_objects(self, scene_id: int):
        return self._db._load_scene_objects(scene_id)


