"""
Living Pet — генератор 3D-лисы (5 стадий роста) для Blender 4.2+ / 5.x.

Запуск:
    blender -b --python make_fox_3d.py -- --out ./exports
    # или с модулем bpy:  python make_fox_3d.py --out ./exports [--stages 4]

Что делает:
  * Строит цельное гладкое тело (голова, щёки, мордочка, грудка, лапы) через
    поля расстояний (SDF) + marching cubes, а не из отдельных шариков.
  * Отдельно: пушистый хвост (у легендарной формы — три), уши с белым пухом,
    глаза с радужкой/зрачком и бликами, веки, нос, улыбка, рот для разговора.
  * Раскраска вершин как на концепте: рыжая спина, белые мордочка/грудь,
    тёмные «чулки» на лапах, тёмные кончики ушей, белый кончик хвоста.
  * Длина шерсти на каждой вершине (2-й UV-канал "FurData"), её читает
    шейдер шерсти в игре (fox3d.js) и рисует 14 слоёв пушистого меха.
  * Скелет с IK для ног; анимации запекаются в FK:
      Idle, Sit, Walk, Run, Jump, Sleep, React, Happy, Eat, Stretch, Wag,
      Blink, Talk
  * Экспорт GLB: fox_stage_1_baby.glb … fox_stage_5_legendary.glb
    (те же имена, что и раньше; клипы называются Fox_<Stage>_<Clip>).
"""
import sys, os, math, json, struct, argparse
import numpy as np
import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

try:
    from skimage.measure import marching_cubes
except ImportError:  # Blender's bundled Python: pip install scikit-image
    raise SystemExit("Нужен scikit-image:  <blender-python> -m pip install scikit-image")

FPS = 24
LID_REST = 0.60   # lids hide inside the eyeball until a blink scales them out
FUR_UNIT = 1.0

# ---------------------------------------------------------------- stages
STAGES = [
    dict(key="baby", name="Baby", head=(0.335, 0.30, 0.29), body_len=0.30, body_r=0.165, leg=0.17,
         muzzle=0.085, ear_h=0.25, ear_w=0.135, eye_r=0.088, tail_len=0.52, tail_r=0.14, fur=0.040,
         paw=(0.066, 0.085, 0.048), neck=0.05),
    dict(key="cub", name="Cub", head=(0.315, 0.29, 0.28), body_len=0.40, body_r=0.175, leg=0.23,
         muzzle=0.11, ear_h=0.28, ear_w=0.14, eye_r=0.082, tail_len=0.64, tail_r=0.155, fur=0.040,
         paw=(0.068, 0.088, 0.05), neck=0.07),
    dict(key="teen", name="Teen", head=(0.295, 0.285, 0.27), body_len=0.52, body_r=0.185, leg=0.31,
         muzzle=0.14, ear_h=0.31, ear_w=0.145, eye_r=0.076, tail_len=0.80, tail_r=0.17, fur=0.038,
         paw=(0.068, 0.09, 0.05), neck=0.10),
    dict(key="adult", name="Adult", head=(0.285, 0.285, 0.265), body_len=0.62, body_r=0.20, leg=0.37,
         muzzle=0.17, ear_h=0.33, ear_w=0.15, eye_r=0.071, tail_len=0.95, tail_r=0.185, fur=0.038,
         paw=(0.07, 0.092, 0.052), neck=0.12),
    dict(key="legendary", name="Legendary", head=(0.285, 0.285, 0.265), body_len=0.62, body_r=0.20, leg=0.37,
         muzzle=0.17, ear_h=0.35, ear_w=0.15, eye_r=0.071, tail_len=0.95, tail_r=0.16, fur=0.040,
         paw=(0.07, 0.092, 0.052), neck=0.12, tails=3, legendary=True),
]

# ---------------------------------------------------------------- palette (sRGB)
def hexc(h):
    h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) / 255 for i in (0, 2, 4)])

PAL = dict(
    orange=hexc('#F0742A'), back=hexc('#D9561C'), white=hexc('#FFF6EC'), cream=hexc('#FFE3C8'),
    dark=hexc('#3A2219'), darkleg=hexc('#4A2A1E'), earin=hexc('#FFD9CF'), nose=hexc('#1E1412'),
    mouth=hexc('#7A2E2E'), tongue=hexc('#E86F78'), sclera=hexc('#FFF6EA'), iris_in=hexc('#F6BE45'),
    iris_out=hexc('#B5621A'), limbal=hexc('#3B1D0E'), pupil=hexc('#120806'),
)
PAL_LEG = dict(PAL, orange=hexc('#FF951C'), back=hexc('#E5600A'), white=hexc('#FFF1C0'),
               cream=hexc('#FFE7A6'), dark=hexc('#C9561A'), darkleg=hexc('#E0791C'), earin=hexc('#FFF0B0'),
               iris_in=hexc('#FFF2A0'), iris_out=hexc('#FF9A1E'), limbal=hexc('#8A3A08'))

def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

# ---------------------------------------------------------------- SDF primitives
def rot_to(axis_from, axis_to):
    a = Vector(axis_from).normalized(); b = Vector(axis_to).normalized()
    return np.array(a.rotation_difference(b).to_matrix())

class Prim:
    """One shape: ellipsoid or tapered capsule. `bone` = who owns it for skinning."""
    def __init__(self, kind, bone, k=0.05, fur=1.0, tag="", **p):
        self.kind, self.bone, self.k, self.fur, self.tag, self.p = kind, bone, k, fur, tag, p

    def sdf(self, P):
        p = self.p
        if self.kind == 'ell':
            q = P - p['c']
            if 'R' in p: q = q @ p['R']
            r = np.asarray(p['r'])
            k0 = np.linalg.norm(q / r, axis=1); k1 = np.linalg.norm(q / (r * r), axis=1)
            return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
        if self.kind == 'cap':
            a, b = np.asarray(p['a']), np.asarray(p['b'])
            ba = b - a; pa = P - a
            h = np.clip(pa @ ba / (ba @ ba), 0, 1)
            if 'flat' in p:  # anisotropic cross-section: scale one axis
                d = pa - np.outer(h, ba)
                ax = np.asarray(p['flat_axis']); comp = d @ ax
                d = d + np.outer(comp * (1.0 / p['flat'] - 1.0), ax)
                return np.linalg.norm(d, axis=1) - (p['ra'] + (p['rb'] - p['ra']) * h)
            return np.linalg.norm(pa - np.outer(h, ba), axis=1) - (p['ra'] + (p['rb'] - p['ra']) * h)
        raise ValueError(self.kind)

    def bbox(self):
        p = self.p
        if self.kind == 'ell':
            m = max(p['r']); c = np.asarray(p['c']); return c - m, c + m
        a, b = np.asarray(p['a']), np.asarray(p['b']); m = max(p['ra'], p['rb'])
        return np.minimum(a, b) - m, np.maximum(a, b) + m

def smin(a, b, k):
    if k <= 0: return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25

def smax(a, b, k):
    return -smin(-a, -b, k)

def field(prims, P, subtract=()):
    d = None
    for pr in prims:
        s = pr.sdf(P)
        d = s if d is None else smin(d, s, pr.k)
    for pr in subtract:
        d = smax(d, -pr.sdf(P), pr.k)
    return d

def polygonize(prims, res, subtract=(), margin=0.06):
    lo = np.min([pr.bbox()[0] for pr in prims], axis=0) - margin
    hi = np.max([pr.bbox()[1] for pr in prims], axis=0) + margin
    n = np.ceil((hi - lo) / res).astype(int) + 1
    xs, ys, zs = [lo[i] + np.arange(n[i]) * res for i in range(3)]
    G = np.stack(np.meshgrid(xs, ys, zs, indexing='ij'), -1).reshape(-1, 3)
    vol = np.empty(len(G), dtype=np.float32)
    CH = 400_000
    for i in range(0, len(G), CH):
        vol[i:i+CH] = field(prims, G[i:i+CH], subtract)
    vol = vol.reshape(n)
    v, f, _, _ = marching_cubes(vol, 0.0, spacing=(res, res, res))
    v = v + lo
    return v, f[:, ::-1].copy()  # outward winding

def surface_point(prims, origin, direction, subtract=()):
    """Bisection along a ray from inside → first surface crossing."""
    o = np.asarray(origin, float); d = np.asarray(direction, float); d /= np.linalg.norm(d)
    lo, hi = 0.0, 2.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if field(prims, (o + d * mid)[None], subtract)[0] < 0: lo = mid
        else: hi = mid
    return o + d * lo

def ownership(prims, P, tau):
    D = np.stack([pr.sdf(P) for pr in prims], 1)
    D = D - D.min(1, keepdims=True)
    W = np.exp(-D / tau); W /= W.sum(1, keepdims=True)
    return W

# ---------------------------------------------------------------- mesh helpers
def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.actions,
                 bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            coll.remove(item)

def simplify(v, f, target_faces):
    me = bpy.data.meshes.new("tmp"); me.from_pydata(v.tolist(), [], f.tolist()); me.update()
    ob = bpy.data.objects.new("tmp", me); bpy.context.collection.objects.link(ob)
    if len(f) > target_faces:
        m = ob.modifiers.new("dec", 'DECIMATE'); m.ratio = target_faces / len(f)
    sm = ob.modifiers.new("smooth", 'SMOOTH'); sm.factor = 0.5; sm.iterations = 2
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    nv = np.zeros(len(me2.vertices) * 3); me2.vertices.foreach_get('co', nv)
    nf = [tuple(p.vertices) for p in me2.polygons]
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me); bpy.data.meshes.remove(me2)
    tris = []
    for poly in nf:
        for i in range(1, len(poly) - 1): tris.append((poly[0], poly[i], poly[i + 1]))
    return nv.reshape(-1, 3), np.array(tris, dtype=np.int64)

def vertex_normals(v, f):
    n = np.zeros_like(v)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for i in range(3): np.add.at(n, f[:, i], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)

class Part:
    """Accumulated geometry with per-vertex color/fur/weights."""
    def __init__(self, name, v, f, color, fur, weights, material, uv_density=14.0):
        self.name, self.v, self.f, self.color, self.fur, self.w = name, v, f, color, fur, weights
        self.material, self.uv_density = material, uv_density

def triplanar_loop_uvs(v, f, density):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    ax = np.argmax(np.abs(fn), 1)
    uv = np.zeros((len(f), 3, 2))
    pairs = {0: (1, 2), 1: (0, 2), 2: (0, 1)}
    for a, (i, j) in pairs.items():
        m = ax == a
        pts = v[f[m]]
        uv[m, :, 0] = pts[..., i] * density
        uv[m, :, 1] = pts[..., j] * density
    return uv.reshape(-1, 2)

def build_object(part, arm, bone_names):
    me = bpy.data.meshes.new(part.name)
    me.from_pydata(part.v.tolist(), [], part.f.tolist()); me.update()
    me.shade_smooth()
    col = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    rgba = np.ones((len(part.v), 4)); rgba[:, :3] = srgb_to_lin(part.color)
    col.data.foreach_set('color', rgba.ravel())
    me.color_attributes.active_color = col
    try: me.color_attributes.render_color_index = me.color_attributes.active_color_index
    except Exception: pass
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set('uv', triplanar_loop_uvs(part.v, part.f, part.uv_density).ravel())
    fd = me.uv_layers.new(name="FurData")
    loop_fur = part.fur[part.f.ravel()]
    fdata = np.stack([loop_fur, np.zeros_like(loop_fur)], 1)
    fd.data.foreach_set('uv', fdata.ravel())
    me.uv_layers.active = uv
    me.materials.append(part.material)
    ob = bpy.data.objects.new(part.name, me); bpy.context.collection.objects.link(ob)
    # skin weights: keep 4 strongest
    W = part.w
    idx = np.argsort(-W, 1)[:, :4]
    groups = {}
    for vi in range(len(part.v)):
        ws = W[vi, idx[vi]]; s = ws.sum()
        for j, bi in enumerate(idx[vi]):
            if ws[j] / s < 0.01: continue
            groups.setdefault(bi, []).append((vi, float(ws[j] / s)))
    for bi, lst in groups.items():
        vg = ob.vertex_groups.new(name=bone_names[bi])
        by_w = {}
        for vi, w in lst: by_w.setdefault(round(w, 3), []).append(vi)
        for w, vis in by_w.items(): vg.add(vis, w, 'REPLACE')
    ob.parent = arm
    mod = ob.modifiers.new("Armature", 'ARMATURE'); mod.object = arm
    return ob

def make_material(name, color, rough=0.8, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; bs = nt.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*srgb_to_lin(color), 1)
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metal
    if emit:
        bs.inputs["Emission Color"].default_value = (*srgb_to_lin(color), 1)
        bs.inputs["Emission Strength"].default_value = emit
    # vertex color drives base color (exported as COLOR_0)
    ca = nt.nodes.new("ShaderNodeVertexColor"); ca.layer_name = "Col"
    nt.links.new(ca.outputs["Color"], bs.inputs["Base Color"])
    return m

# ---------------------------------------------------------------- the fox
def build_stage(S, out_dir):
    clear_scene()
    legendary = S.get('legendary', False)
    pal = PAL_LEG if legendary else PAL
    hx, hy, hz = S['head']; L = S['body_len']; R = S['body_r']; leg = S['leg']
    sc = (hx + 0.15) / 0.43  # overall size factor
    furL = S['fur'] * 1.35

    # --- key points (fox faces -Y, +X is its left, ground z=0)
    h_t = leg + R * 0.78
    shoulder_y, hip_y = -L * 0.42, L * 0.40
    neck_base = np.array([0, -L / 2 - R * 0.05, h_t + R * 0.55])
    Hc = np.array([0, -L / 2 - hy * 0.42, h_t + R + hz * 0.78 + S['neck']])
    head_base = Hc + np.array([0, hy * 0.25, -hz * 0.55])

    body = []
    E = lambda bone, c, r, k=0.06 * sc, fur=1.0, tag="", R_=None: body.append(
        Prim('ell', bone, k, fur, tag, c=np.array(c, float), r=r, **({'R': R_} if R_ is not None else {})))
    C = lambda bone, a, b, ra, rb, k=0.05 * sc, fur=1.0, tag="": body.append(
        Prim('cap', bone, k, fur, tag, a=np.array(a, float), b=np.array(b, float), ra=ra, rb=rb))

    # torso
    E("Chest", (0, shoulder_y + R * 0.15, h_t + R * 0.06), (R * 1.0, R * 1.15, R * 1.06), fur=1.25, tag="chest")
    E("Spine", (0, (shoulder_y + hip_y) / 2, h_t), (R * 0.9, max(L * 0.42, R), R * 0.92), fur=1.1, tag="spine")
    E("Pelvis", (0, hip_y - R * 0.1, h_t + R * 0.02), (R * 0.95, R * 1.15, R * 0.95), fur=1.2, tag="hips")
    E("Chest", (0, shoulder_y - R * 0.55, h_t + R * 0.25), (R * 0.62, R * 0.42, R * 0.7), k=0.12 * sc, fur=1.9, tag="ruff")
    # neck & head
    C("Neck", neck_base, head_base, R * 0.72, hx * 0.62, k=0.09 * sc, fur=1.5, tag="neck")
    E("Head", Hc, (hx, hy, hz), k=0.07 * sc, fur=0.9, tag="head")
    for sx in (1, -1):
        E("Head", Hc + np.array([sx * hx * 0.80, hy * 0.08, -hz * 0.44]), (hx * 0.44, hy * 0.42, hz * 0.38),
          k=0.07 * sc, fur=2.6, tag="cheek")
    mz = Hc + np.array([0, -hy * 0.80 - S['muzzle'] * 0.35, -hz * 0.36])
    E("Head", mz, (hx * 0.36, hy * 0.30 + S['muzzle'] * 0.55, hz * 0.27), k=0.09 * sc, fur=0.25, tag="muzzle",
      R_=np.array(Matrix.Rotation(math.radians(-8), 3, 'X')))
    E("Head", Hc + np.array([0, -hy * 0.62, -hz * 0.62]), (hx * 0.34, hy * 0.36, hz * 0.22), k=0.07 * sc, fur=0.5,
      tag="chin")

    # legs
    bones_pts = {}
    pr = np.array(S['paw'])
    for side, sx in (("L", 1), ("R", -1)):
        x = sx * R * 0.58
        ft = np.array([x, shoulder_y, h_t - R * 0.15]); fm = np.array([x, shoulder_y + 0.02 * sc, leg * 0.55])
        fb = np.array([x, shoulder_y - 0.005, pr[2] * 0.95]); ftoe = fb + np.array([0, -pr[1] * 1.1, -pr[2] * 0.45])
        C("FrontUpper_" + side, ft, fm, R * 0.52, pr[0] * 1.12, tag="leg_front_up", fur=1.0)
        C("FrontLower_" + side, fm, fb, pr[0] * 1.12, pr[0] * 0.98, k=0.03 * sc, tag="leg_front_low", fur=0.45)
        E("FrontPaw_" + side, fb + np.array([0, -pr[1] * 0.35, -pr[2] * 0.12]), tuple(pr), k=0.04 * sc,
          tag="paw", fur=0.35)
        bt = np.array([x * 1.02, hip_y, h_t - R * 0.05]); bm = np.array([x * 1.05, hip_y - 0.06 * sc, leg * 0.52])
        bb = np.array([x * 1.03, hip_y + 0.03 * sc, pr[2] * 0.95]); btoe = bb + np.array([0, -pr[1] * 1.1, -pr[2] * 0.45])
        E("BackUpper_" + side, (x * 1.08, hip_y - 0.01, h_t - R * 0.38), (R * 0.55, R * 0.80, R * 0.82),
          k=0.07 * sc, tag="thigh", fur=1.2)
        C("BackUpper_" + side, bt, bm, R * 0.50, pr[0] * 1.18, tag="leg_back_up", fur=1.0)
        C("BackLower_" + side, bm, bb, pr[0] * 1.14, pr[0] * 0.98, k=0.03 * sc, tag="leg_back_low", fur=0.45)
        E("BackPaw_" + side, bb + np.array([0, -pr[1] * 0.35, -pr[2] * 0.12]), tuple(pr), k=0.04 * sc,
          tag="paw", fur=0.35)
        bones_pts[side] = dict(ft=ft, fm=fm, fb=fb, ftoe=ftoe, bt=bt, bm=bm, bb=bb, btoe=btoe)

    # ---- tails
    n_tails = S.get('tails', 1)
    T0 = np.array([0, hip_y + R * 0.75, h_t + R * 0.35])
    TL, TR = S['tail_len'], S['tail_r']
    tails = []
    fan = [0.0] if n_tails == 1 else [-32.0, 0.0, 32.0]
    for ti, ang in enumerate(fan):
        rot = np.array(Matrix.Rotation(math.radians(ang), 3, 'Z'))
        lift = 0.0 if n_tails == 1 else (0.12 if ang == 0 else -0.02)
        def path(s, rot=rot, lift=lift):
            local = np.array([0, TL * s * 0.92, TL * ((0.42 + lift) * s - 0.22 * s * s)])
            return T0 + local @ rot.T
        tails.append(dict(path=path, rot=rot, prefix="Tail_" if n_tails == 1 else f"Tail{'ABC'[ti]}_"))

    # ---- ears
    ears = []
    for side, sx in (("L", 1), ("R", -1)):
        base = Hc + np.array([sx * hx * 0.54, hy * 0.20, hz * 0.80])
        d = np.array([sx * 0.46, 0.06, 1.0]); d /= np.linalg.norm(d)
        tip = base + d * S['ear_h'] * 0.86
        ears.append(dict(side=side, sx=sx, base=base, tip=tip, dir=d))

    # ---- eyes
    eyes = []
    for side, sx in (("L", 1), ("R", -1)):
        dirv = np.array([sx * 0.45, -0.85, 0.16]); dirv /= np.linalg.norm(dirv)
        sp = surface_point(body, Hc, dirv)
        er = S['eye_r'] * 1.22
        center = sp - dirv * er * 0.58
        fwd = dirv * 0.45 + np.array([0, -1, 0]) * 0.55; fwd /= np.linalg.norm(fwd)
        eyes.append(dict(side=side, sx=sx, c=center, r=er, f=fwd))

    # ================================================================ armature
    arm_data = bpy.data.armatures.new(f"Fox_{S['name']}_Skeleton")
    arm = bpy.data.objects.new(f"Fox_{S['name']}_RIG", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm; arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    def bone(name, head, tail, parent=None, deform=True, connect=False):
        b = arm_data.edit_bones.new(name); b.head = Vector(head); b.tail = Vector(tail)
        if parent: b.parent = eb[parent]; b.use_connect = connect
        b.use_deform = deform; eb[name] = b
    hip_pt = np.array([0, hip_y, h_t]); mid_pt = np.array([0, (shoulder_y + hip_y) * 0.5 - L * 0.05, h_t + R * 0.05])
    sh_pt = np.array([0, shoulder_y, h_t + R * 0.1])
    bone("Root", (0, 0, 0), (0, -0.15 * sc, 0))
    bone("Pelvis", hip_pt, mid_pt, "Root")
    bone("Spine", mid_pt, sh_pt, "Pelvis", connect=True)
    bone("Chest", sh_pt, neck_base, "Spine", connect=True)
    bone("Neck", neck_base, head_base, "Chest", connect=True)
    bone("Head", head_base, Hc + np.array([0, 0, hz * 1.0]), "Neck", connect=True)
    bone("Mouth", mz + np.array([0, -S['muzzle'] * 0.55 - hy * 0.2, -hz * 0.16]),
         mz + np.array([0, -S['muzzle'] * 0.55 - hy * 0.2 - 0.05 * sc, -hz * 0.16]), "Head")
    for e in eyes:
        bone("Eye_" + e['side'], e['c'], e['c'] + e['f'] * e['r'] * 1.5, "Head")
        bone("Lid_" + e['side'], e['c'], e['c'] + e['f'] * e['r'] * 1.2, "Head")
    for e in ears:
        bone("Ear_" + e['side'], e['base'], e['tip'], "Head")
    for side, P in bones_pts.items():
        bone("FrontUpper_" + side, P['ft'], P['fm'], "Chest")
        bone("FrontLower_" + side, P['fm'], P['fb'], "FrontUpper_" + side, connect=True)
        bone("FrontPaw_" + side, P['fb'], P['ftoe'], "FrontLower_" + side, connect=True)
        bone("BackUpper_" + side, P['bt'], P['bm'], "Pelvis")
        bone("BackLower_" + side, P['bm'], P['bb'], "BackUpper_" + side, connect=True)
        bone("BackPaw_" + side, P['bb'], P['btoe'], "BackLower_" + side, connect=True)
        # IK controllers (not exported)
        bone("IK_Front_" + side, P['fb'], P['ftoe'], "Root", deform=False)
        bone("IK_Back_" + side, P['bb'], P['btoe'], "Root", deform=False)
    tail_chains = []
    for t in tails:
        names = []
        for i in range(4):
            s0, s1 = i / 4, (i + 1) / 4
            nm = f"{t['prefix']}{i + 1:02d}"
            bone(nm, t['path'](s0), t['path'](s1), "Pelvis" if i == 0 else names[-1], connect=i > 0)
            names.append(nm)
        tail_chains.append(names)
    for b in arm_data.edit_bones: b.roll = 0.0
    bpy.ops.object.mode_set(mode='OBJECT')

    deform_names = [b.name for b in arm_data.bones if b.use_deform]
    bidx = {n: i for i, n in enumerate(deform_names)}

    # ================================================================ geometry
    furmat = make_material("Fur", pal['orange'], rough=0.92)
    parts = []

    # ---- body
    res = 0.0105 * sc
    v, f = polygonize(body, res)
    v, f = simplify(v, f, 16000)
    W = ownership(body, v, 0.022 * sc)
    nB = len(deform_names)
    Wb = np.zeros((len(v), nB))
    for i, pr in enumerate(body): Wb[:, bidx[pr.bone]] += W[:, i]
    fur = furL * (W @ np.array([pr.fur for pr in body]))
    tagw = lambda tag: W[:, [i for i, p in enumerate(body) if p.tag == tag]].sum(1) if any(
        p.tag == tag for p in body) else np.zeros(len(v))
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    # base orange, darker along the back
    col = np.tile(pal['orange'], (len(v), 1))
    nrm0 = vertex_normals(v, f)
    upback = nrm0 @ (np.array([0, 0.45, 1.0]) / np.linalg.norm([0, 0.45, 1.0]))
    backness = smoothstep(h_t + R * 0.2, h_t + R * 1.0, z) * smoothstep(0.2, 0.7, upback) * (1 - tagw('head') - tagw('cheek') - tagw('muzzle') - tagw('ruff') - tagw('neck')).clip(0, 1)
    col = col * (1 - backness[:, None] * 0.6) + pal['back'] * (backness[:, None] * 0.6)
    # white face: muzzle, lower cheeks, chin
    white = np.zeros(len(v))
    rel = v - Hc
    face_low = smoothstep(-hz * 0.05, -hz * 0.35, rel[:, 2] + 0.25 * np.abs(rel[:, 0]) / hx * hz * 0.4)
    front = smoothstep(-hy * 0.1, -hy * 0.55, rel[:, 1])
    white = np.maximum(white, tagw('muzzle') * smoothstep(0.55, -0.05, (v[:, 2] - mz[2]) / (hz * 0.27) - 0.6 * (np.abs(x) / (hx * 0.36)) ** 2))
    white = np.maximum(white, tagw('chin'))
    white = np.maximum(white, tagw('cheek') * smoothstep(Hc[2] - hz * 0.25, Hc[2] - hz * 0.48, z))
    white = np.maximum(white, (tagw('head') * face_low * front))
    # chest / throat / belly
    white = np.maximum(white, tagw('ruff'))
    white = np.maximum(white, tagw('neck') * smoothstep(0.0, -0.4, (y - neck_base[1]) / R) * smoothstep(head_base[2], neck_base[2], z))
    white = np.maximum(white, tagw('chest') * smoothstep(shoulder_y - R * 0.1, shoulder_y - R * 0.75, y) * smoothstep(h_t + R * 0.5, h_t - R * 0.1, z))
    belly = smoothstep(h_t - R * 0.35, h_t - R * 0.85, z) * (tagw('spine') + tagw('chest') + tagw('hips')).clip(0, 1)
    white = np.maximum(white, belly * 0.85)
    nrm = vertex_normals(v, f)
    fd = np.array([0, -1.0, -0.45]); fd /= np.linalg.norm(fd)
    bib = (tagw('neck') + tagw('chest') + tagw('ruff')).clip(0, 1) * smoothstep(0.25, 0.65, nrm @ fd) * smoothstep(h_t - R * 0.6, h_t, z)
    white = np.maximum(white, bib)
    white = white.clip(0, 1)
    col = col * (1 - white[:, None]) + pal['white'] * white[:, None]
    # dark stockings
    is_front = (tagw('leg_front_up') + tagw('leg_front_low') + tagw('paw') * (y < 0)).clip(0, 1)
    is_back = (tagw('leg_back_up') + tagw('leg_back_low') + tagw('thigh') + tagw('paw') * (y > 0)).clip(0, 1)
    dk = (is_front * smoothstep(leg * 0.62, leg * 0.42, z) + is_back * smoothstep(leg * 0.52, leg * 0.32, z)).clip(0, 1)
    col = col * (1 - dk[:, None]) + pal['darkleg'] * dk[:, None]
    # legendary glowing stripes on flanks and legs
    if legendary:
        stripe = (np.sin(y * 38 / sc + z * 22 / sc) * 0.5 + 0.5) ** 10 * smoothstep(0.3, 0.9, np.abs(x) / R) * (1 - white)
        col = col * (1 - stripe[:, None]) + hexc('#FFF7C0') * stripe[:, None]
    # shorter fur around eyes / mouth
    for e in eyes:
        de = np.linalg.norm(v - e['c'], axis=1)
        fur *= 0.35 + 0.65 * smoothstep(e['r'] * 1.15, e['r'] * 1.9, de)
    fur *= 0.4 + 0.6 * smoothstep(0.0, 0.08 * sc, z)
    parts.append(Part("Body", v, f, col, fur, Wb, furmat, uv_density=55 / sc))

    # ---- tails
    for t, chain in zip(tails, tail_chains):
        tprims = []
        N = 22
        for i in range(N):
            s0, s1 = i / N, (i + 1) / N
            rr = lambda s: TR * (0.32 + 0.68 * math.sin(math.pi * min(1.0, s ** 0.85))) * (1 - s ** 7) + 0.004
            tprims.append(Prim('cap', chain[min(3, int(s0 * 4))], 0.03 * sc, 1.0, "tail",
                               a=t['path'](s0), b=t['path'](s1), ra=rr(s0), rb=rr(s1)))
        tv, tf = polygonize(tprims, res * 0.95)
        tv, tf = simplify(tv, tf, 5200)
        ss = np.linspace(0, 1, 400); pp = np.array([t['path'](s) for s in ss])
        near = np.argmin(((tv[:, None, :] - pp[None]) ** 2).sum(-1), 1); s_v = ss[near]
        Wt = np.zeros((len(tv), nB))
        centers = [0.125, 0.375, 0.625, 0.875]
        for k, nm in enumerate(chain):
            Wt[:, bidx[nm]] = np.clip(1 - np.abs(s_v - centers[k]) / 0.25, 0, 1)
        Wt[s_v < centers[0], bidx[chain[0]]] = 1
        Wt[s_v > centers[-1], bidx[chain[-1]]] = 1
        pel = 1 - smoothstep(0.0, 0.10, s_v)
        Wt *= (1 - pel)[:, None]; Wt[:, bidx['Pelvis']] += pel
        Wt /= Wt.sum(1, keepdims=True)
        tip = smoothstep(0.70, 0.80, s_v)
        tcol = np.tile(pal['orange'], (len(tv), 1))
        topness = smoothstep(-0.2, 1.0, vertex_normals(tv, tf)[:, 2])
        tcol = tcol * (1 - 0.35 * topness[:, None]) + pal['back'] * 0.35 * topness[:, None]
        tcol = tcol * (1 - tip[:, None]) + pal['white'] * tip[:, None]
        tfur = furL * (1.6 + 1.2 * np.sin(np.pi * np.clip(s_v, 0, 1)) ) * (1 - 0.6 * smoothstep(0.92, 1.0, s_v))
        parts.append(Part("Tail" + t['prefix'], tv, tf, tcol, tfur, Wt, furmat, uv_density=55 / sc))

    # ---- ears
    for e in ears:
        d = e['dir']; base = e['base']
        flat_axis = np.cross(d, np.array([e['sx'], 0, 0])); flat_axis /= np.linalg.norm(flat_axis)
        if flat_axis[1] > 0: flat_axis = -flat_axis  # points to the front (-Y)
        outer = Prim('cap', "Ear_" + e['side'], 0.0, a=base + d * 0.02 * sc, b=e['tip'], ra=S['ear_w'] * 1.12, rb=0.030 * sc,
                     flat=0.48, flat_axis=flat_axis)
        cav = Prim('cap', "Ear_" + e['side'], 0.025 * sc, a=base + flat_axis * S['ear_w'] * 0.32 + d * 0.03 * sc,
                   b=e['tip'] - d * 0.05 * sc + flat_axis * 0.02 * sc, ra=S['ear_w'] * 0.80, rb=0.012 * sc,
                   flat=0.30, flat_axis=flat_axis)
        ev, ef = polygonize([outer], res * 0.7, subtract=[cav], margin=0.03)
        ev, ef = simplify(ev, ef, 1800)
        inside = field(body, ev) < -0.012 * sc            # hidden inside the head → drop
        keepf = ~inside[ef].all(1)
        ef = ef[keepf]; used = np.unique(ef); rm = -np.ones(len(ev), int); rm[used] = np.arange(len(used))
        ev = ev[used]; ef = rm[ef]
        hgt = ((ev - base) @ d) / S['ear_h']
        We = np.zeros((len(ev), nB))
        we = smoothstep(0.02, 0.30, hgt)
        We[:, bidx["Ear_" + e['side']]] = we; We[:, bidx['Head']] = 1 - we
        en = vertex_normals(ev, ef)
        frontness = smoothstep(0.1, 0.6, en @ flat_axis)
        radial = np.linalg.norm((ev - base) - np.outer((ev - base) @ d, d) - np.outer((ev - base) @ flat_axis, flat_axis), axis=1)
        wloc = S['ear_w'] * 1.22 * (1 - 0.85 * hgt.clip(0, 1)) + 0.01
        inner = frontness * (1 - smoothstep(0.72, 0.9, hgt)) * smoothstep(wloc * 1.0, wloc * 0.62, radial)
        ecol = np.tile(pal['orange'], (len(ev), 1))
        ecol = ecol * (1 - inner[:, None]) + pal['earin'] * inner[:, None]
        tipd = smoothstep(0.62, 0.80, hgt) * (1 - inner)
        ecol = ecol * (1 - tipd[:, None]) + pal['dark'] * tipd[:, None]
        efur = furL * (0.35 + 2.0 * inner) * (1 - 0.7 * smoothstep(0.7, 1.0, hgt))
        parts.append(Part("Ear_" + e['side'], ev, ef, ecol, efur, We, furmat, uv_density=70 / sc))

    fur_objs = [build_object(p, arm, deform_names) for p in parts]

    # ---- eyes, glints, lids
    eyemat = make_material("Eye", pal['iris_in'], rough=0.06)
    glintmat = make_material("Glint", np.array([1, 1, 1]), rough=0.3, emit=3.0)
    lidmat = make_material("Lid", pal['orange'], rough=0.9)
    nosemat = make_material("Nose", pal['nose'], rough=0.22)
    mouthmat = make_material("Mouth", pal['mouth'], rough=0.5)
    extra = []
    up = np.array([0, 0, 1.0])
    for e in eyes:
        fwd = e['f']; side = np.cross(up, fwd); side /= np.linalg.norm(side); upv = np.cross(fwd, side)
        Rm = np.stack([side, upv, fwd], 1)  # local (x,y,z=fwd) → world
        nu, nv_ = 56, 40
        th = np.linspace(0, math.pi, nv_ + 1); ph = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        T, Pp = np.meshgrid(th, ph, indexing='ij')
        loc = np.stack([np.sin(T) * np.cos(Pp), np.sin(T) * np.sin(Pp), np.cos(T)], -1).reshape(-1, 3)
        verts = (loc * e['r']) @ Rm.T + e['c']
        faces = []
        for i in range(nv_):
            for j in range(nu):
                a = i * nu + j; b = i * nu + (j + 1) % nu; c = (i + 1) * nu + (j + 1) % nu; d_ = (i + 1) * nu + j
                faces += [(a, d_, c), (a, c, b)]
        ang = T.reshape(-1)
        iris_a, pupil_a = 1.30, 0.58
        t_ir = np.clip((ang - pupil_a) / (iris_a - pupil_a), 0, 1)
        ecol = np.tile(pal['sclera'], (len(verts), 1))
        irc = pal['iris_in'][None] * (1 - t_ir[:, None]) + pal['iris_out'][None] * t_ir[:, None]
        ecol = np.where((ang < iris_a)[:, None], irc, ecol)
        lim = smoothstep(iris_a - 0.12, iris_a - 0.02, ang) * (ang < iris_a)
        ecol = ecol * (1 - lim[:, None]) + pal['limbal'] * lim[:, None]
        ecol = np.where((ang < pupil_a)[:, None], pal['pupil'][None], ecol)
        Wt = np.zeros((len(verts), nB)); Wt[:, bidx['Eye_' + e['side']]] = 1
        extra.append(Part("Eye_" + e['side'], verts, np.array(faces), ecol, np.zeros(len(verts)), Wt, eyemat))
        gth = np.linspace(0, math.pi, 9); gph = np.linspace(0, 2 * math.pi, 14, endpoint=False)
        GT, GP = np.meshgrid(gth, gph, indexing='ij')
        gloc = np.stack([np.sin(GT) * np.cos(GP), np.sin(GT) * np.sin(GP), np.cos(GT)], -1).reshape(-1, 3)
        gfaces = np.array([(i * 14 + j, i * 14 + (j + 1) % 14, (i + 1) * 14 + (j + 1) % 14) for i in range(8) for j in range(14)] +
                          [(i * 14 + j, (i + 1) * 14 + (j + 1) % 14, (i + 1) * 14 + j) for i in range(8) for j in range(14)])
        # glints (stay put while the eye looks around → attached to Head)
        for gdir, gr in (((-0.38 * e['sx'] * 0 - 0.30, 0.42, 1.0), 0.24), ((0.28, -0.30, 1.0), 0.11)):
            g = np.array(gdir); g /= np.linalg.norm(g)
            gc = e['c'] + (g @ Rm.T) * e['r'] * 0.985
            gv = gloc * e['r'] * gr; gv[:, 2] *= 0.18
            gq = np.array(Vector((0, 0, 1)).rotation_difference(Vector(g)).to_matrix())
            gv = (gv @ gq.T) @ Rm.T + gc
            Wg = np.zeros((len(gv), nB)); Wg[:, bidx['Head']] = 1
            extra.append(Part("Glint", gv, gfaces, np.ones((len(gv), 3)), np.zeros(len(gv)), Wg, glintmat))
        # eyelid: upper cap in CLOSED position, then rotated open around eye's side axis
        lid_r = e['r'] * 1.07 * LID_REST
        mask_t = np.linspace(0, math.pi * 0.70, 22)
        T2, P2 = np.meshgrid(mask_t, ph, indexing='ij')
        # cap around local +Y(up)… build around local axis (0, 0.15, 1) tilted so it covers the front
        cap = np.stack([np.sin(T2) * np.cos(P2), np.cos(T2), np.sin(T2) * np.sin(P2)], -1).reshape(-1, 3)
        keep_front = cap[:, 2] > -0.55
        lv = cap * lid_r
        lf = []
        for i in range(len(mask_t) - 1):
            for j in range(nu):
                a = i * nu + j; b = i * nu + (j + 1) % nu; c = (i + 1) * nu + (j + 1) % nu; d_ = (i + 1) * nu + j
                if keep_front[a] and keep_front[b] and keep_front[c] and keep_front[d_]:
                    lf += [(a, b, c), (a, c, d_)]
        lv_world = lv @ Rm.T
        # rotate closed lid (covering down to just below center) open by OPEN radians
        OPEN = math.radians(98)
        q_open = Quaternion(Vector(side), OPEN)
        test = np.array(q_open.to_matrix()) @ fwd
        if test[2] < 0: q_open = Quaternion(Vector(side), -OPEN)
        e['lid_axis'] = side; e['lid_close_sign'] = -1 if test[2] >= 0 else 1
        # tilt closed cap down so that it covers the whole eye
        q_down = Quaternion(Vector(side), -math.radians(12) * (1 if test[2] >= 0 else -1))
        Mclosed = np.array(q_down.to_matrix())
        lv_world = lv_world @ Mclosed.T
        lv_open = lv_world @ np.array(q_open.to_matrix()).T + e['c']
        tt = np.repeat(mask_t, nu)
        line = smoothstep(0.075, 0.02, np.abs(tt - math.pi * 0.47)) * (cap[:, 2] > 0.0)
        lidc = pal['orange'] * 0.75 + pal['white'] * 0.25
        lcol = np.tile(lidc, (len(lv), 1)) * (1 - line[:, None]) + pal['dark'] * line[:, None]
        Wl = np.zeros((len(lv), nB)); Wl[:, bidx['Lid_' + e['side']]] = 1
        used = np.unique(np.array(lf).ravel())
        remap = -np.ones(len(lv), int); remap[used] = np.arange(len(used))
        extra.append(Part("Lid_" + e['side'], lv_open[used], remap[np.array(lf)], lcol[used], np.zeros(len(used)), Wl, lidmat))

    # nose
    nose_dir = np.array([0, -1, 0.10]); nose_dir /= np.linalg.norm(nose_dir)
    ntip = surface_point(body, mz + np.array([0, 0, hz * 0.12]), nose_dir)
    nr = np.array([0.048, 0.036, 0.034]) * sc * (1.05 if S['key'] == 'baby' else 1.0)
    nc = ntip + np.array([0, nr[1] * 0.2, 0.0])
    sph = np.stack(np.meshgrid(np.linspace(0, math.pi, 17), np.linspace(0, 2 * math.pi, 28, endpoint=False), indexing='ij'), -1).reshape(-1, 2)
    unit = np.stack([np.sin(sph[:, 0]) * np.cos(sph[:, 1]), np.sin(sph[:, 0]) * np.sin(sph[:, 1]), np.cos(sph[:, 0])], -1)
    def sphere_faces(nr_, nc_):
        fs = []
        for i in range(nr_ - 1):
            for j in range(nc_):
                a = i * nc_ + j; b = i * nc_ + (j + 1) % nc_; c = (i + 1) * nc_ + (j + 1) % nc_; d_ = (i + 1) * nc_ + j
                fs += [(a, b, c), (a, c, d_)]
        return np.array(fs)
    sf = sphere_faces(17, 28)
    nv_ = unit * nr; nv_[:, 2] -= np.clip(nv_[:, 2], None, 0) * 0.35  # flatter bottom
    nv_ = nv_ + nc
    Wn = np.zeros((len(nv_), nB)); Wn[:, bidx['Head']] = 1
    extra.append(Part("Nose", nv_, sf, np.tile(pal['nose'], (len(nv_), 1)), np.zeros(len(nv_)), Wn, nosemat))
    # smile line "ω"
    mouth_pts = []
    for u in np.linspace(-1, 1, 25):
        xx = u * hx * 0.30
        zz = nc[2] - nr[2] * 1.4 - (0.045 * sc) * (1 - abs(u)) ** 0.6 * 0.6 - 0.035 * sc * (1 - (abs(u) - 0.55) ** 2 / 0.3).clip(0, 1) * 0.0
        zz = nc[2] - nr[2] * 1.25 - 0.040 * sc * math.sin(math.pi * abs(u)) ** 0.8 + 0.02 * sc * abs(u) ** 2.5
        if abs(u) < 0.08: zz = nc[2] - nr[2] * 1.25 - 0.005 * sc
        p = surface_point(body, np.array([xx, mz[1] + hy * 0.15, zz]), np.array([0, -1, 0]))
        mouth_pts.append(p + np.array([0, -0.002, 0]))
    # vertical philtrum from nose
    tube_v, tube_f = [], []
    def tube(pts, r):
        base_i = len(tube_v); seg = 8
        for i, p in enumerate(pts):
            t_ = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]; t_ /= np.linalg.norm(t_)
            a_ = np.cross(t_, [0, -1, 0]); a_ /= np.linalg.norm(a_) + 1e-9; b_ = np.cross(t_, a_)
            for k in range(seg):
                th_ = 2 * math.pi * k / seg
                tube_v.append(p + r * (math.cos(th_) * a_ + math.sin(th_) * b_))
        for i in range(len(pts) - 1):
            for k in range(seg):
                a = base_i + i * seg + k; b = base_i + i * seg + (k + 1) % seg
                tube_f.extend([(a, b, b + seg), (a, b + seg, a + seg)])
    tube(np.array(mouth_pts), 0.0065 * sc)
    mid = mouth_pts[len(mouth_pts) // 2]
    phil = [surface_point(body, np.array([0, mz[1] + hy * 0.15, zz]), np.array([0, -1, 0])) + np.array([0, -0.002, 0])
            for zz in np.linspace(nc[2] - nr[2] * 0.7, mid[2], 5)]
    tube(np.array(phil), 0.0055 * sc)
    tv_ = np.array(tube_v); Wm = np.zeros((len(tv_), nB)); Wm[:, bidx['Head']] = 1
    extra.append(Part("Smile", tv_, np.array(tube_f), np.tile(pal['dark'], (len(tv_), 1)), np.zeros(len(tv_)), Wm, mouthmat))
    # open mouth (hidden at rest: tiny, scaled up by Mouth bone in Talk)
    mc = np.array(arm_data.bones['Mouth'].head_local)
    mv = unit * np.array([0.05, 0.02, 0.03]) * sc * 0.18 + mc
    Wmo = np.zeros((len(mv), nB)); Wmo[:, bidx['Mouth']] = 1
    mcol = np.tile(pal['mouth'], (len(mv), 1)); mcol[unit[:, 2] < -0.2] = pal['tongue']
    extra.append(Part("MouthOpen", mv, sf, mcol, np.zeros(len(mv)), Wmo, mouthmat))

    for p in extra: build_object(p, arm, deform_names)

    G = dict(h_t=h_t, L=L, R=R, leg=leg, sc=sc, eyes=eyes, tails=tail_chains, legendary=legendary)
    return arm, G

# ================================================================ animation
def q_arm(rx=0, ry=0, rz=0):
    return Euler((math.radians(rx), math.radians(ry), math.radians(rz)), 'XYZ').to_quaternion()

def set_rot(pb, q):
    Rr = pb.bone.matrix_local.to_quaternion()
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = Rr.inverted() @ q @ Rr

def set_loc(pb, v):
    Rr = pb.bone.matrix_local.to_3x3()
    pb.location = Rr.inverted() @ Vector(v)

def wave(t, phase=0.0):
    return math.sin(2 * math.pi * (t + phase))

def ease(x):
    x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)

def lerp(a, b, t): return a + (b - a) * t

class Pose(dict):
    """bone -> dict(r=(rx,ry,rz) armature-axes degrees, l=(x,y,z))"""
    def r(self, bone, rx=0, ry=0, rz=0):
        e = self.setdefault(bone, {}); o = e.get('r', (0, 0, 0)); e['r'] = (o[0] + rx, o[1] + ry, o[2] + rz); return self
    def l(self, bone, x=0, y=0, z=0):
        e = self.setdefault(bone, {}); o = e.get('l', (0, 0, 0)); e['l'] = (o[0] + x, o[1] + y, o[2] + z); return self
    def s(self, bone, sx=1, sy=1, sz=1):
        self.setdefault(bone, {})['s'] = (sx, sy, sz); return self

def apply_pose(arm, pose, G):
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.scale = (1, 1, 1)
    root_l = pose.get('Root', {}).get('l', (0, 0, 0))
    for name, e in pose.items():
        pb = arm.pose.bones.get(name)
        if pb is None: continue
        if 'r' in e: set_rot(pb, q_arm(*e['r']))
        l = e.get('l')
        if name.startswith('IK_'):  # feet given in ground space → compensate root motion
            l = tuple((l or (0, 0, 0))[i] - root_l[i] for i in range(3))
        if l: set_loc(pb, l)
        if 's' in e:
            pb.scale = e['s']
    bpy.context.view_layer.update()

# --- base poses ------------------------------------------------------------
def tail_pose(p, G, rots, wag=0.0, lift=0.0, curl=0.0):
    """rots: list of 4 (rx,ry,rz); wag/curl in degrees distributed along the chain."""
    n = len(G['tails'])
    for ci, chain in enumerate(G['tails']):
        spread = 0 if n == 1 else (ci - 1) * 6
        for i, bn in enumerate(chain):
            rx, ry, rz = rots[i] if rots else (0, 0, 0)
            ph = 0.12 * i + 0.07 * ci
            p.r(bn, rx + lift * (1 if i == 0 else 0.3), ry, rz + wag * (0.6 + 0.35 * i) * (1 if callable(wag) is False else 1) + curl + spread * (i == 0))
    return p

def stand(G):
    return Pose()

def sit(G, p=None):
    p = p or Pose(); L, leg, R, sc = G['L'], G['leg'], G['R'], G['sc']
    ang = 34
    drop = leg * 0.55 + R * 0.25
    p.l('Root', z=-drop)
    p.r('Pelvis', rx=-ang)
    p.r('Neck', rx=ang * 1.05); p.r('Head', rx=ang * 0.05)
    # hind feet stay below hips, slightly forward
    for s, sx in (('L', 1), ('R', -1)):
        p.l('IK_Back_' + s, y=-L * 0.22 - leg * 0.25, z=0.0)
        p.r('IK_Back_' + s, rx=0)
    p['_front_under_shoulder'] = True
    tail_pose(p, G, [(-18, 0, -38), (8, 0, -34), (6, 0, -30), (0, 0, -24)])
    return p

def lie(G, p=None):
    p = p or Pose(); L, leg, R = G['L'], G['leg'], G['R']
    drop = G['h_t'] - R * 0.92
    p.l('Root', z=-drop)
    for s, sx in (('L', 1), ('R', -1)):
        p.l('IK_Front_' + s, x=-sx * R * 0.08, y=-leg * 0.95, z=0.0); p.r('IK_Front_' + s, rx=0)
        p.l('IK_Back_' + s, x=sx * R * 0.25, y=-leg * 0.55, z=0.0); p.r('IK_Back_' + s, rx=0)
    return p

def finish_front_feet(arm, p, G, lift_extra=None):
    """Two-pass: put front paws on the ground under the (moved) shoulders."""
    if not p.get('_front_under_shoulder'): return
    apply_pose(arm, {k: v for k, v in p.items() if not k.startswith('_')}, G)
    root_l = p.get('Root', {}).get('l', (0, 0, 0))
    for s in ('L', 'R'):
        sh = arm.pose.bones['FrontUpper_' + s].head
        rest_foot = arm.data.bones['IK_Front_' + s].head_local
        dy = sh.y + root_l[1] - rest_foot.y + G['L'] * 0.02
        e = p.setdefault('IK_Front_' + s, {})
        ol = e.get('l', (0, 0, 0))
        e['l'] = (ol[0], ol[1] + dy, ol[2])

def clean(p): return {k: v for k, v in p.items() if not k.startswith('_')}

# --- clips -----------------------------------------------------------------
def clip_defs(G):
    L, leg, R, sc = G['L'], G['leg'], G['R'], G['sc']
    def idle(t):
        p = Pose(); b = wave(t)
        p.r('Spine', rx=1.2 * b); p.r('Chest', rx=-1.5 * b); p.r('Head', rx=2 * wave(t, .2), rz=4 * math.sin(2 * math.pi * t), ry=3 * wave(t * 1, .5))
        ear = max(0, math.sin(2 * math.pi * (t * 2 - 0.55))) ** 8
        p.r('Ear_L', rx=-14 * ear); p.r('Ear_R', ry=0)
        tail_pose(p, G, [(4 + 3 * b, 0, 0)] * 4, wag=10 * wave(t))
        return p
    def sitc(t):
        p = sit(G); b = wave(t)
        p.r('Chest', rx=-1.5 * b); p.r('Head', rz=5 * math.sin(2 * math.pi * t), rx=2 * wave(t, .25), ry=-4 * wave(t, .1))
        ear = max(0, math.sin(2 * math.pi * (t * 2 - 0.3))) ** 8
        p.r('Ear_R', rx=-14 * ear)
        for ci, ch in enumerate(G['tails']):
            for i, bn in enumerate(ch): p.r(bn, rz=6 * wave(t, 0.1 * i) * (0.4 + 0.3 * i))
        return p
    def walk(t, run=False):
        p = Pose(); A = leg * (0.42 if run else 0.30); H = leg * (0.30 if run else 0.20)
        stance = 0.45 if run else 0.6
        phases = {'Front_L': 0.0, 'Back_R': 0.0, 'Front_R': 0.5, 'Back_L': 0.5} if not run else \
                 {'Front_L': 0.0, 'Front_R': 0.1, 'Back_L': 0.5, 'Back_R': 0.6}
        for k, ph in phases.items():
            u = (t + ph) % 1.0
            if u < stance:
                y = lerp(-A, A, u / stance); z = 0; rx = 0
            else:
                w = (u - stance) / (1 - stance); y = lerp(A, -A, ease(w)); z = H * math.sin(math.pi * w); rx = 55 * math.sin(math.pi * w)
            p.l('IK_' + k, y=y, z=z); p.r('IK_' + k, rx=rx)
        bob = (0.035 if run else 0.012) * leg / 0.37 * (abs(math.sin(2 * math.pi * t)) if run else math.cos(4 * math.pi * t))
        p.l('Root', z=bob)
        if run:
            p.r('Pelvis', rx=7 * wave(t, 0.25)); p.r('Chest', rx=-6 * wave(t, 0.25)); p.r('Head', rx=-6 * wave(t, .25))
            p.r('Ear_L', rx=-20); p.r('Ear_R', rx=-20)
        else:
            p.r('Pelvis', rz=3 * wave(t)); p.r('Chest', rz=-3 * wave(t)); p.r('Head', rx=-2 * math.cos(4 * math.pi * t), rz=2 * wave(t))
        tail_pose(p, G, [(10 if run else 4, 0, 0)] * 4, wag=(6 if run else 12) * wave(t, 0.2))
        return p
    def jump(t):
        p = Pose(); hgt = leg * 0.9
        if t < 0.25: c = ease(t / 0.25); z = -leg * 0.22 * c; feet = 0
        elif t < 0.38: c = (t - 0.25) / 0.13; z = lerp(-leg * 0.22, hgt * 0.55, ease(c)); feet = ease(c)
        elif t < 0.72: c = (t - 0.38) / 0.34; z = hgt * 0.55 + hgt * 0.45 * math.sin(math.pi * c); feet = 1
        elif t < 0.85: c = (t - 0.72) / 0.13; z = lerp(hgt * 0.55, -leg * 0.18, ease(c)); feet = 1 - ease(c)
        else: c = (t - 0.85) / 0.15; z = lerp(-leg * 0.18, 0, ease(c)); feet = 0
        p.l('Root', z=z)
        for s in ('L', 'R'):
            p.l('IK_Front_' + s, y=-leg * 0.25 * feet, z=max(z, 0) + leg * 0.30 * feet); p.r('IK_Front_' + s, rx=60 * feet)
            p.l('IK_Back_' + s, y=leg * 0.25 * feet, z=max(z, 0) + leg * 0.25 * feet); p.r('IK_Back_' + s, rx=-50 * feet)
        air = 1 if 0.3 < t < 0.8 else 0
        p.r('Pelvis', rx=-10 * math.sin(math.pi * min(1, max(0, (t - 0.25) / 0.6))))
        p.r('Head', rx=-10 * air); p.r('Ear_L', rx=-25 * air); p.r('Ear_R', rx=-25 * air)
        tail_pose(p, G, [(25 * air - 10 * (1 - air), 0, 0)] * 4)
        return p
    def sleep(t):
        p = lie(G); b = wave(t)
        p.r('Pelvis', rz=6); p.r('Spine', rz=6, rx=1.5 * b); p.r('Chest', rx=4)
        p.r('Neck', rx=6, rz=10); p.r('Head', rx=-4, rz=10, ry=-10 + 1.5 * b)
        p.r('Ear_L', rx=-28); p.r('Ear_R', rx=-28)
        tail_pose(p, G, [(-30, 0, -30), (-4, 0, -40), (0, 0, -42), (0, 0, -38)])
        p.s('Spine', 1 + 0.025 * b, 1, 1 + 0.025 * b)
        for e in G['eyes']: p['Lid_' + e['side']] = {'r_axis': (e['lid_axis'], e['lid_close_sign'] * 84)}
        return p
    def react(t):
        p = sit(G); hop = math.sin(math.pi * min(1, t / 0.45)) if t < 0.45 else 0
        p.l('Root', z=leg * 0.18 * hop)
        p.r('Head', rx=-14 * hop, rz=10 * math.sin(2 * math.pi * t))
        p.r('Ear_L', rx=18 * hop); p.r('Ear_R', rx=18 * hop)
        for ch in G['tails']:
            for i, bn in enumerate(ch): p.r(bn, rz=24 * math.sin(2 * math.pi * 3 * t + i * 0.5) * (1 - t) , rx=15 * hop)
        return p
    def happy(t):
        p = sit(G)
        p.r('Head', rz=10 * math.sin(2 * math.pi * t), ry=14 + 4 * math.sin(2 * math.pi * t), rx=-6)
        p.r('Ear_L', rx=-22, ry=-8); p.r('Ear_R', rx=-22, ry=8)
        for ch in G['tails']:
            for i, bn in enumerate(ch): p.r(bn, rz=18 * math.sin(2 * math.pi * 2 * t + i * 0.6))
        for e in G['eyes']: p['Lid_' + e['side']] = {'r_axis': (e['lid_axis'], e['lid_close_sign'] * 80)}
        return p
    def eat(t):
        p = Pose(); nib = abs(math.sin(2 * math.pi * 2 * t))
        p.r('Chest', rx=8); p.r('Neck', rx=34); p.r('Head', rx=12 + 7 * nib)
        for s in ('L', 'R'): p.l('IK_Front_' + s, y=-leg * 0.08)
        p.r('Ear_L', rx=10); p.r('Ear_R', rx=10)
        tail_pose(p, G, [(6, 0, 0)] * 4, wag=8 * wave(t))
        return p
    def stretch(t):
        p = Pose()
        k = ease(t / 0.3) if t < 0.3 else (1 if t < 0.7 else 1 - ease((t - 0.7) / 0.3))
        p.l('Root', z=-leg * 0.08 * k)
        p.r('Pelvis', rx=24 * k); p.r('Chest', rx=6 * k); p.r('Neck', rx=-30 * k); p.r('Head', rx=-14 * k)
        for s in ('L', 'R'): p.l('IK_Front_' + s, y=-leg * 0.55 * k); p.r('IK_Front_' + s, rx=-10 * k)
        p.r('Ear_L', rx=-20 * k); p.r('Ear_R', rx=-20 * k)
        tail_pose(p, G, [(30 * k, 0, 0)] * 4, wag=6 * wave(t * 2))
        return p
    def wagc(t):
        p = idle(t)
        for ch in G['tails']:
            for i, bn in enumerate(ch): p.r(bn, rz=28 * math.sin(2 * math.pi * 2 * t + i * 0.6), rx=14)
        p.r('Ear_L', rx=8); p.r('Ear_R', rx=8)
        return p
    def blink(t):
        k = math.sin(math.pi * t)
        p = Pose()
        for e in G['eyes']: p['Lid_' + e['side']] = {'r_axis': (e['lid_axis'], e['lid_close_sign'] * 98 * k)}
        return p
    def talk(t):
        k = abs(math.sin(2 * math.pi * t))
        return Pose().s('Mouth', 1 + 4.5 * k, 1 + 2.5 * k, 1 + 5.5 * k)

    base_ex = {'Mouth', 'Eye_L', 'Eye_R', 'Lid_L', 'Lid_R'}
    lids = {'Lid_L', 'Lid_R'}
    return [  # name, frames, func, loop, bone filter (None = all except base_ex)
        ("Idle", 96, idle, True, None),
        ("Sit", 96, sitc, True, None),
        ("Walk", 24, walk, True, None),
        ("Run", 14, lambda t: walk(t, True), True, None),
        ("Jump", 26, jump, False, None),
        ("Sleep", 96, sleep, True, lids),
        ("React", 26, react, False, None),
        ("Happy", 48, happy, True, lids),
        ("Eat", 24, eat, True, None),
        ("Stretch", 48, stretch, False, None),
        ("Wag", 24, wagc, True, None),
        ("Blink", 6, blink, False, 'ONLY_LIDS'),
        ("Talk", 12, talk, True, 'ONLY_MOUTH'),
    ], base_ex

def add_ik(arm):
    for s in ('L', 'R'):
        for limb in ('Front', 'Back'):
            low = arm.pose.bones[f"{limb}Lower_{s}"]
            c = low.constraints.new('IK'); c.target = arm; c.subtarget = f"IK_{limb}_{s}"; c.chain_count = 2
            paw = arm.pose.bones[f"{limb}Paw_{s}"]
            cr = paw.constraints.new('COPY_TRANSFORMS'); cr.target = arm; cr.subtarget = f"IK_{limb}_{s}"

def remove_ik(arm):
    for pb in arm.pose.bones:
        for c in list(pb.constraints): pb.constraints.remove(c)

def apply_pose_full(arm, p, G):
    # special: lid rotations around arbitrary axis
    p = Pose(p)
    lid_axes = {}
    for k in list(p.keys()):
        if isinstance(p[k], dict) and 'r_axis' in p[k]:
            lid_axes[k] = p.pop(k)['r_axis']
    finish_front_feet(arm, p, G)
    apply_pose(arm, clean(p), G)
    for k, (axis, deg) in lid_axes.items():
        pb = arm.pose.bones[k]
        set_rot(pb, Quaternion(Vector(axis), math.radians(deg)))
        k_ = min(1.0, abs(deg) / 25.0)
        sc_ = 1.0 + (1.0 / LID_REST - 1.0) * k_
        pb.scale = (sc_, sc_, sc_)
    bpy.context.view_layer.update()

def bake_clips(arm, G, prefix):
    clips, base_ex = clip_defs(G)
    deform = [pb for pb in arm.pose.bones if pb.bone.use_deform]
    add_ik(arm)
    baked = []
    for name, frames, fn, loop, filt in clips:
        data = []
        n = frames + 1
        for fi in range(n):
            t = fi / frames
            if loop: t = t % 1.0 if fi < frames else 0.0
            apply_pose_full(arm, fn(t), G)
            data.append({pb.name: arm.convert_space(pose_bone=pb, matrix=pb.matrix, from_space='POSE', to_space='LOCAL').copy()
                         for pb in deform})
        if filt == 'ONLY_LIDS': keep = {'Lid_L', 'Lid_R'}
        elif filt == 'ONLY_MOUTH': keep = {'Mouth'}
        else: keep = {pb.name for pb in deform} - base_ex | (filt or set())
        baked.append((name, n, data, keep, loop))
    remove_ik(arm)
    if arm.animation_data is None: arm.animation_data_create()
    meta = {}
    for name, n, data, keep, loop in baked:
        act = bpy.data.actions.new(f"{prefix}_{name}")
        arm.animation_data.action = act
        for fi in range(n):
            for bn in keep:
                pb = arm.pose.bones[bn]
                pb.rotation_mode = 'QUATERNION'
                pb.matrix_basis = data[fi][bn]
                pb.keyframe_insert("location", frame=fi + 1)
                pb.keyframe_insert("rotation_quaternion", frame=fi + 1)
                pb.keyframe_insert("scale", frame=fi + 1)
        tr = arm.animation_data.nla_tracks.new(); tr.name = act.name
        st = tr.strips.new(act.name, 1, act); st.name = act.name
        arm.animation_data.action = None
        meta[act.name] = dict(clip=name, loop=loop, bones=sorted(keep))
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.scale = (1, 1, 1)
    return meta

# ================================================================ export + post-process
def export_glb(arm, path):
    for ob in bpy.context.scene.objects: ob.select_set(ob == arm or ob.parent == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.context.scene.render.fps = FPS
    kw = dict(filepath=path, export_format='GLB', use_selection=True, export_animations=True,
              export_skins=True, export_def_bones=True, export_yup=True, export_apply=False,
              export_animation_mode='NLA_TRACKS', export_force_sampling=True,
              export_cameras=False, export_lights=False, export_materials='EXPORT')
    try:
        bpy.ops.export_scene.gltf(**kw, export_vertex_color='ACTIVE', export_all_vertex_colors=False)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)

def read_glb(path):
    b = open(path, 'rb').read()
    jl = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl = struct.unpack('<I', b[off:off + 4])[0]
    return j, b[off + 8: off + 8 + bl]

def write_glb(path, j, binb):
    js = json.dumps(j, separators=(',', ':')).encode()
    js += b' ' * ((4 - len(js) % 4) % 4)
    binb += b'\0' * ((4 - len(binb) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(binb)
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, total))
        fh.write(struct.pack('<II', len(js), 0x4E4F534A)); fh.write(js)
        fh.write(struct.pack('<II', len(binb), 0x004E4942)); fh.write(binb)

def postprocess(path, meta, stage_info):
    j, binb = read_glb(path)
    node_name = {i: n.get('name') for i, n in enumerate(j['nodes'])}
    for an in j.get('animations', []):
        m = meta.get(an['name'])
        if not m: continue
        keep_ch, keep_s = [], []
        for ch in an['channels']:
            if node_name.get(ch['target'].get('node')) in m['bones']:
                ch2 = dict(ch); keep_s.append(an['samplers'][ch['sampler']]); ch2['sampler'] = len(keep_s) - 1
                keep_ch.append(ch2)
        an['channels'], an['samplers'] = keep_ch, keep_s
        an.setdefault('extras', {})['loop'] = m['loop']
    # compact: keep only referenced accessors
    used = set()
    for me in j['meshes']:
        for p in me['primitives']:
            used |= set(p['attributes'].values())
            if 'indices' in p: used.add(p['indices'])
    for sk in j.get('skins', []):
        if 'inverseBindMatrices' in sk: used.add(sk['inverseBindMatrices'])
    for an in j.get('animations', []):
        for s in an['samplers']: used |= {s['input'], s['output']}
    imgs_bv = {im['bufferView'] for im in j.get('images', []) if 'bufferView' in im}
    new_acc, amap, new_bv, out = [], {}, [], bytearray()
    bvmap = {}
    for bvi in sorted(imgs_bv):
        bv = j['bufferViews'][bvi]; data = binb[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']]
        while len(out) % 4: out += b'\0'
        nb = dict(bv); nb['byteOffset'] = len(out); out += data; bvmap[bvi] = len(new_bv); new_bv.append(nb)
    comp = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    ncomp = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
    for ai, acc in enumerate(j['accessors']):
        if ai not in used: continue
        bv = j['bufferViews'][acc['bufferView']]
        esize = comp[acc['componentType']] * ncomp[acc['type']]
        stride = bv.get('byteStride', esize)
        start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
        if stride == esize: data = binb[start:start + esize * acc['count']]
        else: data = b''.join(binb[start + i * stride: start + i * stride + esize] for i in range(acc['count']))
        while len(out) % 4: out += b'\0'
        nb = {'buffer': 0, 'byteOffset': len(out), 'byteLength': len(data)}
        if 'target' in bv: nb['target'] = bv['target']
        out += data
        a2 = dict(acc); a2['bufferView'] = len(new_bv); a2.pop('byteOffset', None)
        new_bv.append(nb); amap[ai] = len(new_acc); new_acc.append(a2)
    for me in j['meshes']:
        for p in me['primitives']:
            p['attributes'] = {k: amap[v] for k, v in p['attributes'].items()}
            if 'indices' in p: p['indices'] = amap[p['indices']]
    for sk in j.get('skins', []):
        if 'inverseBindMatrices' in sk: sk['inverseBindMatrices'] = amap[sk['inverseBindMatrices']]
    for an in j.get('animations', []):
        for s in an['samplers']: s['input'] = amap[s['input']]; s['output'] = amap[s['output']]
    for im in j.get('images', []):
        if 'bufferView' in im: im['bufferView'] = bvmap[im['bufferView']]
    j['accessors'], j['bufferViews'] = new_acc, new_bv
    j['buffers'] = [{'byteLength': len(out)}]
    j.setdefault('asset', {})['extras'] = stage_info
    write_glb(path, j, bytes(out))

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports'))
    ap.add_argument('--stages', default='1,2,3,4,5')
    ap.add_argument('--blend', action='store_true', help='also save editable .blend per stage')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    for si in [int(s) for s in a.stages.split(',')]:
        S = STAGES[si - 1]
        arm, G = build_stage(S, a.out)
        prefix = f"Fox_{S['name']}"
        meta = bake_clips(arm, G, prefix)
        path = os.path.join(a.out, f"fox_stage_{si}_{S['key']}.glb")
        export_glb(arm, path)
        info = dict(stage=si, key=S['key'], clips=[m['clip'] for m in meta.values()],
                    furLength=S['fur'], legendary=bool(S.get('legendary')))
        postprocess(path, meta, info)
        if a.blend: bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, f"fox_stage_{si}.blend"))
        print(f"OK stage {si}: {path} ({os.path.getsize(path) // 1024} KB)")

if __name__ == '__main__':
    main()
