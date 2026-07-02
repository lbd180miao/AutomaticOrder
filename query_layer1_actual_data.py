"""
查询第1层的历史记录，显示真实坐标值
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationResult
from django.db.models import Avg, StdDev, Count
import numpy as np

print("=" * 80)
print("第1层历史记录 - 真实坐标数据分析")
print("=" * 80)

# 查询第1层的所有记录
layer1_results = RackLocationResult.objects.filter(layer_no=1).order_by('-created_at')

total_count = layer1_results.count()
print(f"\n📊 第1层总记录数: {total_count}")

if total_count == 0:
    print("\n⚠️  没有找到第1层的历史记录")
    sys.exit(0)

print("\n" + "=" * 80)
print("最近10条记录:")
print("=" * 80)
print(f"{'ID':<6} {'时间':<20} {'POS':<5} {'Actual X':<12} {'Actual Y':<12} {'Actual Z':<12} {'置信度':<8} {'状态':<6}")
print("-" * 80)

recent_records = []
for result in layer1_results[:10]:
    # 判断状态：is_success字段或根据error_code判断
    status = "OK" if result.is_success else "NG"
    print(f"{result.id:<6} {str(result.created_at)[:19]:<20} {result.position_no:<5} "
          f"{result.actual_x:<12.3f} {result.actual_y:<12.3f} {result.actual_z:<12.3f} "
          f"{result.confidence:<8.3f} {status:<6}")
    
    recent_records.append({
        'id': result.id,
        'actual_x': float(result.actual_x),
        'actual_y': float(result.actual_y),
        'actual_z': float(result.actual_z),
        'confidence': float(result.confidence),
        'position_no': result.position_no,
    })

# 统计分析
print("\n" + "=" * 80)
print("统计分析（所有第1层记录）:")
print("=" * 80)

# 收集所有第1层的数据
all_x = []
all_y = []
all_z = []

for result in layer1_results:
    all_x.append(float(result.actual_x))
    all_y.append(float(result.actual_y))
    all_z.append(float(result.actual_z))

if all_x:
    print(f"\n📐 Actual X 坐标:")
    print(f"   中位数 (Median): {np.median(all_x):.3f} mm")
    print(f"   平均值 (Mean):   {np.mean(all_x):.3f} mm")
    print(f"   标准差 (StdDev): {np.std(all_x):.3f} mm")
    print(f"   最小值 (Min):    {np.min(all_x):.3f} mm")
    print(f"   最大值 (Max):    {np.max(all_x):.3f} mm")
    print(f"   范围 (Range):    {np.max(all_x) - np.min(all_x):.3f} mm")

    print(f"\n📐 Actual Y 坐标:")
    print(f"   中位数 (Median): {np.median(all_y):.3f} mm")
    print(f"   平均值 (Mean):   {np.mean(all_y):.3f} mm")
    print(f"   标准差 (StdDev): {np.std(all_y):.3f} mm")
    print(f"   最小值 (Min):    {np.min(all_y):.3f} mm")
    print(f"   最大值 (Max):    {np.max(all_y):.3f} mm")
    print(f"   范围 (Range):    {np.max(all_y) - np.min(all_y):.3f} mm")

    print(f"\n📐 Actual Z 坐标:")
    print(f"   中位数 (Median): {np.median(all_z):.3f} mm")
    print(f"   平均值 (Mean):   {np.mean(all_z):.3f} mm")
    print(f"   标准差 (StdDev): {np.std(all_z):.3f} mm")
    print(f"   最小值 (Min):    {np.min(all_z):.3f} mm")
    print(f"   最大值 (Max):    {np.max(all_z):.3f} mm")
    print(f"   范围 (Range):    {np.max(all_z) - np.min(all_z):.3f} mm")

# 按POS分组统计
print("\n" + "=" * 80)
print("按 POS 分组统计:")
print("=" * 80)

positions = layer1_results.values('position_no').distinct().order_by('position_no')
for pos_dict in positions:
    pos = pos_dict['position_no']
    pos_results = layer1_results.filter(position_no=pos)
    
    pos_x = [float(r.actual_x) for r in pos_results]
    pos_y = [float(r.actual_y) for r in pos_results]
    pos_z = [float(r.actual_z) for r in pos_results]
    
    if pos_x:
        print(f"\n📍 POS{pos} (共 {len(pos_x)} 条记录):")
        print(f"   Actual X: 中位数={np.median(pos_x):.3f}, 平均={np.mean(pos_x):.3f}, 标准差={np.std(pos_x):.3f}")
        print(f"   Actual Y: 中位数={np.median(pos_y):.3f}, 平均={np.mean(pos_y):.3f}, 标准差={np.std(pos_y):.3f}")
        print(f"   Actual Z: 中位数={np.median(pos_z):.3f}, 平均={np.mean(pos_z):.3f}, 标准差={np.std(pos_z):.3f}")

# 查看配方的标准坐标
print("\n" + "=" * 80)
print("配方标准坐标对比:")
print("=" * 80)

from apps.vision.models import RackLocationRecipe
recipes = RackLocationRecipe.objects.filter(layer_no=1, enabled=True).order_by('position_no')

for recipe in recipes:
    print(f"\n🎯 配方: {recipe.recipe_name} (POS{recipe.position_no}, Layer{recipe.layer_no})")
    print(f"   标准坐标: X={recipe.standard_x}, Y={recipe.standard_y}, Z={recipe.standard_z}")
    
    # 查找该配方对应的实际测量值
    recipe_results = layer1_results.filter(position_no=recipe.position_no)
    if recipe_results.exists():
        recipe_x = [float(r.actual_x) for r in recipe_results]
        recipe_y = [float(r.actual_y) for r in recipe_results]
        recipe_z = [float(r.actual_z) for r in recipe_results]
        
        median_x = np.median(recipe_x)
        median_y = np.median(recipe_y)
        median_z = np.median(recipe_z)
        
        print(f"   实际测量 (中位数): X={median_x:.3f}, Y={median_y:.3f}, Z={median_z:.3f}")
        print(f"   偏差 (实际-标准): ΔX={median_x - float(recipe.standard_x):.3f}, "
              f"ΔY={median_y - float(recipe.standard_y):.3f}, ΔZ={median_z - float(recipe.standard_z):.3f}")

# 数据分布可视化（简单的ASCII图）
print("\n" + "=" * 80)
print("数据分布可视化 (Actual X):")
print("=" * 80)

if all_x:
    min_x = np.min(all_x)
    max_x = np.max(all_x)
    bins = 10
    hist, bin_edges = np.histogram(all_x, bins=bins)
    
    max_count = max(hist)
    scale = 50 / max_count if max_count > 0 else 1
    
    for i in range(bins):
        bar_len = int(hist[i] * scale)
        bar = '█' * bar_len
        print(f"[{bin_edges[i]:8.2f} - {bin_edges[i+1]:8.2f}] {bar} ({hist[i]})")

print("\n" + "=" * 80)
print("✅ 分析完成")
print("=" * 80)

# 输出关键结论
if all_x:
    print("\n🎯 关键结论:")
    print(f"   第1层历史记录中，真实坐标的中位数为:")
    print(f"   • Actual X (中位数): {np.median(all_x):.3f} mm")
    print(f"   • Actual Y (中位数): {np.median(all_y):.3f} mm")
    print(f"   • Actual Z (中位数): {np.median(all_z):.3f} mm")
    print(f"\n   这些值是从点云ROI区域内所有有效点的XYZ坐标计算的中位数。")
