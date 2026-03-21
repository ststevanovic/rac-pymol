from pymol import cmd

# 1. Clear the scene
cmd.reinitialize()

# 2. Define coordinates for a basic Diamond Tetrahedral Unit
# Central Silver (Ag) atom and 4 surrounding vertices for the cage
coords = [
    (0.0, 0.0, 0.0),    # Central Ag atom (0)
    (1.0, 1.0, 1.0),    # Top-Right-Front (1)
    (-1.0, -1.0, 1.0),  # Bottom-Left-Front (2)
    (1.0, -1.0, -1.0),  # Top-Left-Back (3)
    (-1.0, 1.0, -1.0)   # Bottom-Right-Back (4)
]

# 3. Create the atoms
for i, pos in enumerate(coords):
    name = "ag_center" if i == 0 else "vertex"
    cmd.pseudoatom("dia_unit", name=name, pos=pos, resi=str(i))

# 4. Draw the Tetrahedral Cage (gray sticks)
# Connecting the vertices to each other to form the frame
connections = [(1,2), (2,3), (3,4), (4,1), (1,3), (2,4)]
for pair in connections:
    cmd.bond(f"dia_unit and resi {pair[0]}", f"dia_unit and resi {pair[1]}")

# 5. Visual Styling to match your image
cmd.show("spheres", "name ag_center")
cmd.show("sticks", "dia_unit")

# Set Colors
cmd.set_color("silver_metallic", [0.75, 0.75, 0.8])
cmd.color("silver_metallic", "name ag_center")
cmd.color("gray40", "name vertex")

# Radii and Quality
cmd.set("sphere_scale", 0.6, "name ag_center")
cmd.set("stick_radius", 0.12)
cmd.set("stick_quality", 50)
cmd.set("sphere_quality", 4)

# Lighting for the "Cool" Effect
cmd.set("ray_trace_mode", 1)  # Outline mode
cmd.set("ray_shadow", 1)
cmd.set("ambient", 0.5)
cmd.set("reflect", 0.3)
cmd.set("direct", 0.7)

cmd.zoom()