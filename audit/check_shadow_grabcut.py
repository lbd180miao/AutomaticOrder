import cv2,numpy as np,json,sqlite3,time
from pathlib import Path
c=sqlite3.connect('file:db.sqlite3?mode=ro',uri=True);r=c.execute('select roi_config,standard_template_config from vision_visionrecipe where id=11').fetchone();roi,t=map(json.loads,r);im=cv2.imread(str(Path('media')/t['source_image_path']));small=cv2.resize(im,(1280,853));h,w=small.shape[:2]
reference=np.zeros((h,w),np.uint8)
for key in ['leftFoamROI','rightFoamROI']:
 v=roi[key]
 if v.get('type')=='polygon':cv2.fillPoly(reference,[np.rint(np.array(v['points'])*[w,h]).astype(np.int32)],255)
 else:cv2.rectangle(reference,(round(v['x1r']*w),round(v['y1r']*h)),(round(v['x2r']*w),round(v['y2r']*h)),255,-1)
gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY);area=cv2.dilate(reference,np.ones((31,31),np.uint8))>0
m=np.full((h,w),cv2.GC_BGD,np.uint8);m[area]=cv2.GC_PR_BGD;m[(reference>0)&(gray>35)]=cv2.GC_PR_FGD
inner=cv2.erode(reference,np.ones((21,21),np.uint8))>0;m[inner&(gray>=110)]=cv2.GC_FGD;m[gray<30]=cv2.GC_BGD
t=time.perf_counter();cv2.grabCut(small,m,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK);print(time.perf_counter()-t)
sel=(m==cv2.GC_FGD)|(m==cv2.GC_PR_FGD);out=small.copy();out[sel]=(out[sel]*.55+np.array([0,0,255])*.45).astype(np.uint8);cv2.imwrite('audit/shadow_grabcut.jpg',out)
