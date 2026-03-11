# Rendering as Code with PyMOL

A minimal Python project for "Rendering as Code with PyMOL".

## Architecture

Two layers:

* **`engine`** — renderer-agnostic layer with features:
  - **ABC interfaces**: storage, selector mapping
  - **`Models`**: BaseType constants, dataclasses
  - **`Condenser`**: compression/decompression middleware
  - **API**: thin singleton facade

* **`pymol-backend`** — concrete backend implementing engine ABCs:
  - **PyMOLController**: implements DBController + BaseTypeApi
  - **Classification**: maps objects to BaseType via chemistry detection
  - **Scene**: distribution-based scene application (capture, apply)
  - **Scripts**: CLI entry points for save/load/browse



```mermaid
classDiagram
    namespace engine {
        class DBController {
            <<abstract>>
            +save_scene(...) int
            +store_object(...) int
            +load_scene(id) dict
            +ingest_scene(...)* int
        }

        class BaseTypeApi {
            <<abstract>>
            +get_selector(base_type)* str
        }

        class BaseType {
            <<constants>>
            ORGANIC
            INORGANIC
            MACROMOLECULAR
            SPECIAL
            CHAINS
        }

        class Condenser {
            <<module>>
            +compress_payload(...) dict
            +detect_distributions(...)
            ...
        }

        class API {
            +get_controller(...) DBController
            +save_scene(...) int
            +load_scene(id) dict
            ...
        }
    }

    namespace pymol_backend {
        class PyMOLController {
            +ingest_scene(...) int
            +get_selector(base_type) str
            +_classify_with_cmd(name) str
        }

        class SceneControl {
            +export_visual_system_state() dict
            +apply_scene(scene_id)
            +capture_and_store(name) int
        }

        class Scripts {
            save_scene.py
            load_scene.py
        }
    }

    DBController <|-- PyMOLController
    BaseTypeApi <|-- PyMOLController
    PyMOLController ..> Condenser : uses
    PyMOLController ..> BaseType : returns
    SceneControl ..> PyMOLController : calls
    SceneControl ..> API : uses
    API --> DBController : facade
    Scripts --> API : uses
    
    note for Scripts "CLI entry points"
```

## Usage


### 1. Setup, lint and test

For POSIX:

```bash
python3 -m venv .venv \
    && . .venv/bin/activate \
    && pip install --upgrade pip setuptools wheel \
    && pip install -e .[dev] \
    && ruff check . \
    && pytest -q
```

For Windows:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install --upgrade pip setuptools wheel; pip install -e .[dev]; ruff check .; pytest -q
```

### 2. Quick run

```bash
python pymol-templates/simple.py
```

Checkout the other template scripts...




