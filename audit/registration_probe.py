import json,sqlite3,time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

def sample(p,voxel=3):
    p=p[np.isfinite(p).all(1)&(p[:,2]>0)]
    cells,inv=np.unique(np.floor(p/voxel),axis=0,return_inverse=True)
    n=np.bincount(inv)
    return np.column_stack([np.bincount(inv,weights=p[:,i])/n for i in range(3)])

def register(srcs,dsts):
    srcs=[sample(x) for x in srcs];dsts=[sample(x) for x in dsts]
    trees=[cKDTree(x) for x in dsts]
    norms=[]
    for p,t in zip(dsts,trees):
        idx=t.query(p,k=min(20,len(p)))[1];nbr=p[idx];q=nbr-nbr.mean(1)[:,None,:]
        _,v=np.linalg.eigh(np.einsum('nki,nkj->nij',q,q));norms.append(v[:,:,0])
    T=np.eye(4);pivot=np.concatenate(srcs).mean(0)
    for it in range(35):
        rows=[];res=[];weights=[]
        for p,tree,q,n in zip(srcs,trees,dsts,norms):
            x=p@T[:3,:3].T+T[:3,3];dd,ii=tree.query(x);mask=dd<15
            x=x[mask];y=q[ii[mask]];nn=n[ii[mask]]
            e=np.einsum('ij,ij->i',nn,x-y)
            # Huber robust loss, balanced region weights.
            w=np.minimum(1,1.0/np.maximum(abs(e),1e-8))/max(1,len(e))
            rows.append(np.column_stack([np.cross(x-pivot,nn),nn]));res.append(e);weights.append(w)
        A=np.concatenate(rows);e=np.concatenate(res);w=np.sqrt(np.concatenate(weights));step=np.linalg.lstsq(A*w[:,None],-e*w,rcond=None)[0]
        R=Rotation.from_rotvec(step[:3]).as_matrix();inc=np.eye(4);inc[:3,:3]=R;inc[:3,3]=pivot-R@pivot+step[3:];T=inc@T
        if np.linalg.norm(step[3:])<.0001 and np.linalg.norm(step[:3])<1e-7:break
    return T,{'iterations':it+1,'residual':float(np.sqrt(np.mean(e**2))),'condition':float(np.linalg.cond(A)))}

if __name__=='__main__':
    c=sqlite3.connect('db.sqlite3');rows={r[0]:(r[1],json.loads(r[2])) for r in c.execute('select id,raw_data_path,result_data from vision_racklocationresult where id between 361 and 367')}
    rois=rows[364][1]['local_template_rois']
    def parts(pk):
        p=np.load(Path('media')/rows[pk][0]);return [p[r['y']:r['y']+r['h'],r['x']:r['x']+r['w']].reshape(-1,3) for r in rois.values()]
    std=parts(364);C=np.array(rows[365][1]['robot_groups']['B']['T_base_camera'])
    for pk in rows:
        cur=parts(pk)
        for key,idx in [('A',0),('B',2)]:
            t=time.monotonic();T,stats=register([std[idx],std[1]],[cur[idx],cur[1]]);B=C@T@np.linalg.inv(C)
            print(pk,key,'xyz',np.round(B[:3,3],3),'rot',np.round(Rotation.from_matrix(B[:3,:3]).as_euler('xyz',degrees=True),4),stats,'sec',round(time.monotonic()-t,2),flush=True)
