"""
修复大偏差问题 - 增强版算法，添加详细调试信息
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')

import django
django.setup()


def add_debug_logging():
    """在算法中添加详细的调试日志"""
    
    algo_file = "apps/vision/rack_positioning_algorithm.py"
    
    print("=" * 70)
    print("增强料架定位算法 - 添加详细调试信息")
    print("=" * 70)
    
    enhancements = """
修改建议:

1. 在 detect_support_plane() 方法中添加:
   - 打印输入点云的范围和数量
   - 打印检测到的平面参数
   - 打印Z位置的计算过程

2. 在 detect_front_edge() 方法中添加:
   - 打印输入点云的Y坐标范围
   - 打印边缘点的数量和位置
   - 打印Y位置的计算过程

3. 在 detect_pillar() 方法中添加:
   - 打印输入点云的X坐标范围
   - 打印立柱点的数量和位置
   - 打印X位置的计算过程

4. 在 calculate_rack_position() 方法中添加:
   - 打印每个ROI裁剪后的点云数量
   - 如果点云数量为0，给出警告
   - 打印最终的实际值和偏差值
    """
    
    print(enhancements)
    print("\n正在应用增强...")
    
    # 读取文件
    with open(algo_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # 在detect_support_plane开始处添加日志
        if 'def detect_support_plane(' in line and not modified:
            # 找到下一个方法体的开始
            for j in range(i+1, min(i+20, len(lines))):
                if '"""' in lines[j] or '\'\'\'':
                    # 跳过文档字符串
                    continue
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    # 在方法开始添加日志
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    debug_code = ' ' * indent + 'self.logger.debug(f"[detect_support_plane] 输入点云: {pointcloud.shape[0]}点, Z范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}]")\n'
                    new_lines.insert(len(new_lines), debug_code)
                    modified = True
                    break
    
    if modified:
        # 备份原文件
        backup_file = algo_file + ".backup"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"✓ 已备份原文件到: {backup_file}")
        
        # 写入修改后的文件
        with open(algo_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"✓ 已添加调试日志")
    else:
        print("⚠️  未找到合适的插入位置，请手动添加日志")


def create_enhanced_diagnostic_view():
    """创建增强的诊断视图"""
    
    print("\n=" * 70)
    print("创建诊断API端点")
    print("=" * 70)
    
    diagnostic_code = '''
@require_POST
@csrf_exempt
def api_rack_locator_diagnose(request):
    """
    诊断料架定位 - 返回详细的中间结果
    """
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        data = json.loads(request.body)
        token = data.get('pointcloud_token')
        recipe_id = data.get('recipe_id')
        
        if not token:
            return JsonResponse({'success': False, 'error': '缺少点云token'}, status=400)
        
        # 加载点云
        service = RackLocationService()
        pointcloud = service._load_workbench_pointcloud(token)
        
        logger.info(f"[诊断] 加载点云: {pointcloud.shape}")
        logger.info(f"[诊断] X范围: [{pointcloud[:, 0].min():.2f}, {pointcloud[:, 0].max():.2f}]")
        logger.info(f"[诊断] Y范围: [{pointcloud[:, 1].min():.2f}, {pointcloud[:, 1].max():.2f}]")
        logger.info(f"[诊断] Z范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}]")
        
        # 获取配方
        recipe = None
        if recipe_id:
            recipe = RackLocationRecipe.objects.get(pk=recipe_id)
            logger.info(f"[诊断] 配方标准值: X={recipe.standard_x}, Y={recipe.standard_y}, Z={recipe.standard_z}")
        
        # 返回诊断信息
        return JsonResponse({
            'success': True,
            'diagnostic': {
                'pointcloud_shape': pointcloud.shape,
                'pointcloud_stats': {
                    'x_min': float(pointcloud[:, 0].min()),
                    'x_max': float(pointcloud[:, 0].max()),
                    'x_mean': float(pointcloud[:, 0].mean()),
                    'y_min': float(pointcloud[:, 1].min()),
                    'y_max': float(pointcloud[:, 1].max()),
                    'y_mean': float(pointcloud[:, 1].mean()),
                    'z_min': float(pointcloud[:, 2].min()),
                    'z_max': float(pointcloud[:, 2].max()),
                    'z_mean': float(pointcloud[:, 2].mean()),
                },
                'recipe': {
                    'standard_x': float(recipe.standard_x) if recipe else None,
                    'standard_y': float(recipe.standard_y) if recipe else None,
                    'standard_z': float(recipe.standard_z) if recipe else None,
                } if recipe else None
            }
        })
        
    except Exception as e:
        logger.exception("[诊断] 失败")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
'''
    
    print("将以下代码添加到 apps/vision/views.py:")
    print(diagnostic_code)
    
    print("\n将以下URL添加到 apps/vision/urls.py:")
    print("    path('api/rack/diagnose/', views.api_rack_locator_diagnose, name='api_rack_locator_diagnose'),")


def create_validation_checks():
    """创建验证检查"""
    
    print("\n=" * 70)
    print("添加数据验证检查")
    print("=" * 70)
    
    validation_code = """
在 rack_positioning_algorithm.py 的 calculate_rack_position() 方法开始添加:

        # 验证输入点云
        if support_plane_cloud.shape[0] == 0:
            self.logger.warning("⚠️  支撑面点云为空！检查ROI裁剪是否正确")
            result.error_message = "支撑面ROI裁剪后点云为空"
            
        if front_edge_cloud.shape[0] == 0:
            self.logger.warning("⚠️  前边缘点云为空！检查ROI裁剪是否正确")
            result.error_message = "前边缘ROI裁剪后点云为空"
            
        if pillar_cloud.shape[0] == 0:
            self.logger.warning("⚠️  立柱点云为空！检查ROI裁剪是否正确")
            result.error_message = "立柱ROI裁剪后点云为空"
        
        # 打印点云统计信息
        self.logger.info(f"[综合定位] 输入点云统计:")
        self.logger.info(f"  支撑面: {support_plane_cloud.shape[0]}点")
        if support_plane_cloud.shape[0] > 0:
            self.logger.info(f"    Z范围: [{support_plane_cloud[:, 2].min():.2f}, {support_plane_cloud[:, 2].max():.2f}]")
            
        self.logger.info(f"  前边缘: {front_edge_cloud.shape[0]}点")
        if front_edge_cloud.shape[0] > 0:
            self.logger.info(f"    Y范围: [{front_edge_cloud[:, 1].min():.2f}, {front_edge_cloud[:, 1].max():.2f}]")
            
        self.logger.info(f"  立柱: {pillar_cloud.shape[0]}点")
        if pillar_cloud.shape[0] > 0:
            self.logger.info(f"    X范围: [{pillar_cloud[:, 0].min():.2f}, {pillar_cloud[:, 0].max():.2f}]")
    """
    
    print(validation_code)


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  修复大偏差问题 - 诊断和优化工具")
    print("=" * 70)
    
    print("\n根据诊断结果，问题的根本原因是:")
    print("  实际测量值(actual_x/y/z)接近0，导致:")
    print("  offset = actual - standard ≈ 0 - standard = -standard")
    print(f"  即: offset_x ≈ -899mm, offset_y ≈ -530mm, offset_z ≈ -920mm")
    print()
    print("可能的原因:")
    print("  1. ROI裁剪失败，点云被过滤掉了")
    print("  2. 点云坐标系错误，点云不在预期位置")
    print("  3. 3D ROI参数配置错误")
    print()
    
    # 提供修复方案
    print("修复方案:")
    print("\n方案1: 检查ROI配置")
    print("  1. 打开工作台，采集点云")
    print("  2. 检查点云预览图，确认点云可见")
    print("  3. 绘制ROI时，确保框选了目标特征区域")
    print("  4. 检查3D ROI参数是否合理（不要设置过小的范围）")
    
    print("\n方案2: 添加诊断日志")
    add_debug_logging()
    
    print("\n方案3: 创建诊断接口")
    create_enhanced_diagnostic_view()
    
    print("\n方案4: 添加验证检查")
    create_validation_checks()
    
    print("\n=" * 70)
    print("  下一步操作")
    print("=" * 70)
    print("""
1. **立即检查**: 在工作台中:
   - 采集点云后，查看控制台日志
   - 检查点云统计信息（点数、范围）
   - 确认3D ROI参数是否合理

2. **调整ROI**: 如果点云被过滤:
   - 放宽3D ROI的X/Y/Z范围
   - 例如: X: [-500, 500], Y: [-500, 500], Z: [-200, 200]

3. **检查坐标系**: 确认:
   - 点云是否已转换到机器人基坐标系
   - 手眼标定是否正确
   - 点云坐标的单位是否是mm

4. **查看日志**: 在Django日志中查找:
   - "[综合定位] 输入点云统计"
   - "⚠️  xxx点云为空"
   - 确认哪个步骤出问题
    """)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
