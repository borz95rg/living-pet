# Living Fox Pet — 3D starter pack

## What this creates
A Blender procedural starter character for five growth stages:
1. Baby
2. Cub
3. Teen
4. Adult
5. Legendary

Each stage is exported as its own GLB and editable BLEND scene. The rig uses named bones for the spine, head, three tail sections, ears, and leg chains. Six named animation actions are authored: Idle, Walk, Run, Jump, Sleep, React.

## Generate the assets
1. Install Blender 4.x.
2. Put `make_fox_pet.py` in an empty folder.
3. Run from a terminal:

   `blender -b --python make_fox_pet.py`

4. Find outputs in the `exports` folder.

## Android integration
Use the GLB files with a runtime that supports glTF 2.0 skeletal animation (for example, Filament/SceneView). Load one growth-stage GLB at a time and select animation clips by name. Typical mapping:
- Idle: loop while waiting
- Walk: loop for short movement
- Run: loop for fast movement
- Jump: one-shot
- Sleep: loop while resting
- React: one-shot when touched, spoken to, or when an event occurs

For a floating overlay, Android still needs a separately implemented overlay service and the user's explicit “display over other apps” permission. The GLB does not itself create an Android overlay.

## Important limitations
This is a procedural prototype, not a final hand-sculpted commercial character. It provides separate mesh parts, a named armature, and starter keyframe actions. Before shipping, a 3D artist should refine topology, fur, facial expressions, paw contacts, skinning/weights, and animation polish. The current script parents rigid mesh parts to bones for a reliable starter rig; it is not soft-skin deformation.
