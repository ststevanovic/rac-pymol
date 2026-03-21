import pymol
from pymol import cmd

# 1. Start PyMOL in headless mode (no GUI)
pymol.finish_launching(['pymol', '-cq'])

def run_headless_render(pdb_id="3j1s", output_name="final_voxel.png"):
    print("# --- STEP 1: CONSTRUCTION ---")
    cmd.set("bg_rgb", [1, 1, 1]) # Set background to white
    print(f"Constructing {pdb_id}...")
    # Fetching pdb1 type applies the biological symmetry matrices
    cmd.fetch(pdb_id, name="virus", type="pdb1")
    cmd.split_states("virus")
    cmd.delete("virus")
    cmd.remove("resn HOH")

    print("# --- STEP 2: SMART VISUALIZATION ---")
    target = "virus_*"
    # Multi-color Scaffold
    cmd.color("blue", f"{target} and ss h")     # Helices
    cmd.color("blue", f"{target} and ss s")   # Sheets
    cmd.color("cyan", f"{target} and ss l+''") # Loops
    cmd.show_as("cartoon", target)

    # Radial Bump Detection
    v = cmd.get_extent(target)
    center = [(v[0][i] + v[1][i]) / 2 for i in range(3)]
    cmd.pseudoatom("v_origin", pos=center)
    
    max_radius = max([abs(v[1][i] - center[i]) for i in range(3)])
    cutoff = max_radius * 0.82  # Only outer 18%
    
    # Isolate Bumps (Robust Double-Selection)
    cmd.select("all_atoms", f"{target} and not v_origin")
    cmd.select("core", f"all_atoms within {cutoff} of v_origin")
    cmd.select("bumps", "all_atoms and not core")
    
    print("# --- Resource-intensive process! SOLID BUMPS SURFACE RENDER ---")

    # This is the BIG speed booster: 
    # It tells PyMOL not to worry about internal 'hidden' surfaces
    cmd.set("surface_type", 0) # 1 = Surface (Solvent Accessible), 2 = Mesh, 0 = keeping it same as gui
    
    print("Starting surface tessellation... (System may appear unresponsive for N s)")
    # Use a high-contrast 'Red-White-Blue' or 'Red-Orange-Yellow' field logic
    # This mimics the appearance of Poisson-Boltzmann solvers (like APBS)
   
    # Ensure the surface calculation is using all available CPU threads
    cmd.set("hash_max", 1000)

    # ACTUALLY SHOW THE BUMPS AS SURFACE
    cmd.show_as("surface", "bumps")
    cmd.set("surface_quality", 1) 
    
    # REMOVED CARVE CUTOFF: Ensure full volume is rendered
    print("surface_carve_cutoff")
    cmd.set("surface_carve_cutoff", 0) # IN GUI this was 4.5 surface cutoff - so we are being more productive here...
    
    # FIXED SPECTRUM: Explicitly providing colors to avoid CmdException
    # This creates a 'hot' gradient from Red to Yellow through Orange
    # this is a Data-Intensive Map-Reduce operation.
    print("spectrum")
    # cmd.spectrum("b", "yellow red", "bumps")

    # --- STEP 5: COLORING & TEXTURE (Matching your Pic) ---
    print("Applying Electrostatic-style Color Map...")
    
    # Use 'count' or 'atomic' to create that mottled, high-detail look from your pic
    cmd.spectrum("count", "red yellow", "bumps", byres=1)
    
    # FIXED: Replaced 'lighting_review' with standard high-contrast settings
    cmd.set("direct", 0.8)             # Strong primary light source
    cmd.set("ambient", 0.2)            # Darker shadows in the 'valleys'
    cmd.set("reflect", 0.8)            # High 'metallic' reflection
    cmd.set("spec_power", 120)         # Very tight, sharp highlights

    # SOLIDITY: No transparency
    print("transparency")
    cmd.set("transparency", 0.0, "bumps")
    
    # HIGH-END SHINE: Raytrace reflect settings
    cmd.set("reflect", 0.6, "bumps")
    cmd.set("spec_power", 100, "bumps")

    print("Surface mesh generated successfully.")

    print("# --- STEP 3: THE RAY TRACE ENGINE ---")
    # cmd.set("ray_trace_mode", 1)     # Technical outlines
    cmd.set("ray_trace_mode", 0)     # Technical outlines
    # cmd.set("ray_shadows", 1)        # Realistic depth
    cmd.set("ray_shadows", 0)        # Realistic depth
    # cmd.set("antialias", 2)          # Perfect edges
    cmd.set("antialias", 1)          # Perfect edges
    cmd.zoom(target, buffer=100)
    
    print("Ray tracing starting in background...  Veeeery compute-bound! :)")
    # High-resolution output
    cmd.png(output_name, width=1200, height=1200, dpi=150, ray=1)
    print(f"Render complete: {output_name}")

# Execute
run_headless_render()
cmd.quit()