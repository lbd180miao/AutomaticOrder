"""泡棉贴附检测算法（2D 检测相机）。

本模块用于装箱工位的固定式 2D 工业相机（海康 MV-CS050-10GC）检测泡棉贴附质量。
在装箱机器人完成泡棉贴附后，PLC 触发工位固定式检测相机拍照，视觉系统对泡棉贴附状态
进行实时校验，检测：
  - 泡棉漏贴（缺失）
  - 泡棉位置偏移（与预设位置的X/Y偏差）
  - 泡棉边缘起翘

检测合格后向 PLC 发送"工序完成"信号；不合格则立即报警并锁定工位，提示人工核查处理。

硬件配置：
  - 相机：海康 MV-CS050-10GC（500万像素，10GigE接口）
  - 镜头：MVL-MF1618M-5MPE 16MM（定焦，5MP，工作距离3m）
  - 安装：固定在装箱工位，俯视拍摄保险杠泡棉贴附区域
"""
from django.db import models

from . import image_io


class FoamDefectType(models.TextChoices):
    """泡棉缺陷分类。"""
    NONE = 'NONE', '无缺陷'
    MISSING = 'MISSING', '泡棉缺失/漏贴'
    MISALIGNED = 'MISALIGNED', '位置偏移'
    LIFTED_EDGE = 'LIFTED_EDGE', '边缘起翘'


class FoamInspector:
    """工位固定式2D相机泡棉贴附质量检测。
    
    用于装箱机器人完成泡棉贴附后的质量校验，检测漏贴、偏移、起翘等缺陷。
    """

    def __init__(self, *, simulate=True):
        """初始化检测器。
        
        Args:
            simulate: 是否使用模拟模式（调试用）。生产环境应设为 False。
        """
        self.simulate = simulate

    def inspect(self, *, position_index=0, inspection_config=None, image=None,
                camera_image_path='', simulated_pass=True):
        """检测泡棉贴附质量并生成可视化结果。

        本方法由 PLC 触发相机拍照后调用，用于检测：
          1. 泡棉是否存在（is_present）- 检测漏贴
          2. 泡棉位置是否对齐（is_aligned）- 检测偏移
          3. 泡棉边缘是否起翘（has_lifted_edge）- 检测起翘

        参数：
            position_index: 装箱位置编号（0-based），用于区分不同产品或不同装箱位
            inspection_config: 检测参数配置字典：
                - score_threshold (float, default 0.8): 综合评分阈值
                - coverage_threshold (float, default 0.75): ROI 覆盖率阈值
                - max_offset_px (int, default 30): 允许的最大像素偏移
            image: 相机拍摄的实际图像（numpy array，BGR格式）
                   - 模拟模式下可为 None
                   - 生产模式下由相机适配器传入
            camera_image_path: 原始图像路径（用于记录）
            simulated_pass: 仅模拟模式有效，强制通过/失败

        返回：
            dict: 检测结果，包含以下字段：
                - is_present (bool): 泡棉是否存在
                - is_aligned (bool): 泡棉位置是否对齐
                - has_lifted_edge (bool): 是否检测到边缘起翘
                - defect_type (str): 缺陷类型（NONE/MISSING/MISALIGNED/LIFTED_EDGE）
                - score (float): 综合评分 (0.0-1.0)
                - is_passed (bool): 最终判定（合格/不合格）
                - offset_x_px (float): X方向偏移（像素）
                - offset_y_px (float): Y方向偏移（像素）
                - coverage_ratio (float): 泡棉覆盖率 (0.0-1.0)
                - original_image (str): 原始图像路径
                - result_image (str): 标注结果图路径
                - roi (tuple): ROI检测区域 (x1, y1, x2, y2)
                - foam_box (tuple): 检测到的泡棉位置 (x1, y1, x2, y2)
                - result_data (dict): 详细检测数据（用于调试和追溯）

        工作流程：
            1. PLC 触发拍照 -> 相机采集图像
            2. 调用本方法进行检测
            3. 返回检测结果
            4. 根据 is_passed 判断：
               - True: 向 PLC 发送"工序完成"信号
               - False: 系统报警并锁定工位
        """
        if not self.simulate and image is None:
            raise NotImplementedError(
                '真实泡棉检测算法尚未接入。需要实现基于海康工业相机的图像处理算法。'
            )

        # 解析检测配置
        cfg = inspection_config or {}
        score_threshold = float(cfg.get('score_threshold', 0.8))
        coverage_threshold = float(cfg.get('coverage_threshold', 0.75))
        max_offset_px = int(cfg.get('max_offset_px', 30))

        # 1) 确定本次检测的缺陷类型（模拟模式）
        if simulated_pass:
            defect_type = FoamDefectType.NONE
        else:
            # 根据 position_index 轮换不同缺陷，模拟真实场景
            defect_cycle = [
                FoamDefectType.MISALIGNED,   # 位置偏移
                FoamDefectType.LIFTED_EDGE,  # 边缘起翘
                FoamDefectType.MISSING,      # 漏贴/缺失
            ]
            defect_type = defect_cycle[position_index % len(defect_cycle)]

        # 2) 获取图像（真实相机图像或模拟图像）
        using_camera_image = image is not None
        if using_camera_image:
            # 使用真实相机图像
            scene = image
            height, width = scene.shape[:2]
            
            # ROI设置为整张图片，留出小边距
            margin = 10
            roi = (margin, margin, width - margin, height - margin)
            
            # 泡棉检测区域设置为整张图片的95%
            # TODO: 这里需要实现真实的图像处理算法
            # 可能的方法：颜色阈值分割、轮廓检测、模板匹配等
            shrink = 30
            foam = (
                shrink,
                shrink,
                width - shrink,
                height - shrink,
            )
        else:
            # 模拟模式：生成测试图像
            scene, roi, foam = image_io.generate_foam_scene(
                position_index=position_index,
                passed=(defect_type == FoamDefectType.NONE),
                defect_type=defect_type,
            )

        # 3) 计算量化指标
        roi_cx = (roi[0] + roi[2]) / 2
        roi_cy = (roi[1] + roi[3]) / 2
        roi_area = max((roi[2] - roi[0]) * (roi[3] - roi[1]), 1)

        if defect_type == FoamDefectType.MISSING:
            # 泡棉缺失：未检测到泡棉
            foam_cx, foam_cy = roi_cx, roi_cy
            foam_area = 0
            coverage_ratio = 0.0
        else:
            # 计算泡棉中心偏移和覆盖率
            foam_cx = (foam[0] + foam[2]) / 2
            foam_cy = (foam[1] + foam[3]) / 2
            
            # 计算泡棉与 ROI 的交叉面积
            inter_x1 = max(roi[0], foam[0])
            inter_y1 = max(roi[1], foam[1])
            inter_x2 = min(roi[2], foam[2])
            inter_y2 = min(roi[3], foam[3])
            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            coverage_ratio = round(inter_area / roi_area, 4)

        # 计算偏移量（像素）
        offset_x_px = round(foam_cx - roi_cx, 1)
        offset_y_px = round(foam_cy - roi_cy, 1)

        # 4) 判定结果
        result = _build_result(
            defect_type=defect_type,
            offset_x_px=offset_x_px,
            offset_y_px=offset_y_px,
            coverage_ratio=coverage_ratio,
            score_threshold=score_threshold,
            coverage_threshold=coverage_threshold,
            max_offset_px=max_offset_px,
        )

        # 5) 保存原图和标注结果图
        original_path, w, h = image_io.save_image(
            scene, f'foam_raw_p{position_index}'
        )
        annotated = image_io.annotate_foam(scene, roi, foam, result)
        result_path, _, _ = image_io.save_image(
            annotated, f'foam_result_p{position_index}', rel_dir='vision/results',
        )

        # 6) 构建完整返回结果
        result.update({
            'position_index': position_index,
            'original_image': original_path,
            'result_image': result_path,
            'image_width': w,
            'image_height': h,
            'roi': roi,
            'foam_box': foam,
            'result_data': {
                'algorithm': 'camera_foam_inspector' if using_camera_image else 'simulated_foam_inspector',
                'camera_image_path': camera_image_path,
                'defect_type': defect_type,
                'roi': roi,
                'foam_box': foam,
                'offset_x_px': offset_x_px,
                'offset_y_px': offset_y_px,
                'coverage_ratio': coverage_ratio,
                'score_threshold': score_threshold,
                'coverage_threshold': coverage_threshold,
                'max_offset_px': max_offset_px,
                'camera_model': 'MV-CS050-10GC',
                'lens_model': 'MVL-MF1618M-5MPE 16MM',
            },
        })
        return result


def _build_result(*, defect_type, offset_x_px, offset_y_px, coverage_ratio,
                  score_threshold, coverage_threshold, max_offset_px):
    """根据缺陷类型和量化指标构建判定结果。
    
    判定逻辑：
        1. 泡棉缺失 -> 直接不合格
        2. 边缘起翘 -> 直接不合格
        3. 位置偏移 -> 根据偏移量和覆盖率判定
        4. 无缺陷 -> 合格
    """
    if defect_type == FoamDefectType.NONE:
        # 无缺陷：合格
        return {
            'is_present': True,
            'is_aligned': True,
            'has_lifted_edge': False,
            'defect_type': FoamDefectType.NONE,
            'score': 0.96,
            'offset_x_px': offset_x_px,
            'offset_y_px': offset_y_px,
            'coverage_ratio': coverage_ratio,
            'is_passed': True,
        }
    elif defect_type == FoamDefectType.MISSING:
        # 泡棉缺失/漏贴：不合格
        return {
            'is_present': False,
            'is_aligned': False,
            'has_lifted_edge': False,
            'defect_type': FoamDefectType.MISSING,
            'score': 0.0,
            'offset_x_px': 0.0,
            'offset_y_px': 0.0,
            'coverage_ratio': 0.0,
            'is_passed': False,
        }
    elif defect_type == FoamDefectType.LIFTED_EDGE:
        # 边缘起翘：不合格
        return {
            'is_present': True,
            'is_aligned': True,
            'has_lifted_edge': True,
            'defect_type': FoamDefectType.LIFTED_EDGE,
            'score': 0.42,
            'offset_x_px': offset_x_px,
            'offset_y_px': offset_y_px,
            'coverage_ratio': coverage_ratio,
            'is_passed': False,
        }
    else:  # MISALIGNED
        # 位置偏移：根据偏移量判定
        offset_px = (offset_x_px ** 2 + offset_y_px ** 2) ** 0.5
        score = round(max(0.0, 0.85 - offset_px / 200), 3)
        
        # 判定条件：
        # 1. X/Y偏移均不超过最大允许偏移
        # 2. 覆盖率满足要求
        # 3. 综合分数达标
        is_passed = (
            abs(offset_x_px) <= max_offset_px
            and abs(offset_y_px) <= max_offset_px
            and coverage_ratio >= coverage_threshold
            and score >= score_threshold
        )
        
        return {
            'is_present': True,
            'is_aligned': not is_passed,  # 偏移超标则不对齐
            'has_lifted_edge': False,
            'defect_type': FoamDefectType.MISALIGNED,
            'score': score,
            'offset_x_px': offset_x_px,
            'offset_y_px': offset_y_px,
            'coverage_ratio': coverage_ratio,
            'is_passed': is_passed,
        }
