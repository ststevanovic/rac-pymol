# pymol-backend

PyMOL concrete backend for the rendering-as-code engine.

## Files

| File | Role |
|---|---|
| `adapter.py` | `PyMOLController` — classification contract (`is_*`) + `capture_scene` trigger. Calls `DataPipeline`. |
| `driver.py` | Apply only — reads DB payload → `cmd` calls. `save_scene` / `apply_scene` / `SceneSession` / `BatchSession`. |
| `middleware.py` | `DataPipeline` — raw session JSON → staged BT payload (LayerA→D). |

## Capture flow

```
capture_scene()
  └─ _extract_scene()        ← raw PyMOL session dict
       └─ DataPipeline().process(raw)   ← LayerA→B→C→D
            └─ (SceneRecord, [SceneObject]) → DB
```

## Apply flow

```
apply_scene()
  └─ _apply_object()
       ├─ _apply_colours()          ← ratios + atom_names + special drift
       │    └─ reconstruct_special_drift()   ← middleware helper, called by driver
       └─ _apply_chain_settings()
```

## BaseType / SPECIAL

SPECIAL is dual-purpose:

| Role | Meaning |
|---|---|
| Primary `base_type` | Object selector (CGO, axes, nanomaterial) |
| `payload[bt]["special"]` | Drift entries within a chemistry bucket — not a primary classification |