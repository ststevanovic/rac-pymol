# Rendering as Code with PyMOL

A minimal Python project for "Rendering as Code with PyMOL".

## Architecture

Three layers, strict dependency direction — nothing in `engine/` imports from `pymol/`:

* **`engine/`** — renderer-agnostic ABC (`DBController`), typed models (`BaseType`, `SceneRecord`, `SceneObject`), and a thin singleton API.  Zero PyMOL knowledge.
* **`pymol/`** — first concrete backend.  `PyMOLController` subclasses `DBController`, implements `ingest_scene`, and classifies objects into `BaseType`.  `scene_control.py` and `pymol_hooks.py` are PyMOL-only and untouched by the engine.
* **Scripts** — CLI entry points that call `engine.api` only.  Swapping the backend requires changing one import line in `engine/api.py`.

```mermaid
classDiagram
    namespace engine {
        class DBController {
            <<abstract>>
            +path: Path
            +connect()
            +close()
            +init_schema()
            +save_scene(name, meta, view, size) int
            +store_object(scene_id, name, base_type, payload) int
            +list_scenes() List
            +load_scene(id) dict
            +load_scene_objects(scene_id) List
            +ingest_scene(filepath, name)* int
        }

        class BaseType {
            <<constants>>
            ORGANIC
            INORGANIC
            MACROMOLECULAR
            SPECIAL
            CHAINS
        }

        class SceneRecord {
            id: int
            name: str
            meta: str
            view: str
            size: str
            created: str
        }

        class SceneObject {
            id: int
            scene_id: int
            name: str
            base_type: str
            payload: str
        }

        class API {
            +get_controller(db_path) DBController
            +save_scene(name, meta, view, size) int
            +ingest_scene(filepath, name) int
            +list_scenes() List
            +load_scene(id) dict
            +load_scene_objects(id) List
        }
    }

    namespace pymol_backend {
        class PyMOLController {
            +ingest_scene(filepath, name) int
        }

        class _classify_object {
            <<function>>
            heuristics: representations
            heuristics: atom_colors keys
            heuristics: object name
        }

        class SceneControl {
            +export_visual_system_state(outfile)
            +apply_scene(infile)
        }

        class PyMOLHooks {
            +install_hooks()
        }
    }

    class Scripts {
        save_scene.py
        load_scene.py
        browse_scenes.py
    }

    DBController <|-- PyMOLController : extends
    PyMOLController ..> _classify_object : uses
    PyMOLController ..> BaseType : returns
    API --> DBController : facade
    API ..> PyMOLController : instantiates
    PyMOLHooks --> API : calls
    SceneControl --> API : calls
    Scripts --> API : calls
    SceneObject ..> BaseType : base_type field
```

## Usage

The simplest way to try the project is to start PyMOL (headless) and import the
module; you can then call `pymol.scene_control.export_scene()` and use the CLI
utilities to persist or restore the state.  See individual scripts for example
arguments.

