# Rendering as Code with PyMOL

A minimal Python project for "Rendering as Code with PyMOL".

## Architecture

Two layers:

* **`engine`** — renderer-agnostic core:
  - **`DBController`** (ABC) — SQL persistence
  - **`MolecularClassifier`** (ABC) — `is_*` slots + `classify_object`
  - **`SceneBackend`** (ABC) — `capture_scene` contract + `ingest_scene` wiring
  - **`BackendController`** — composes all three ABCs; backends subclass this only
  - **`BaseType`** — constants (`MACROMOLECULAR`, `ORGANIC`, `INORGANIC`, `SPECIAL`, `CHAINS`)

* **`pymol-backend`** — PyMOL concrete implementation:
  - **`PyMOLController`** — implements all ABC slots via `cmd` selectors; `capture_scene` reads `cmd.get_session()` once
  - **`driver`** — `save_scene` / `apply_scene` registered via `cmd.extend`



```mermaid
classDiagram
    direction LR
    namespace engine {
        class DBController {
            +make_scene_record()
            +ingest_scene()
            -_list_scenes()
        }

        class MolecularClassifier {
            <<abstract>>
            +is_*() abc
        }

        class SceneBackend {
            <<abstract>>
            +capture_scene() abc
        }

        class BackendController {
            <<facade>>
            +list_scenes()
            +load_*()
        }

        class BaseType {
            <<enumeration>>
            +MACROMOLECULAR str
            +ORGANIC str
            +INORGANIC str
            +SPECIAL str
            +CHAINS str
        }
    }

    namespace pymol_backend {
        class PyMOLController {
            +is_*()
            +capture_scene()
        }

        class driver {
            <<module>>
            +save_scene()
            +apply_scene()
        }
    }

    BackendController o--> DBController
    BackendController --|> MolecularClassifier
    BackendController --|> SceneBackend
    MolecularClassifier ..> BaseType
    PyMOLController --|> BackendController
    driver --> PyMOLController
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
python pymol-workshop/simple.py
```