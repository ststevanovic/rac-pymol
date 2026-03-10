from pathlib import Path
from pymol import cmd

# PML_DIR = Path(__file__).parent / "pmlrepo"
PML_DIR = Path.cwd() / "pmlrepo"

def recipe(action: str = ""):
    if action is None or len(action) == 0 or action == "":
        raise ValueError("Try `recipe ls` or `recipe <pml scrip name>` ...")

    if action == "ls":
        for n in sorted(PML_DIR.glob("*.pml")):
            print(n.stem)
        return

    else:
        script = PML_DIR / f"{action}.pml"
        if script.exists():
            cmd.run(str(script))
        else:
            print(f"Not found: {script}")

cmd.extend("recipe", recipe)
