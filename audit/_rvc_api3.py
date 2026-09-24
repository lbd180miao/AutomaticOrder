import numpy as np
import PyRVC as RVC

print("Size ctor:", end=" ")
try:
    s = RVC.Size(4, 3)
except Exception:
    s = RVC.Size()
    s.width = 4
    s.height = 3
print("w,h =", s.width, s.height, "rows,cols =", s.rows, s.cols)

pm = RVC.PointMapCreate(RVC.PointMapTypeEnum.PointsOnly, s)
print("pm valid:", pm.IsValid(), "size:", pm.GetSize().width, pm.GetSize().height)

# buffer protocol?
for name, obj in [("PointMap", pm)]:
    try:
        arr = np.array(obj, copy=False)
        print(name, "np.array:", arr.shape, arr.dtype)
    except Exception as e:
        print(name, "np.array err:", e)
    try:
        arr = np.frombuffer(obj, dtype=np.float32)
        print(name, "frombuffer:", arr.shape)
    except Exception as e:
        print(name, "frombuffer err:", e)

nd = pm.GetNormalDataPtr()
print("NormalData:", nd, type(nd))
print("NormalData attrs:", [a for a in dir(nd) if not a.startswith("_")])

# Image
it = RVC.ImageTypeEnum.RGB8
img = RVC.ImageCreate(it, s)
print("img valid:", img.IsValid(), "type:", img.GetType())
try:
    arr = np.array(img, copy=False)
    print("Image np.array:", arr.shape, arr.dtype)
except Exception as e:
    print("Image np.array err:", e)
for a in dir(img):
    if not a.startswith("_"):
        print("  img attr:", a)
