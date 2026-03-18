# pymol-backend

PyMOL-specific concrete backend for the rendering-as-code engine.  
Handles all PyMOL concerns: session capture, molecular classification,
DB ingestion, and scene restoration.


## Next features

### `utils.py`

Maybe some better name to simulated perfecting the scope.
Stub module — **not yet wired into the pipeline**.  
Defines the API for future user-GUI-selection detection and special-block
reconstruction.  See § Future Work.

---

### BaseType / SPECIAL Semantics

SPECIAL is **dual-purpose**:

| Role | Meaning | `get_selector` returns |
|---|---|---|
| **Primary base_type** | Tool has no native selector (CGO axes, nanomaterial, graphene) | `""` — no universal keyword |
| **Payload subcategory** | List of user-defined GUI selections sub-scoping the parent object | n/a — entries carry their own `base_type` + distribution |

The `"special"` key in a payload is always a **list**:

```json
{
  "macromolecular": {"atom_type_colors": {"CA": 11, "C": 26}},
  "special": [
    {
      "name": "active_site_residues",
      "base_type": "macromolecular",
      "atom_type_colors": {"CA": 25},
      "ratio": 0.20,
      "distribution": {"start": 0.80, "end": 1.0}
    }
  ]
}
```

Multiple entries are allowed — one per user-defined selection that
sub-scopes the parent object.