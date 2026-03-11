"""PyMOL integration setup - import this in your PyMOL session.

This module provides tight integration between PyMOL and the scenography
database, with memory-efficient direct writes instead of JSON intermediates.

Usage
-----
In PyMOL or .pymolrc:
    from pymol_backend import pymol_integration
Or manually configure custom db:
    from pymol_backend import scene
    scene.setup_db("/path/to/custom.db")

Available Commands
------------------
- capture_and_store [name] — Store current view to database
- apply_scene scene_id=N — Restore scene by ID
- apply_scene scene_name="X" — Restore scene by name
- save_scene_json [file] — Debug: export to JSON
- setup_db [path] — Configure custom database path
"""

#  BOT - Move the db related code here 
# scene.py should be only for saving and loading the scene...

from . import scene

# Auto-initialize with default database on import
scene.setup_db()

print("PyMOL scenography integration ready")
print(f"Database: {scene.get_db_path()}")
print("Commands: capture_and_store, apply_scene, save_scene_json")
