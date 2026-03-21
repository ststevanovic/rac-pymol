# PyMOL Templates

Demo with RaC PyMOL toolkit. 
The general workflow:
    stage the scene → store to DB → reload from DB → verify with PNG render check (px-compare store and reload).

## Run Examples

Run from `rac_pymol/`:

### simple.py
```bash
python pymol-templates/simple.py
```
Outputs in `.rendering/`:
- `_staged.png` — styled scene before DB round-trip
- `_staged.json` — debug JSON snapshot
- `_applied.png` — scene restored from `scenography.db`

