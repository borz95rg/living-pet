# Living Fox Pet — Blender asset generator
# Run with Blender 4.x:
#   blender -b --python make_fox_pet.py
# Outputs: fox_stage_1_baby.glb ... fox_stage_5_legendary.glb
#
# This is a procedural, stylized starter character (not a production sculpt).
# Every body part is a separate mesh attached to a named bone. Each GLB contains
# the six animation clips: Idle, Walk, Run, Jump, Sleep, React.

import bpy, math, os
from mathutils import Vector, Euler

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
os.makedirs(OUT_DIR, exist_ok=True)

def mat(name, color, rough=0.72, emission=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = rough
    if emission:
        bs.inputs["Emission Color"].default_value = (*color, 1)
        bs.inputs["Emission Strength"].default_value = emission
    return m

ORANGE = mat("Fox • warm orange", (0.92, 0.24, 0.045))
LIGHT = mat("Fox • cream", (1.0, 0.78, 0.55))
WHITE = mat("Fox • tail tip", (1.0, 0.91, 0.79))
DARK = mat("Fox • paws", (0.16, 0.075, 0.055))
PINK = mat("Fox • ear inner", (0.95, 0.28, 0.32))
EYE = mat("Fox • eyes", (0.035, 0.018, 0.012), 0.18)
GOLD = mat("Legendary • gold glow", (1.0, 0.48, 0.055), 0.35, 0.7)

def uv(name, loc, scale, material, segments=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    for p in o.data.polygons: p.use_smooth = True
    return o

def cone(name, loc, radius1, depth, material, rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=radius1, radius2=0.025, depth=depth,
                                    location=loc, rotation=rotation)
    o=bpy.context.object; o.name=name; o.data.materials.append(material)
    for p in o.data.polygons: p.use_smooth=True
    bevel=o.modifiers.new("Soft edges","BEVEL"); bevel.width=0.045; bevel.segments=3
    o.modifiers.new("Weighted normals","WEIGHTED_NORMAL")
    return o

def create_rig(prefix, stage, scale):
    # Clear scene for a clean standalone export
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    # Actions are datablocks and survive deleting their armature users. Remove
    # the previous stage's clips so each exported GLB contains exactly six.
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    arm_data=bpy.data.armatures.new(prefix+"_Skeleton")
    arm=bpy.data.objects.new(prefix+"_RIG", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active=arm; arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bones={}
    def bone(name, head, tail, parent=None):
        b=arm_data.edit_bones.new(name); b.head=head; b.tail=tail
        if parent: b.parent=bones[parent]
        bones[name]=b
    bone("Root",(0,0,0),(0,0,0.35))
    bone("Spine",(0,0,0.35),(0,0,0.95),"Root")
    bone("Head",(0,0,0.95),(0,0,1.35),"Spine")
    bone("Tail_01",(0,-0.25,0.48),(0,-0.72,0.68),"Root")
    bone("Tail_02",(0,-0.72,0.68),(0,-1.08,0.82),"Tail_01")
    bone("Tail_03",(0,-1.08,0.82),(0,-1.35,0.94),"Tail_02")
    for side, x in (("L",-0.23),("R",0.23)):
        bone("Ear_"+side,(x,0,1.31),(x*1.35,0,1.68),"Head")
        bone("FrontUpper_"+side,(x*0.72,0.12,0.45),(x*0.72,0.12,0.23),"Spine")
        bone("FrontLower_"+side,(x*0.72,0.12,0.23),(x*0.72,0.12,0.06),"FrontUpper_"+side)
        bone("BackUpper_"+side,(x*0.72,-0.43,0.42),(x*0.72,-0.43,0.22),"Root")
        bone("BackLower_"+side,(x*0.72,-0.43,0.22),(x*0.72,-0.43,0.06),"BackUpper_"+side)
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.show_in_front=True
    arm.scale=(scale,scale,scale)

    # All pieces are separate meshes, attached to bones so the rig can animate them.
    def attach(obj, bone_name):
        # Keep the mesh in its intended world-space location while assigning its
        # bone parent. Reading matrix_world after setting parent captures Blender's
        # already-shifted matrix and makes exported parts drift away from the body.
        world_matrix = obj.matrix_world.copy()
        obj.parent=arm; obj.parent_type='BONE'; obj.parent_bone=bone_name
        obj.matrix_parent_inverse=(arm.matrix_world @ arm.data.bones[bone_name].matrix_local).inverted()
        obj.matrix_world = world_matrix
        return obj

    # Main silhouette
    attach(uv(prefix+"_Body",(0,0,0.53),(0.39,0.67,0.40),ORANGE), "Spine")
    attach(uv(prefix+"_Chest",(0,0.27,0.55),(0.32,0.34,0.34),LIGHT), "Spine")
    attach(uv(prefix+"_Head",(0,0.35,1.10),(0.34,0.34,0.34),ORANGE), "Head")
    attach(uv(prefix+"_Cheeks",(0,0.57,0.98),(0.27,0.19,0.18),LIGHT), "Head")
    attach(uv(prefix+"_Muzzle",(0,0.66,1.02),(0.19,0.18,0.12),LIGHT), "Head")
    attach(uv(prefix+"_Nose",(0,0.82,1.07),(0.065,0.045,0.05),DARK), "Head")
    for side,x in (("L",-0.145),("R",0.145)):
        attach(uv(prefix+"_Eye_"+side,(x,0.635,1.20),(0.068,0.045,0.085),EYE), "Head")
        ear=cone(prefix+"_Ear_"+side,(x*1.15,0.30,1.48),0.14,0.42,ORANGE,rotation=(math.radians(-8),0,math.radians(x*20)))
        attach(ear,"Ear_"+side)
        inner=cone(prefix+"_EarInner_"+side,(x*1.15,0.345,1.49),0.075,0.29,PINK,rotation=(math.radians(-8),0,math.radians(x*20)))
        attach(inner,"Ear_"+side)

    # Tail as three fluffy articulated sections; white tip is its own part.
    attach(uv(prefix+"_TailBase",(0,-0.58,0.67),(0.25,0.48,0.25),ORANGE),"Tail_01")
    attach(uv(prefix+"_TailMid",(0,-1.00,0.82),(0.25,0.43,0.25),ORANGE),"Tail_02")
    attach(uv(prefix+"_TailTip",(0,-1.34,0.94),(0.24,0.34,0.23),WHITE),"Tail_03")

    # Four articulated legs, upper and lower pieces
    for side,x in (("L",-0.23),("R",0.23)):
        for limb, y, upper, lower in (("Front",0.17,"FrontUpper_","FrontLower_"),("Back",-0.43,"BackUpper_","BackLower_")):
            up=upper+side; lo=lower+side
            attach(uv(prefix+"_"+limb+"Leg_"+side,(x,y,0.29),(0.105,0.14,0.25),ORANGE),"Spine" if limb=="Front" else "Root")
            attach(uv(prefix+"_"+limb+"Paw_"+side,(x,y+0.025,0.075),(0.12,0.16,0.075),DARK),lo)

    # Stage-specific size and proportions; same rig contract across all stages.
    arm["growth_stage"]=stage
    arm["animation_clips"]="Idle,Walk,Run,Jump,Sleep,React"
    arm["rig_notes"]="Tail_01..03, Ear_L/R, four upper/lower leg chains"

    def animate(action_name, frames, rotations=None, locations=None):
        bpy.context.scene.frame_start=1; bpy.context.scene.frame_end=max(f for f,_ in frames)
        bpy.ops.object.mode_set(mode='OBJECT')
        if arm.animation_data is None: arm.animation_data_create()
        action=bpy.data.actions.new(prefix+"_"+action_name)
        arm.animation_data.action=action
        for frame, value in frames:
            bpy.context.scene.frame_set(frame)
            for bn in ["Spine","Head","Tail_01","Tail_02","Tail_03","Ear_L","Ear_R",
                       "FrontUpper_L","FrontUpper_R","FrontLower_L","FrontLower_R",
                       "BackUpper_L","BackUpper_R","BackLower_L","BackLower_R"]:
                pb=arm.pose.bones.get(bn)
                if not pb: continue
                pb.rotation_mode='XYZ'
                rot=(rotations or {}).get(bn,(0,0,0))
                # Per-frame multiplier lets each clip keep a readable, compact key set.
                mul=value if isinstance(value,(int,float)) else 1.0
                pb.rotation_euler=Euler((rot[0]*mul,rot[1]*mul,rot[2]*mul),'XYZ')
                pb.keyframe_insert(data_path="rotation_euler",frame=frame,group=bn)
            root=arm.pose.bones["Root"]
            root.location=(0,0,(locations or {}).get(frame,0.0))
            root.keyframe_insert(data_path="location",frame=frame,group="Root")
        if action.fcurves:
            for fc in action.fcurves:
                for k in fc.keyframe_points: k.interpolation='BEZIER'
        # Put each clip on its own NLA track so glTF export can retain all clips.
        track = arm.animation_data.nla_tracks.new()
        track.name = action_name
        strip = track.strips.new(action_name, int(action.frame_range[0]), action)
        strip.name = action_name
        arm.animation_data.action = None
        return action

    # Six independent animation actions. Looping is configured in the game runtime.
    animate("Idle",[(1,0),(12,1),(24,0)],{
        "Spine":(0,0,0.025),"Head":(0,0,0.035),"Tail_01":(0.06,0,0.12),
        "Tail_02":(0.08,0,0.14),"Tail_03":(0.1,0,0.16),"Ear_L":(0,0,0.04),"Ear_R":(0,0,-0.04)})
    animate("Walk",[(1,1),(7,-1),(13,1),(19,-1),(25,1)],{
        "FrontUpper_L":(0.45,0,0),"FrontUpper_R":(-0.45,0,0),
        "BackUpper_L":(-0.42,0,0),"BackUpper_R":(0.42,0,0),
        "Tail_01":(0.04,0,0.12),"Tail_02":(0.04,0,0.14)})
    animate("Run",[(1,1),(5,-1),(9,1),(13,-1),(17,1)],{
        "Spine":(0.08,0,0),"FrontUpper_L":(0.85,0,0),"FrontUpper_R":(-0.85,0,0),
        "BackUpper_L":(-0.8,0,0),"BackUpper_R":(0.8,0,0),
        "Tail_01":(0,0,0.2),"Tail_02":(0,0,0.22),"Tail_03":(0,0,0.18)},
        {1:0,5:0.06,9:0,13:0.06,17:0})
    animate("Jump",[(1,0),(5,1),(10,1),(16,0)],{
        "Spine":(-0.12,0,0),"FrontUpper_L":(-0.8,0,0),"FrontUpper_R":(-0.8,0,0),
        "BackUpper_L":(0.6,0,0),"BackUpper_R":(0.6,0,0),
        "Tail_01":(0,0,0.28),"Tail_02":(0,0,0.24)},
        {1:0,5:0.45,10:0.45,16:0})
    animate("Sleep",[(1,0),(12,1),(24,0)],{
        "Spine":(0.16,0,0),"Head":(0.35,0,0.08),"Tail_01":(0,0,0.3),
        "Tail_02":(0,0,0.35),"Tail_03":(0,0,0.28),"Ear_L":(0,0,-0.15),"Ear_R":(0,0,0.15)})
    animate("React",[(1,0),(4,1),(8,-0.5),(12,0)],{
        "Head":(-0.25,0,0),"Ear_L":(0,0,0.22),"Ear_R":(0,0,-0.22),
        "Tail_01":(0,0,0.32),"Tail_02":(0,0,0.25),"Spine":(-0.06,0,0)})

    # Simple camera/light for the accompanying .blend preview
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.camera_add(location=(3.1,4.0,2.6))
    cam=bpy.context.object; cam.name="PreviewCamera"
    cam.rotation_euler=(Vector((0,-0.1,0.82))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO'; cam.data.ortho_scale=3.9
    bpy.context.scene.camera=cam
    bpy.ops.object.light_add(type='AREA', location=(1.5,2.5,3.5))
    light=bpy.context.object; light.data.energy=450; light.data.shape='DISK'; light.data.size=4
    light.rotation_euler=(Vector((0,0,0.7))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.scene.render.engine='BLENDER_EEVEE_NEXT'
    bpy.context.scene.render.resolution_x=900; bpy.context.scene.render.resolution_y=900
    bpy.context.scene.render.resolution_percentage=100
    bpy.context.scene.world.color=(0.035,0.035,0.07)
    bpy.context.scene.frame_set(1)

    # Export this stage as an independent GLB with all six named actions.
    bpy.ops.object.select_all(action='SELECT')
    bpy.context.view_layer.objects.active=arm
    filename=os.path.join(OUT_DIR, f"fox_stage_{stage}_{['baby','cub','teen','adult','legendary'][stage-1]}.glb")
    bpy.ops.export_scene.gltf(filepath=filename, export_format='GLB',
        use_selection=True, export_animations=True, export_skins=True,
        export_apply=True, export_yup=True, export_materials='EXPORT',
        export_cameras=False, export_lights=False)
    # Save editable Blender scene for this stage.
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR,f"fox_stage_{stage}.blend"))
    print("Exported:",filename)

STAGES=[
    ("Fox_Baby",1,0.72),
    ("Fox_Cub",2,0.84),
    ("Fox_Teen",3,0.94),
    ("Fox_Adult",4,1.00),
    ("Fox_Legendary",5,1.08),
]
for p,s,sc in STAGES:
    create_rig(p,s,sc)

print("DONE. GLB and BLEND files are in:",OUT_DIR)
