"""快速检查 ROI 质量的脚本"""
import numpy as np
from apps.vision.models import RackLocationRecipe, RackLocationResult
from apps.vision.rack_location import RackLocationService
from apps.vision import rack_spatial as spatial

# 配置
RECIPE_ID = 8
RESULT_ID = 376  # 或者最新的结果 ID

# 加载数据
recipe = RackLocationRecipe.objects.get(pk=RECIPE_ID)
result = RackLocationResult.objects.get(pk=RESULT_ID)
service = RackLocationService()

cloud = service._load_workbench_pointcloud(result.raw_data_path)
rois = recipe.roi_config.get('spatial_rois', {})

print(f"\n检查配方 #{RECIPE_ID} 的 ROI 质量\n" + "="*60)

# 提取各 ROI 的点云
regions = spatial.extract(cloud, rois)

for name in ['plane1', 'plane2', 'plane3']:
    label = {'plane1': 'Π1 顶部横梁', 'plane2': 'Π2 左侧立柱', 'plane3': 'Π3 底部横梁'}[name]
    points = regions[name]
    
    print(f"\n【{label}】")
    print(f"  点数: {len(points)}")
    
    # 计算空间跨度
    span = points.max(0) - points.min(0)
    print(f"  空间跨度 XYZ: {span[0]:.1f} × {span[1]:.1f} × {span[2]:.1f} mm")
    
    # 拟合轴线
    center = points.mean(0)
    cov = np.cov((points - center).T)
    values = np.linalg.eigvalsh(cov)
    vectors = np.linalg.eigh(cov)[1]
    direction = vectors[:, -1]
    
    # 计算质量指标
    variance_ratio = values[-1] / max(values[-2], 1e-6)
    residuals = np.linalg.norm(np.cross(points - center, direction), axis=1)
    rms = np.sqrt(np.mean(residuals**2))
    linearity = 1 - values[-2] / values[-1]
    
    print(f"  方差比: {variance_ratio:.2f} (应该 > 10)")
    print(f"  RMS 误差: {rms:.1f} mm (应该 < 20)")
    print(f"  线性度: {linearity:.3f} (应该 > 0.95)")
    
    # 判断
    if variance_ratio < 5:
        print(f"  ❌ 方差比太低！ROI 可能包含多个构件或形状不够狭长")
    if rms > 30:
        print(f"  ❌ RMS 误差太大！点云可能包含噪声、弯曲或多个表面")
    if linearity < 0.90:
        print(f"  ❌ 线性度太低！拟合的不是直线，检查是否包含弯曲部分")
    
    if variance_ratio >= 10 and rms <= 20 and linearity >= 0.95:
        print(f"  ✓ 质量良好")

print("\n" + "="*60)
print("\n建议:")
print("1. 如果方差比低：缩小 ROI，只框选单一构件的直线段")
print("2. 如果 RMS 大：避开焊缝、螺栓、弯曲部分")
print("3. 如果线性度低：确保 ROI 沿着构件轴线方向延伸")
print("4. 确保 Π1 和 Π3 是横梁，Π2 是立柱")
print("\n重新框选后，再次运行此脚本检查。\n")
