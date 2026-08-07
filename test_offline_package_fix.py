"""
测试离线数据包管理修复
用于验证标准数据包和原始数据包都能正常工作
"""

import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

import numpy as np
from pathlib import Path
from apps.vision.offline_data_service import OfflineDataPackageService, OfflineDataPackageError


def test_list_packages():
    """测试列出所有数据包（包括原始数据包）"""
    print("\n" + "="*60)
    print("测试 1: 列出所有数据包")
    print("="*60)
    
    service = OfflineDataPackageService()
    
    try:
        packages = service.list_packages(include_raw=True)
        print(f"✅ 成功列出 {len(packages)} 个数据包")
        
        for pkg in packages[:5]:  # 只显示前5个
            pkg_type = "原始数据包" if pkg.get('is_raw') else "标准数据包"
            print(f"  - {pkg['package_name']}: {pkg_type} | {pkg.get('recipe_name', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def test_raw_package_detail():
    """测试获取原始数据包详情"""
    print("\n" + "="*60)
    print("测试 2: 获取原始数据包详情")
    print("="*60)
    
    service = OfflineDataPackageService()
    
    try:
        packages = service.list_packages(include_raw=True)
        raw_packages = [p for p in packages if p.get('is_raw')]
        
        if not raw_packages:
            print("⚠️ 未找到原始数据包，跳过测试")
            return True
        
        test_package = raw_packages[0]['package_name']
        print(f"测试数据包: {test_package}")
        
        detail = service.package_detail(test_package)
        print(f"✅ 成功获取详情")
        print(f"  - 类型: {'原始数据包' if detail.get('is_raw') else '标准数据包'}")
        print(f"  - 点云点数: {detail.get('point_count', 'N/A')}")
        print(f"  - 配方名: {detail.get('recipe_name', 'N/A')}")
        
        return True
    except OfflineDataPackageError as e:
        print(f"❌ 失败 (OfflineDataPackageError): {e}")
        return False
    except Exception as e:
        print(f"❌ 失败 (其他错误): {e}")
        import traceback
        traceback.print_exc()
        return False


def test_standard_package_detail():
    """测试获取标准数据包详情"""
    print("\n" + "="*60)
    print("测试 3: 获取标准数据包详情")
    print("="*60)
    
    service = OfflineDataPackageService()
    
    try:
        packages = service.list_packages(include_raw=True)
        standard_packages = [p for p in packages if not p.get('is_raw')]
        
        if not standard_packages:
            print("⚠️ 未找到标准数据包，跳过测试")
            return True
        
        test_package = standard_packages[0]['package_name']
        print(f"测试数据包: {test_package}")
        
        detail = service.package_detail(test_package)
        print(f"✅ 成功获取详情")
        print(f"  - 类型: {'原始数据包' if detail.get('is_raw') else '标准数据包'}")
        print(f"  - 点云点数: {detail.get('point_count', 'N/A')}")
        print(f"  - 配方名: {detail.get('recipe_name', 'N/A')}")
        print(f"  - 位置: POS{detail.get('position_no', 'N/A')}")
        print(f"  - 层: L{detail.get('layer_no', 'N/A')}")
        
        return True
    except OfflineDataPackageError as e:
        print(f"❌ 失败 (OfflineDataPackageError): {e}")
        return False
    except Exception as e:
        print(f"❌ 失败 (其他错误): {e}")
        import traceback
        traceback.print_exc()
        return False


def test_load_raw_package():
    """测试加载原始数据包"""
    print("\n" + "="*60)
    print("测试 4: 加载原始数据包")
    print("="*60)
    
    service = OfflineDataPackageService()
    
    try:
        packages = service.list_packages(include_raw=True)
        raw_packages = [p for p in packages if p.get('is_raw')]
        
        if not raw_packages:
            print("⚠️ 未找到原始数据包，跳过测试")
            return True
        
        test_package = raw_packages[0]['package_name']
        print(f"测试数据包: {test_package}")
        
        package = service.load_raw_package(test_package)
        print(f"✅ 成功加载原始数据包")
        print(f"  - 点云形状: {package['pointcloud'].shape}")
        print(f"  - 手眼矩阵形状: {package['hand_eye_matrix'].shape}")
        print(f"  - 机器人位姿矩阵形状: {package['robot_pose_matrix'].shape}")
        
        return True
    except OfflineDataPackageError as e:
        print(f"❌ 失败 (OfflineDataPackageError): {e}")
        return False
    except Exception as e:
        print(f"❌ 失败 (其他错误): {e}")
        import traceback
        traceback.print_exc()
        return False


def test_preview_retrieval():
    """测试预览图获取"""
    print("\n" + "="*60)
    print("测试 5: 预览图获取")
    print("="*60)
    
    service = OfflineDataPackageService()
    
    try:
        packages = service.list_packages(include_raw=True)
        
        success_count = 0
        fail_count = 0
        
        for pkg in packages[:5]:  # 测试前5个
            package_name = pkg['package_name']
            is_raw = pkg.get('is_raw')
            
            try:
                if is_raw:
                    preview_path = service.get_raw_preview(package_name)
                else:
                    preview_path = service.preview_path(package_name)
                
                if preview_path.is_file():
                    print(f"  ✅ {package_name}: 找到预览图 ({preview_path.name})")
                    success_count += 1
                else:
                    print(f"  ⚠️ {package_name}: 预览图路径无效")
                    fail_count += 1
            except OfflineDataPackageError:
                print(f"  ⚠️ {package_name}: 未找到预览图")
                fail_count += 1
        
        print(f"\n✅ 成功: {success_count}, 失败/未找到: {fail_count}")
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("离线数据包管理修复测试")
    print("="*60)
    
    tests = [
        test_list_packages,
        test_raw_package_detail,
        test_standard_package_detail,
        test_load_raw_package,
        test_preview_retrieval,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("✅ 所有测试通过！")
    else:
        print(f"⚠️ {total - passed} 个测试失败")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
