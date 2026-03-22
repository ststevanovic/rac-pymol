# pymol-workshop

Demo scripts. Run from `rac_pymol/`.

---

### `simple.py` — basic scene store + verify
```bash
conda run -n pymol python pymol-workshop/simple.py
```
Loads `1pdb`, applies cartoon style, ingests to DB as `simple_1pdb`.  
Outputs in `.rendering/`: `_loaded.png`, `_staged.png`, `_staged.json`, `_applied.png`.

---

### `enzyme.py` — reference enzyme scene
```bash
conda run -n pymol python pymol-workshop/enzyme.py
```
Loads `9ax6`, applies full enzyme style (chains, organics, active site),  
ingests **root object only** to DB as `enzyme_9ax6`.  
Drift detection runs automatically — proportional color groups stored in payload.  
**Wipes DB before ingest.** Run before `batch.py`.

---

### `batch.py` — apply stored scene to RCSB candidates
```bash
# enzyme scene → antibody candidates
conda run -n pymol python pymol-workshop/batch.py 9ax6

# limit subjects fetched
BATCH_N_SUBJECTS=2 conda run -n pymol python pymol-workshop/batch.py 9ax6
```
Reads scene `id=1` from DB.  
Fetches `BATCH_N_SUBJECTS` PDB candidates from RCSB for the ref molecule's category.  
Applies stored scene to each candidate → renders PNG.  
Builds slide deck via `Vis.build_deck()` → `.rendering/random/<timestamp>/slides.html`.  
Symlink `.rendering/random/latest.html` always points to the last run.
