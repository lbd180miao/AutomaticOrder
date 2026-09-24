import inspect
import numpy as np
import PyRVC as RVC

print("=== SystemFindDevice signature ===")
try:
    print(inspect.signature(RVC.SystemFindDevice))
except Exception as e:
    print("sig err:", e)
print(inspect.getdoc(RVC.SystemFindDevice))

print("=== X1.Create sig ===")
print(inspect.getdoc(RVC.X1.Create))
print("=== X1.Open ===")
print(inspect.getdoc(RVC.X1.Open))
print("=== X1.Capture ===")
print(inspect.getdoc(RVC.X1.Capture))
print("=== X1.GetPointMap ===")
print(inspect.getdoc(RVC.X1.GetPointMap))
print("=== X1.GetImage ===")
print(inspect.getdoc(RVC.X1.GetImage))

print("=== PointMapCreate ===")
print(inspect.getdoc(RVC.PointMapCreate))
print("=== PointMap.Save ===")
print(inspect.getdoc(RVC.PointMap.Save))
print("=== PointMap.GetSize ===")
print(inspect.getdoc(RVC.PointMap.GetSize))
print("=== PointMap.GetNormalDataPtr ===")
print(inspect.getdoc(RVC.PointMap.GetNormalDataPtr))

print("=== DepthMap methods ===")
print([m for m in dir(RVC.DepthMap) if not m.startswith("_")])
print("=== Image methods doc ===")
print(inspect.getdoc(RVC.Image.SaveImage))
print(inspect.getdoc(RVC.ImageCreate))
print("=== Size ===")
print([m for m in dir(RVC.Size) if not m.startswith("_")])

# Try creating a synthetic point map and inspecting data access
try:
    pm = RVC.PointMapCreate(4, 3, RVC.PointMapTypeEnum.PointsOnly)
    print("created pm:", pm, "valid:", pm.IsValid())
    sz = pm.GetSize()
    print("size:", sz, type(sz), [a for a in dir(sz) if not a.startswith("_")])
    print("size values:", getattr(sz, "width", None), getattr(sz, "height", None))
    ptr = pm.GetNormalDataPtr()
    print("normal ptr:", ptr)
    arr = np.array(pm, copy=False)
    print("np.array shape:", arr.shape, arr.dtype)
except Exception as e:
    print("synthetic pm err:", e)
