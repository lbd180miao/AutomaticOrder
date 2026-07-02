"""
3D坐标转换服务
处理相机坐标系 → 机器人法兰坐标系 → 机器人基坐标系的转换
"""
import numpy as np
from typing import Tuple, Dict, Optional, Union
import logging
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)


class CoordinateTransformService:
    """
    坐标转换服务
    
    核心功能：
    1. 解析各种格式的变换矩阵
    2. 相机坐标系到机器人基坐标系的转换
    3. 六自由度位姿与齐次变换矩阵的转换
    """
    
    @staticmethod
    def parse_matrix_from_json(matrix_data: Union[Dict, list]) -> np.ndarray:
        """
        从JSON格式解析4×4齐次变换矩阵
        
        支持的格式：
        1. {"matrix": [[r11, r12, r13, tx], [r21, r22, r23, ty], [r31, r32, r33, tz], [0, 0, 0, 1]]}
        2. {"matrix": [r11, r12, r13, tx, r21, r22, r23, ty, ...]}  # 16元素扁平列表
        3. {"x": 30, "y": 0, "z": 100, "rx": 0, "ry": 0, "rz": 0}  # 六自由度（角度单位：度）
        4. [[...], [...], [...], [...]]  # 直接传入4×4列表
        
        Args:
            matrix_data: 矩阵数据（字典或列表）
            
        Returns:
            4×4 numpy数组
            
        Raises:
            ValueError: 格式不支持或数据无效
        """
        if isinstance(matrix_data, np.ndarray):
            if matrix_data.shape == (4, 4):
                return matrix_data
            raise ValueError(f"矩阵形状必须是(4, 4)，当前是{matrix_data.shape}")
        
        if isinstance(matrix_data, list):
            # 直接是4×4嵌套列表
            if len(matrix_data) == 4 and all(isinstance(row, list) and len(row) == 4 for row in matrix_data):
                return np.array(matrix_data, dtype=np.float64)
            # 或者是16元素扁平列表
            elif len(matrix_data) == 16:
                return np.array(matrix_data, dtype=np.float64).reshape(4, 4)
            else:
                raise ValueError(f"列表格式不正确，应为4×4嵌套列表或16元素列表，当前长度{len(matrix_data)}")
        
        if isinstance(matrix_data, dict):
            # 格式1: {"matrix": [[...], ...]}
            if 'matrix' in matrix_data:
                return CoordinateTransformService.parse_matrix_from_json(matrix_data['matrix'])
            
            # 格式3: {"x": ..., "y": ..., "z": ..., "rx": ..., "ry": ..., "rz": ...}
            if all(k in matrix_data for k in ['x', 'y', 'z']):
                x = float(matrix_data['x'])
                y = float(matrix_data['y'])
                z = float(matrix_data['z'])
                rx = float(matrix_data.get('rx', 0))
                ry = float(matrix_data.get('ry', 0))
                rz = float(matrix_data.get('rz', 0))
                return CoordinateTransformService.pose_to_matrix(x, y, z, rx, ry, rz)
            
            # 格式: {"rvec": [...], "tvec": [...]} (OpenCV格式)
            if 'rvec' in matrix_data and 'tvec' in matrix_data:
                return CoordinateTransformService.rvec_tvec_to_matrix(
                    matrix_data['rvec'],
                    matrix_data['tvec']
                )
            
            raise ValueError(f"字典格式不支持，必须包含'matrix'或'x,y,z'或'rvec,tvec'字段")
        
        raise ValueError(f"不支持的数据类型: {type(matrix_data)}")
    
    @staticmethod
    def pose_to_matrix(x: float, y: float, z: float, 
                      rx: float, ry: float, rz: float,
                      angle_unit: str = 'deg') -> np.ndarray:
        """
        将六自由度位姿（X, Y, Z, RX, RY, RZ）转换为4×4齐次变换矩阵
        
        Args:
            x, y, z: 平移分量（单位：mm）
            rx, ry, rz: 旋转分量（欧拉角）
            angle_unit: 角度单位，'deg'（度）或'rad'（弧度）
            
        Returns:
            4×4齐次变换矩阵
        """
        # 构造旋转矩阵（使用ZYX欧拉角顺序，机器人常用）
        if angle_unit == 'deg':
            rotation = Rotation.from_euler('ZYX', [rz, ry, rx], degrees=True)
        else:
            rotation = Rotation.from_euler('ZYX', [rz, ry, rx], degrees=False)
        
        R = rotation.as_matrix()
        
        # 构造4×4齐次变换矩阵
        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        T[:3, 3] = [x, y, z]
        
        return T
    
    @staticmethod
    def matrix_to_pose(T: np.ndarray, angle_unit: str = 'deg') -> Dict[str, float]:
        """
        将4×4齐次变换矩阵转换为六自由度位姿
        
        Args:
            T: 4×4齐次变换矩阵
            angle_unit: 角度单位，'deg'（度）或'rad'（弧度）
            
        Returns:
            {"x": ..., "y": ..., "z": ..., "rx": ..., "ry": ..., "rz": ...}
        """
        if T.shape != (4, 4):
            raise ValueError(f"矩阵形状必须是(4, 4)，当前是{T.shape}")
        
        # 提取平移
        x, y, z = T[:3, 3]
        
        # 提取旋转（ZYX欧拉角）
        R = T[:3, :3]
        rotation = Rotation.from_matrix(R)
        rz, ry, rx = rotation.as_euler('ZYX', degrees=(angle_unit == 'deg'))
        
        return {
            'x': float(x),
            'y': float(y),
            'z': float(z),
            'rx': float(rx),
            'ry': float(ry),
            'rz': float(rz),
        }
    
    @staticmethod
    def rvec_tvec_to_matrix(rvec: Union[list, np.ndarray], 
                           tvec: Union[list, np.ndarray]) -> np.ndarray:
        """
        将OpenCV的旋转向量+平移向量转换为4×4齐次变换矩阵
        
        Args:
            rvec: 旋转向量 (3,) 或 (3, 1)
            tvec: 平移向量 (3,) 或 (3, 1)
            
        Returns:
            4×4齐次变换矩阵
        """
        import cv2
        
        rvec = np.array(rvec, dtype=np.float64).flatten()
        tvec = np.array(tvec, dtype=np.float64).flatten()
        
        R, _ = cv2.Rodrigues(rvec)
        
        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        T[:3, 3] = tvec
        
        return T
    
    @staticmethod
    def matrix_to_rvec_tvec(T: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        将4×4齐次变换矩阵转换为OpenCV的旋转向量+平移向量
        
        Args:
            T: 4×4齐次变换矩阵
            
        Returns:
            (rvec, tvec) 元组
        """
        import cv2
        
        R = T[:3, :3]
        tvec = T[:3, 3]
        
        rvec, _ = cv2.Rodrigues(R)
        
        return rvec.flatten(), tvec.flatten()
    
    @staticmethod
    def camera_to_robot_base(
        P_camera: np.ndarray,
        T_flange_camera: np.ndarray,
        T_base_flange: np.ndarray,
    ) -> np.ndarray:
        """
        将相机坐标系点云转换到机器人基坐标系
        
        核心公式：P_base = T_base_flange × T_flange_camera × P_camera
        
        转换流程：
        1. 相机坐标点 P_camera
        2. 通过 T_flange_camera（手眼标定矩阵）转到机器人法兰坐标
        3. 通过 T_base_flange（机器人当前位姿）转到机器人基坐标
        4. 得到机器人基坐标点 P_base
        
        Args:
            P_camera: 相机坐标系下的点云，shape (N, 3) 或 (3,)
            T_flange_camera: 手眼标定矩阵，shape (4, 4)
            T_base_flange: 机器人当前拍照位姿，shape (4, 4)
            
        Returns:
            P_base: 机器人基坐标系下的点云，shape (N, 3) 或 (3,)
            
        Raises:
            ValueError: 输入形状不正确
        """
        # 输入验证
        if T_flange_camera.shape != (4, 4):
            raise ValueError(f"T_flange_camera形状必须是(4, 4)，当前是{T_flange_camera.shape}")
        if T_base_flange.shape != (4, 4):
            raise ValueError(f"T_base_flange形状必须是(4, 4)，当前是{T_base_flange.shape}")
        
        # 处理点云格式
        P_camera = np.array(P_camera, dtype=np.float64)
        original_shape = P_camera.shape
        
        if P_camera.ndim == 1:
            if len(P_camera) != 3:
                raise ValueError(f"单点坐标必须是3维，当前是{len(P_camera)}维")
            P_camera = P_camera.reshape(1, 3)
        elif P_camera.ndim == 2:
            if P_camera.shape[1] != 3:
                raise ValueError(f"点云坐标必须是(N, 3)格式，当前是{P_camera.shape}")
        else:
            raise ValueError(f"点云维度必须是1或2，当前是{P_camera.ndim}")
        
        # 转换为齐次坐标 (N, 4)
        N = P_camera.shape[0]
        P_camera_homogeneous = np.hstack([P_camera, np.ones((N, 1))])
        
        # 连续变换：T_base_flange × T_flange_camera × P_camera
        T_combined = T_base_flange @ T_flange_camera
        P_base_homogeneous = (T_combined @ P_camera_homogeneous.T).T
        
        # 转回笛卡尔坐标
        P_base = P_base_homogeneous[:, :3]
        
        # 恢复原始形状
        if original_shape == (3,):
            return P_base.flatten()
        
        return P_base
    
    @staticmethod
    def verify_transform_chain(
        P_camera: np.ndarray,
        T_flange_camera: np.ndarray,
        T_base_flange: np.ndarray,
        P_expected_base: Optional[np.ndarray] = None,
        tolerance: float = 5.0
    ) -> Dict:
        """
        验证坐标转换链的正确性
        
        Args:
            P_camera: 相机坐标系测试点
            T_flange_camera: 手眼标定矩阵
            T_base_flange: 机器人位姿
            P_expected_base: 期望的机器人基坐标系坐标（可选）
            tolerance: 误差容忍度（mm）
            
        Returns:
            验证结果字典
        """
        # 执行转换
        P_base = CoordinateTransformService.camera_to_robot_base(
            P_camera, T_flange_camera, T_base_flange
        )
        
        result = {
            'P_camera': P_camera.tolist() if isinstance(P_camera, np.ndarray) else P_camera,
            'P_base': P_base.tolist() if isinstance(P_base, np.ndarray) else P_base,
            'T_combined': (T_base_flange @ T_flange_camera).tolist(),
        }
        
        # 如果提供了期望值，计算误差
        if P_expected_base is not None:
            P_expected_base = np.array(P_expected_base, dtype=np.float64)
            
            # 计算欧氏距离误差
            if P_base.ndim == 1:
                error = np.linalg.norm(P_base - P_expected_base)
                result['error'] = float(error)
                result['is_valid'] = error <= tolerance
            else:
                errors = np.linalg.norm(P_base - P_expected_base, axis=1)
                result['errors'] = errors.tolist()
                result['mean_error'] = float(np.mean(errors))
                result['max_error'] = float(np.max(errors))
                result['std_error'] = float(np.std(errors))
                result['is_valid'] = result['mean_error'] <= tolerance
            
            result['tolerance'] = tolerance
            result['P_expected_base'] = P_expected_base.tolist()
        else:
            result['is_valid'] = True
            result['message'] = '无期望值，跳过误差验证'
        
        return result
    
    @staticmethod
    def create_identity_matrix() -> np.ndarray:
        """创建4×4单位矩阵"""
        return np.eye(4, dtype=np.float64)
    
    @staticmethod
    def invert_transform(T: np.ndarray) -> np.ndarray:
        """
        计算变换矩阵的逆
        
        对于齐次变换矩阵 T = [R t; 0 1]
        其逆为 T^-1 = [R^T -R^T*t; 0 1]
        
        Args:
            T: 4×4齐次变换矩阵
            
        Returns:
            T的逆矩阵
        """
        if T.shape != (4, 4):
            raise ValueError(f"矩阵形状必须是(4, 4)，当前是{T.shape}")
        
        R = T[:3, :3]
        t = T[:3, 3]
        
        T_inv = np.eye(4, dtype=np.float64)
        T_inv[:3, :3] = R.T
        T_inv[:3, 3] = -R.T @ t
        
        return T_inv
    
    @staticmethod
    def matrix_to_json(T: np.ndarray) -> Dict:
        """
        将numpy矩阵转换为JSON友好格式
        
        Args:
            T: 4×4 numpy矩阵
            
        Returns:
            {"matrix": [[...], [...], [...], [...]]}
        """
        if not isinstance(T, np.ndarray):
            T = np.array(T)
        
        if T.shape != (4, 4):
            raise ValueError(f"矩阵形状必须是(4, 4)，当前是{T.shape}")
        
        return {
            "matrix": T.tolist()
        }
    
    @staticmethod
    def validate_rotation_matrix(R: np.ndarray, tolerance: float = 1e-6) -> Tuple[bool, str]:
        """
        验证旋转矩阵的有效性
        
        旋转矩阵必须满足：
        1. R * R^T = I (正交性)
        2. det(R) = 1 (右手系)
        
        Args:
            R: 3×3旋转矩阵
            tolerance: 误差容忍度
            
        Returns:
            (是否有效, 错误信息)
        """
        if R.shape != (3, 3):
            return False, f"旋转矩阵形状必须是(3, 3)，当前是{R.shape}"
        
        # 检查正交性
        should_be_eye = R @ R.T
        if not np.allclose(should_be_eye, np.eye(3), atol=tolerance):
            return False, "旋转矩阵不满足正交性 (R * R^T != I)"
        
        # 检查行列式
        det = np.linalg.det(R)
        if not np.isclose(det, 1.0, atol=tolerance):
            return False, f"旋转矩阵行列式不为1 (det={det:.6f})"
        
        return True, "旋转矩阵有效"
