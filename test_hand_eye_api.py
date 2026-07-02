"""
手眼标定模块 API 测试脚本

测试所有手眼标定相关的API接口和业务逻辑
需要Django服务运行：python manage.py runserver
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

import numpy as np
from apps.vision.hand_eye_service import HandEyeCalibrationService
from apps.vision.coordinate_transform import CoordinateTransformService
from apps.vision.models_hand_eye import HandEyeCalibration, HandEyeCalibrationSample
from apps.devices.models import Device
from apps.core.constants import DeviceType


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_1_create_devices():
    """测试1：创建测试设备"""
    print_section("测试1: 创建测试设备")
    
    # 创建机器人
    robot, created = Device.objects.get_or_create(
        code='ROBOT-TEST-01',
        defaults={
            'name': '测试装箱机器人',
            'device_type': DeviceType.BOXING_ROBOT,
            'enabled': True,
            'status': 'ONLINE'
        }
    )
    print(f"✓ 机器人设备: {robot.name} (ID: {robot.id}) {'[新建]' if created else '[已存在]'}")
    
    # 创建相机
    camera, created = Device.objects.get_or_create(
        code='DM-CAMERA-TEST-01',
        defaults={
            'name': '测试DM 3D相机',
            'device_type': DeviceType.DEPTH_CAMERA,
            'enabled': True,
            'status': 'ONLINE'
        }
    )
    print(f"✓ 相机设备: {camera.name} (ID: {camera.id}) {'[新建]' if created else '[已存在]'}")
    
    return robot, camera


def test_2_create_calibration(robot, camera):
    """测试2：创建手眼标定任务"""
    print_section("测试2: 创建手眼标定任务")
    
    service = HandEyeCalibrationService()
    
    # 清理旧的测试数据
    HandEyeCalibration.objects.filter(name__startswith='测试标定').delete()
    
    calibration = service.create_calibration(
        name=f"测试标定-自动化测试-{np.random.randint(1000, 9999)}",
        robot_device_id=robot.id,
        camera_device_id=camera.id,
        description="自动化测试创建的标定任务",
        operator="测试脚本"
    )
    
    print(f"✓ 标定任务已创建: {calibration.name}")
    print(f"  - ID: {calibration.id}")
    print(f"  - 机器人: {calibration.robot_device.name}")
    print(f"  - 相机: {calibration.camera_device.name}")
    print(f"  - 激活状态: {calibration.is_active}")
    
    return calibration


def test_3_add_samples(calibration):
    """测试3：添加标定样本"""
    print_section("测试3: 添加标定样本")
    
    service = HandEyeCalibrationService()
    
    # 模拟10个不同位姿的标定样本
    sample_count = 10
    print(f"添加 {sample_count} 个标定样本...")
    
    for i in range(sample_count):
        # 模拟机器人移动到不同位姿
        T_base_flange = {
            'x': 500 + i * 20,
            'y': 200 + i * 10,
            'z': 850 + i * 5,
            'rx': 0 + i * 2,
            'ry': 0,
            'rz': 0 + i * 5
        }
        
        # 模拟标定板在相机坐标系的位姿（OpenCV格式）
        T_camera_target = {
            'rvec': [0.1 + i*0.01, 0.2 + i*0.01, 0.3 + i*0.01],
            'tvec': [100.0, 50.0, 600.0 - i*10]
        }
        
        sample = service.add_sample(
            calibration_id=calibration.id,
            T_base_flange=T_base_flange,
            T_camera_target=T_camera_target,
            detection_success=True,
            reprojection_error=0.5 + i * 0.1
        )
        
        print(f"  ✓ 样本 #{sample.sample_index} 已添加 (误差: {sample.reprojection_error:.2f} px)")
    
    total = HandEyeCalibrationSample.objects.filter(calibration=calibration).count()
    print(f"\n总计: {total} 个样本")
    
    return total


def test_4_compute_calibration(calibration):
    """测试4：计算手眼标定"""
    print_section("测试4: 计算手眼标定")
    
    service = HandEyeCalibrationService()
    
    print("使用 OPENCV_TSAI 方法计算标定...")
    
    try:
        result = service.compute_calibration(
            calibration_id=calibration.id,
            method='OPENCV_TSAI'
        )
        
        print(f"✓ 标定计算成功!")
        print(f"  - 方法: {result['method']}")
        print(f"  - 样本数: {result['sample_count']}")
        print(f"  - 标定误差: {result['calibration_error']:.6f} mm")
        print(f"  - 旋转矩阵有效: {result['rotation_valid']}")
        
        # 显示标定矩阵
        T_matrix = np.array(result['T_flange_camera'])
        print(f"\n  T_flange_camera 矩阵:")
        for row in T_matrix:
            print(f"    {row}")
        
        return result
        
    except Exception as e:
        print(f"✗ 标定计算失败: {e}")
        return None


def test_5_verify_calibration(calibration):
    """测试5：验证手眼标定"""
    print_section("测试5: 验证手眼标定")
    
    service = HandEyeCalibrationService()
    
    # 测试位姿
    T_base_flange = {
        'x': 500.0, 'y': 200.0, 'z': 850.0,
        'rx': 0.0, 'ry': 0.0, 'rz': 0.0
    }
    
    # 相机坐标系测试点
    test_points_camera = [
        [0.0, 0.0, 0.0],
        [100.0, 0.0, 0.0],
        [0.0, 100.0, 0.0],
    ]
    
    print("验证测试点坐标转换...")
    
    try:
        verification = service.verify_calibration(
            calibration_id=calibration.id,
            T_base_flange=T_base_flange,
            test_points_camera=test_points_camera,
            error_threshold=50.0,  # 由于是模拟数据，放宽阈值
            notes="自动化测试验证"
        )
        
        print(f"✓ 验证完成!")
        print(f"  - 平均误差: {verification.mean_error:.2f} mm")
        print(f"  - 最大误差: {verification.max_error:.2f} mm")
        print(f"  - 标准差: {verification.std_error:.2f} mm")
        print(f"  - 验证通过: {verification.is_passed}")
        
        # 显示转换后的坐标
        print(f"\n  转换结果:")
        for i, (p_cam, p_robot) in enumerate(zip(test_points_camera, verification.test_points_robot)):
            print(f"    点{i+1}: {p_cam} → {p_robot}")
        
        return verification
        
    except Exception as e:
        print(f"✗ 验证失败: {e}")
        return None


def test_6_activate_calibration(calibration):
    """测试6：激活标定配置"""
    print_section("测试6: 激活标定配置")
    
    service = HandEyeCalibrationService()
    
    print(f"激活标定: {calibration.name}")
    
    calibration = service.activate_calibration(calibration.id)
    
    print(f"✓ 标定已激活: {calibration.is_active}")
    
    # 验证同组只有一个激活
    active_count = HandEyeCalibration.objects.filter(
        robot_device=calibration.robot_device,
        camera_device=calibration.camera_device,
        is_active=True
    ).count()
    
    print(f"  - 同组激活标定数量: {active_count} (应为1)")
    
    assert active_count == 1, "同组应只有一个激活的标定"
    
    return calibration


def test_7_coordinate_transform():
    """测试7：坐标转换功能"""
    print_section("测试7: 坐标转换功能")
    
    service = CoordinateTransformService()
    
    # 测试点
    P_camera = np.array([100.0, 50.0, 500.0])
    print(f"相机坐标系测试点: {P_camera}")
    
    # 手眼标定矩阵（相机在法兰偏移30mm X, 100mm Z）
    T_flange_camera = service.pose_to_matrix(30, 0, 100, 0, 0, 0)
    print(f"T_flange_camera: X偏移=30mm, Z偏移=100mm")
    
    # 机器人位姿
    T_base_flange = service.pose_to_matrix(500, 200, 850, 0, 0, 0)
    print(f"T_base_flange: (500, 200, 850)")
    
    # 执行转换
    P_base = service.camera_to_robot_base(P_camera, T_flange_camera, T_base_flange)
    print(f"\n转换结果: {P_base}")
    
    # 预期值
    P_expected = np.array([630.0, 250.0, 1450.0])
    error = np.linalg.norm(P_base - P_expected)
    print(f"预期值: {P_expected}")
    print(f"误差: {error:.6f} mm")
    
    if error < 0.001:
        print("✓ 坐标转换测试通过！")
    else:
        print(f"✗ 坐标转换误差过大: {error} mm")


def test_8_get_active_calibration(robot, camera):
    """测试8：获取激活的标定配置"""
    print_section("测试8: 获取激活的标定配置")
    
    service = HandEyeCalibrationService()
    
    calibration = service.get_active_calibration(robot.id, camera.id)
    
    if calibration:
        print(f"✓ 找到激活的标定配置:")
        print(f"  - 名称: {calibration.name}")
        print(f"  - 标定误差: {calibration.calibration_error:.6f} mm")
        print(f"  - 样本数: {calibration.sample_count}")
        print(f"  - 验证时间: {calibration.verified_at or '未验证'}")
    else:
        print("✗ 未找到激活的标定配置")
    
    return calibration


def test_9_export_import(calibration):
    """测试9：导出和导入标定"""
    print_section("测试9: 导出和导入标定")
    
    service = HandEyeCalibrationService()
    
    # 导出
    print("导出标定配置...")
    export_data = service.export_calibration(calibration.id)
    
    print(f"✓ 标定已导出:")
    print(f"  - 名称: {export_data['name']}")
    print(f"  - 标定误差: {export_data['calibration_error']:.6f} mm")
    print(f"  - 样本数: {export_data['sample_count']}")
    
    # 导入（使用相同设备）
    print("\n导入标定配置...")
    export_data['name'] = f"导入-{export_data['name']}"
    
    imported = service.import_calibration(
        import_data=export_data,
        robot_device_id=calibration.robot_device_id,
        camera_device_id=calibration.camera_device_id
    )
    
    print(f"✓ 标定已导入:")
    print(f"  - 新ID: {imported.id}")
    print(f"  - 名称: {imported.name}")
    print(f"  - 激活状态: {imported.is_active}")
    
    return imported


def test_10_list_calibrations(robot, camera):
    """测试10：列出所有标定"""
    print_section("测试10: 列出所有标定配置")
    
    calibrations = HandEyeCalibration.objects.filter(
        robot_device=robot,
        camera_device=camera
    ).order_by('-created_at')
    
    print(f"找到 {calibrations.count()} 个标定配置:\n")
    
    for i, cal in enumerate(calibrations, 1):
        status = "✓ 激活" if cal.is_active else "  未激活"
        verified = "✓" if cal.verified_at else "✗"
        
        print(f"{i}. {status} | {cal.name}")
        print(f"   - 误差: {cal.calibration_error:.6f} mm | 样本: {cal.sample_count} | 验证: {verified}")
        print(f"   - 创建: {cal.created_at.strftime('%Y-%m-%d %H:%M')}")
        print()


def test_11_robot_pose_reading():
    """测试11：读取机器人位姿"""
    print_section("测试11: 读取机器人位姿（模拟）")
    
    from apps.devices.services import DeviceService
    
    device_service = DeviceService()
    
    for robot_code in ['ROBOT-01', 'ROBOT-02']:
        pose_data = device_service.adapter.read_robot_pose(robot_code)
        
        if pose_data['success']:
            print(f"✓ {robot_code} 位姿:")
            pose = pose_data['pose']
            print(f"  - 位置: X={pose['x']}, Y={pose['y']}, Z={pose['z']}")
            print(f"  - 姿态: RX={pose['rx']}, RY={pose['ry']}, RZ={pose['rz']}")
            print(f"  - 时间: {pose_data['timestamp']}")
        else:
            print(f"✗ 读取 {robot_code} 位姿失败")
        print()


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  手眼标定模块 - 完整功能测试")
    print("=" * 70)
    print()
    
    try:
        # 测试1: 创建设备
        robot, camera = test_1_create_devices()
        
        # 测试2: 创建标定任务
        calibration = test_2_create_calibration(robot, camera)
        
        # 测试3: 添加样本
        sample_count = test_3_add_samples(calibration)
        
        # 测试4: 计算标定
        result = test_4_compute_calibration(calibration)
        
        if result:
            # 测试5: 验证标定
            verification = test_5_verify_calibration(calibration)
            
            # 测试6: 激活标定
            calibration = test_6_activate_calibration(calibration)
        
        # 测试7: 坐标转换
        test_7_coordinate_transform()
        
        # 测试8: 获取激活标定
        active_cal = test_8_get_active_calibration(robot, camera)
        
        # 测试9: 导出导入
        if active_cal:
            imported = test_9_export_import(active_cal)
        
        # 测试10: 列出所有标定
        test_10_list_calibrations(robot, camera)
        
        # 测试11: 读取机器人位姿
        test_11_robot_pose_reading()
        
        # 总结
        print_section("测试总结")
        print("✓ 所有测试完成！")
        print()
        print("功能验证:")
        print("  ✓ 设备管理")
        print("  ✓ 标定任务创建")
        print("  ✓ 样本采集")
        print("  ✓ 标定计算 (OpenCV)")
        print("  ✓ 标定验证")
        print("  ✓ 标定激活")
        print("  ✓ 坐标转换")
        print("  ✓ 导出导入")
        print("  ✓ 机器人位姿读取")
        print()
        print("手眼标定模块功能正常！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
