"""Inject PAT into app.js — reads PAT from env var RAC_PAT, never from args."""
import os, sys

pat = os.environ.get("RAC_PAT", "")
if not pat:
    print("ERROR: RAC_PAT env var is empty", file=sys.stderr)
    sys.exit(1)

target = sys.argv[1]
src = open(target).read()
count = src.count("__PAT_UI__")
if count == 0:
    print(f"WARNING: __PAT_UI__ not found in {target}", file=sys.stderr)
out = src.replace("__PAT_UI__", pat)
open(target, "w").write(out)
print(f"inject_pat: {count} occurrence(s) replaced in {target} ({len(pat)} chars)")
