"""
手眼标定坐标转换测试脚本

测试核心公式：P_base = T_base_flange × T_flange_camera × P_camera
"""
import numpy as np
from apps.vision.coordinate_transform import CoordinateTransformService

def test_identity_transform():
    """测试单位矩阵转换（无变换）"""
    print("=" * 60)
    print("测试1: 单位矩阵转换")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 相机坐标系测试点
    P_camera = np.array([100.0, 50.0, 500.0])
    print(f"相机坐标系测试点: {P_camera}")
    
    # 单位矩阵（无变换）
    T_flange_camera = np.eye(4)
    T_base_flange = np.eye(4)
    
    # 执行转换
    P_base = service.camera_to_robot_base(P_camera, T_flange_camera, T_base_flange)
    print(f"机器人基坐标系结果: {P_base}")
    print(f"预期结果: {P_camera}")
    print(f"误差: {np.linalg.norm(P_base - P_camera):.6f} mm")
    print()


def test_translation_only():
    """测试纯平移变换"""
    print("=" * 60)
    print("测试2: 纯平移变换")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 相机坐标系测试点
    P_camera = np.array([0.0, 0.0, 0.0])
    print(f"相机坐标系测试点: {P_camera}")
    
    # 手眼标定：相机在法兰坐标系向X偏移30mm, Z偏移100mm
    T_flange_camera = service.pose_to_matrix(30, 0, 100, 0, 0, 0)
    print(f"T_flange_camera (相机偏移): X=30mm, Z=100mm")
    
    # 机器人位姿：法兰在基坐标系位置 (500, 200, 850)
    T_base_flange = service.pose_to_matrix(500, 200, 850, 0, 0, 0)
    print(f"T_base_flange (机器人位姿): X=500mm, Y=200mm, Z=850mm")
    
    # 执行转换
    P_base = service.camera_to_robot_base(P_camera, T_flange_camera, T_base_flange)
    print(f"机器人基坐标系结果: {P_base}")
    
    # 预期结果：500+30=530, 200+0=200, 850+100=950
    P_expected = np.array([530.0, 200.0, 950.0])
    print(f"预期结果: {P_expected}")
    print(f"误差: {np.linalg.norm(P_base - P_expected):.6f} mm")
    print()


def test_rotation_and_translation():
    """测试旋转+平移变换"""
    print("=" * 60)
    print("测试3: 旋转+平移变换")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 相机坐标系测试点
    P_camera = np.array([50.0, 0.0, 100.0])
    print(f"相机坐标系测试点: {P_camera}")
    
    # 手眼标定：相机绕Z轴旋转90度，并偏移
    T_flange_camera = service.pose_to_matrix(0, 0, 100, 0, 0, 90)
    print(f"T_flange_camera: RZ=90度, Z=100mm")
    
    # 机器人位姿
    T_base_flange = service.pose_to_matrix(500, 200, 850, 0, 0, 0)
    print(f"T_base_flange: X=500mm, Y=200mm, Z=850mm")
    
    # 执行转换
    P_base = service.camera_to_robot_base(P_camera, T_flange_camera, T_base_flange)
    print(f"机器人基坐标系结果: {P_base}")
    
    # 分析：相机点(50,0,100)经过90度旋转变成(0,50,100)，再加上基坐标系偏移
    print(f"分析：旋转90度后 (50,0) -> (0,50)，最终基坐标系应约为 (500, 250, 950)")
    print()


def test_pointcloud_batch():
    """测试点云批量转换"""
    print("=" * 60)
    print("测试4: 点云批量转换")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 相机坐标系点云（5个点）
    P_camera = np.array([
        [0, 0, 500],
        [100, 0, 500],
        [0, 100, 500],
        [-100, 0, 500],
        [0, -100, 500]
    ], dtype=np.float64)
    print(f"相机坐标系点云形状: {P_camera.shape}")
    print(f"前3个点:\n{P_camera[:3]}")
    
    # 手眼标定和机器人位姿
    T_flange_camera = service.pose_to_matrix(30, 0, 100, 0, 0, 0)
    T_base_flange = service.pose_to_matrix(500, 200, 850, 0, 0, 0)
    
    # 批量转换
    P_base = service.camera_to_robot_base(P_camera, T_flange_camera, T_base_flange)
    print(f"机器人基坐标系点云形状: {P_base.shape}")
    print(f"前3个点:\n{P_base[:3]}")
    
    # 验证所有点都正确偏移
    expected_offset = np.array([530, 200, 1450])  # 500+30, 200+0, 850+100+500
    print(f"\n第一个点预期值: {expected_offset}")
    print(f"第一个点实际值: {P_base[0]}")
    print(f"误差: {np.linalg.norm(P_base[0] - expected_offset):.6f} mm")
    print()


def test_matrix_formats():
    """测试不同的矩阵格式解析"""
    print("=" * 60)
    print("测试5: 矩阵格式解析")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 格式1: 六自由度字典
    pose_dict = {'x': 100, 'y': 200, 'z': 300, 'rx': 0, 'ry': 0, 'rz': 90}
    T1 = service.parse_matrix_from_json(pose_dict)
    print(f"六自由度字典格式解析成功: {T1.shape}")
    
    # 格式2: 嵌套矩阵
    matrix_nested = {
        'matrix': [
            [1, 0, 0, 100],
            [0, 1, 0, 200],
            [0, 0, 1, 300],
            [0, 0, 0, 1]
        ]
    }
    T2 = service.parse_matrix_from_json(matrix_nested)
    print(f"嵌套矩阵格式解析成功: {T2.shape}")
    
    # 格式3: OpenCV格式
    opencv_format = {
        'rvec': [0, 0, 1.5708],  # 90度 ≈ 1.5708弧度
        'tvec': [100, 200, 300]
    }
    T3 = service.parse_matrix_from_json(opencv_format)
    print(f"OpenCV格式解析成功: {T3.shape}")
    
    print("所有格式解析测试通过！")
    print()


def test_transform_verification():
    """测试坐标转换验证功能"""
    print("=" * 60)
    print("测试6: 坐标转换验证")
    print("=" * 60)
    
    service = CoordinateTransformService()
    
    # 测试点和期望结果
    P_camera = np.array([0.0, 0.0, 0.0])
    P_expected_base = np.array([530.0, 200.0, 950.0])
    
    T_flange_camera = service.pose_to_matrix(30, 0, 100, 0, 0, 0)
    T_base_flange = service.pose_to_matrix(500, 200, 850, 0, 0, 0)
    
    # 验证转换
    result = service.verify_transform_chain(
        P_camera, T_flange_camera, T_base_flange, 
        P_expected_base, tolerance=0.01
    )
    
    print(f"转换结果: {result['P_base']}")
    print(f"期望结果: {result['P_expected_base']}")
    print(f"误差: {result['error']:.6f} mm")
    print(f"验证通过: {result['is_valid']}")
    print()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("手眼标定坐标转换测试")
    print("=" * 60)
    print()
    
    try:
        test_identity_transform()
        test_translation_only()
        test_rotation_and_translation()
        test_pointcloud_batch()
        test_matrix_formats()
        test_transform_verification()
        
        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
