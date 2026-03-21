from pymol import cmd, util

# --- 1. Scene Initialization ---
cmd.reinitialize()
cmd.set("bg_rgb", [1, 1, 1])          # Clean white background
cmd.set("orthoscopic", 1)             # Remove perspective distortion for "architectural" look
cmd.set("field_of_view", 30)          # Narrower FOV for better lattice alignment

# --- 2. Load and Prepare Cargo (Streptavidin) ---
cmd.fetch("6J6J", "cargo")
cmd.remove("resn HOH")                # Clean up water
cmd.select("prot", "cargo and polymer.protein")

# Visual styling for the protein
cmd.show_as("surface", "prot")
cmd.set_color("cargo_blue", [0.3, 0.5, 0.9])
cmd.color("cargo_blue", "prot")
cmd.set("surface_quality", 2)
cmd.set("transparency", 0.2, "prot")  # Slight transparency for "gel" look
cmd.center("cargo")
cmd.origin("cargo")

# --- 3. Construct the Polyhedral DNA Frame (Tetrahedron) ---
# Scale adjusted to encapsulate the 6J6J tetramer (~45 Angstroms)
scale = 48 
vertices = [
    ( scale,  scale,  scale),  # V1
    (-scale, -scale,  scale),  # V2
    ( scale, -scale, -scale),  # V3
    (-scale,  scale, -scale)   # V4
]

for i, pos in enumerate(vertices):
    cmd.pseudoatom("frame", name="v", pos=pos, resi=str(i+1))

# Create the "Grey Frame" connectivity
connections = [(1,2), (2,3), (3,4), (4,1), (1,3), (2,4)]
for pair in connections:
    cmd.bond(f"frame and resi {pair[0]}", f"frame and resi {pair[1]}")

# Style the frame
cmd.show("sticks", "frame")
cmd.set("stick_radius", 1.8)
cmd.set_color("dna_grey", [0.6, 0.6, 0.6])
cmd.color("dna_grey", "frame")
cmd.set("stick_quality", 50)

# --- 4. Add Purple Hybridization Linkers ---
# These extend from the vertices outward
for i, pos in enumerate(vertices):
    ext_pos = [p * 1.35 for p in pos] # Extend 35% further out
    cmd.pseudoatom("linkers", name="link", pos=ext_pos, resi=str(i+1))
    cmd.bond(f"frame and resi {i+1}", f"linkers and resi {i+1}")

cmd.show("lines", "linkers")
cmd.set("line_width", 5)
cmd.set_color("hybrid_purple", [0.6, 0.2, 0.8])
cmd.color("hybrid_purple", "linkers")

# --- 5. Ray Tracing & Lighting Setup ---
# This utilizes the internal Ray Trace engine for the "Cool" effect
cmd.set("ray_trace_mode", 1)           # Add subtle outlines
cmd.set("ray_shadow", 1)               # Enable shadows
cmd.set("ray_trace_gain", 0.4)         # Enhance ambient occlusion in protein crevices
cmd.set("ambient", 0.5)                # Soften dark areas
cmd.set("direct", 0.7)                 # Stronger primary light source
cmd.set("reflect", 0.2)                # Slight metallic sheen on the frame

cmd.zoom("all", 10)
print("Voxel Setup Complete. Type 'ray' for final render.")