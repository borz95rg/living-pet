import os, glob, json, struct, math
import numpy as np
ROOT='/mnt/data/foxwork/living pet'
MODEL_DIR=os.path.join(ROOT,'app/src/main/assets/models')

def read_glb(path):
    b=open(path,'rb').read(); magic,ver,total=struct.unpack_from('<4sII',b,0)
    assert magic==b'glTF' and ver==2
    pos=12; chunks=[]
    while pos<len(b):
        n,typ=struct.unpack_from('<I4s',b,pos); pos+=8
        chunks.append((typ,b[pos:pos+n])); pos+=n
    j=json.loads(next(d for t,d in chunks if t==b'JSON'))
    bin_data=bytearray(next(d for t,d in chunks if t==b'BIN\x00'))
    return j,bin_data

def write_glb(path,j,bin_data):
    jd=json.dumps(j,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    jd+=b' '*((4-len(jd)%4)%4)
    bd=bytes(bin_data); bd+=b'\x00'*((4-len(bd)%4)%4)
    total=12+8+len(jd)+8+len(bd)
    with open(path,'wb') as f:
        f.write(struct.pack('<4sII',b'glTF',2,total)); f.write(struct.pack('<I4s',len(jd),b'JSON')); f.write(jd)
        f.write(struct.pack('<I4s',len(bd),b'BIN\x00')); f.write(bd)

def accessor_array(j,bin_data,acc_idx):
    a=j['accessors'][acc_idx]; bv=j['bufferViews'][a['bufferView']]
    assert a['componentType']==5126 and a['type']=='VEC3'
    stride=bv.get('byteStride',12); start=bv.get('byteOffset',0)+a.get('byteOffset',0)
    count=a['count']; arr=np.empty((count,3),dtype=np.float32)
    for i in range(count): arr[i]=struct.unpack_from('<3f',bin_data,start+i*stride)
    return arr,start,stride,a

def put_array(bin_data,arr,start,stride):
    for i,row in enumerate(arr): struct.pack_into('<3f',bin_data,start+i*stride,*map(float,row))

def patch_one(path):
    j,bd=read_glb(path)
    # Map mesh names to their unique POSITION/NORMAL accessors.
    mesh_by_name={m.get('name',''):m for m in j.get('meshes',[])}
    report={}
    for name,scale in [('Eye_L',0.86),('Eye_R',0.86),('Glint',0.90),('Glint.001',0.90),('Glint.002',0.90),('Glint.003',0.90),('Lid_L',0.94),('Lid_R',0.94)]:
        m=mesh_by_name.get(name)
        if not m: continue
        prim=m['primitives'][0]; ai=prim['attributes']['POSITION']
        v,start,stride,a=accessor_array(j,bd,ai)
        center=v.mean(axis=0)
        v=center+(v-center)*scale
        put_array(bd,v,start,stride)
        a['min']=v.min(axis=0).astype(float).tolist(); a['max']=v.max(axis=0).astype(float).tolist()
        # Recompute normals for scaled spherical parts by inverse-transpose scale.
        ni=prim['attributes'].get('NORMAL')
        if ni is not None:
            n,ns,nstride,na=accessor_array(j,bd,ni)
            n=n/scale; n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-9)
            put_array(bd,n,ns,nstride)
        report[name]=scale
    # Refine head silhouette in the skinned body: slightly narrower temples,
    # fuller lower cheek line. Weight fades smoothly into neck/ruff.
    m=mesh_by_name.get('Body')
    if m:
        prim=m['primitives'][0]; ai=prim['attributes']['POSITION']
        v,start,stride,a=accessor_array(j,bd,ai)
        x,y,z=v.T
        # Head vertices are forward (+Y) and high (+Z). Do not touch the ears or muzzle tip.
        wy=np.clip((y-0.60)/0.22,0,1); wz=np.clip((z-0.25)/0.22,0,1)
        w=(wy*wy*(3-2*wy))*(wz*wz*(3-2*wz))
        # A 5% narrower upper head removes the spherical/helmet look.
        v[:,0]*=(1.0-0.055*w)
        # Gently broaden lower cheeks only, preserving the centerline and nose.
        cheek=np.clip((z-0.20)/0.18,0,1)*(1-np.clip((z-0.48)/0.20,0,1))*np.clip((y-0.66)/0.18,0,1)
        v[:,0]*=(1.0+0.025*cheek)
        put_array(bd,v,start,stride)
        a['min']=v.min(axis=0).astype(float).tolist(); a['max']=v.max(axis=0).astype(float).tolist()
        # Recalculate body normals from existing normal vectors under mild x scaling.
        ni=prim['attributes'].get('NORMAL')
        if ni is not None:
            n,ns,nstride,na=accessor_array(j,bd,ni)
            n[:,0]*=1.04; n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-9)
            put_array(bd,n,ns,nstride)
        report['Body_head']='temple taper + soft cheek fullness'
    write_glb(path,j,bd)
    return report

for p in sorted(glob.glob(os.path.join(MODEL_DIR,'*.glb'))):
    print(os.path.basename(p),patch_one(p))
