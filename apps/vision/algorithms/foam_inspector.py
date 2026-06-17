"""泡棉贴附检测算法（2D 检测相机）。

用 OpenCV 生成模拟的 2D 相机画面，在 ROI 检测区内识别泡棉是否存在、是否
对齐、是否起翘，输出结构化结果，并归档原图与带 ROI 标注的结果图。
后期可用阈值、轮廓、模板匹配等真实方法替换 generate/inspect 内部实现。
"""
from django.db import models

from . import image_io


class FoamDefectType(models.TextChoices):
    """泡棉缺陷分类。"""
    NONE = 'NONE', '无缺陷'
    MISALIGNED = 'MISALIGNED', '位置偏移'
    LIFTED_EDGE = 'LIFTED_EDGE', '边缘起翘'
    MISSING = 'MISSING', '泡棉缺失'


# 每个 position_index 对应的模拟缺陷场景参数
# 合格位置用 None；不合格位置指定对应的 FoamDefectType
_POSITION_DEFECT_MAP = {
    0: None,                      # 位置 0：无缺陷
    1: FoamDefectType.MISALIGNED, # 位置 1：偏移
    2: FoamDefectType.LIFTED_EDGE,# 位置 2：起翘
    3: FoamDefectType.MISSING,    # 位置 3：缺失
}


class FoamInspector:
    """2D camera foam inspection with simulated scene and ROI annotation."""

    def __init__(self, *, simulate=True):
        self.simulate = simulate

    def inspect(self, *, position_index=0, inspection_config=None, image=None,
                camera_image_path='', simulated_pass=True):
        """检测泡棉并生成可视化图片。

        参数：
            position_index: 泡棉贴附位置编号（0-based），影响模拟场景差异。
            inspection_config: 可选配置字典，支持以下键：
                - score_threshold (float, default 0.8): 合格分数阈值
                - coverage_threshold (float, default 0.75): ROI 覆盖率阈值
                - max_offset_px (int, default 30): 允许的最大像素偏移
            image: 真实相机接入后传入的图像数组（模拟模式忽略）。
            simulated_pass: 模拟模式下强制通过/失败。

        返回结构化字典，包含：
            - is_present / is_aligned / has_lifted_edge / score / is_passed
            - defect_type: FoamDefectType 枚举值
            - offset_x_px / offset_y_px: 泡棉中心与 ROI 中心的像素偏差
            - coverage_ratio: 泡棉面积与 ROI 面积的覆盖比
            - original_image / result_image（media 相对路径）
            - roi / foam_box（检测框坐标）
        """
        if not self.simulate and image is None:
            raise NotImplementedError('真实泡棉检测算法尚未接入')

        # 解析 inspection_config
        cfg = inspection_config or {}
        score_threshold = float(cfg.get('score_threshold', 0.8))
        coverage_threshold = float(cfg.get('coverage_threshold', 0.75))
        max_offset_px = int(cfg.get('max_offset_px', 30))

        # 1) 确定本次模拟的缺陷类型
        if simulated_pass:
            defect_type = FoamDefectType.NONE
        else:
            # 根据 position_index 轮换不同缺陷，增加模拟真实感
            defect_cycle = [
                FoamDefectType.MISALIGNED,
                FoamDefectType.LIFTED_EDGE,
                FoamDefectType.MISSING,
            ]
            defect_type = defect_cycle[position_index % len(defect_cycle)]

        # 2) 取得 2D 相机画面。有真实图时直接在真实图上画 ROI，否则生成模拟图。
        using_camera_image = image is not None
        if using_camera_image:
            scene = image
            height, width = scene.shape[:2]
            roi_w = min(220, max(width - 40, 40))
            roi_h = min(160, max(height - 40, 40))
            roi = (
                width // 2 - roi_w // 2,
                height // 2 - roi_h // 2,
                width // 2 + roi_w // 2,
                height // 2 + roi_h // 2,
            )
            shrink_x = max((roi[2] - roi[0]) // 6, 1)
            shrink_y = max((roi[3] - roi[1]) // 6, 1)
            foam = (
                roi[0] + shrink_x,
                roi[1] + shrink_y,
                roi[2] - shrink_x,
                roi[3] - shrink_y,
            )
        else:
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
            # 泡棉缺失：无泡棉框
            foam_cx, foam_cy = roi_cx, roi_cy
            foam_area = 0
            coverage_ratio = 0.0
        else:
            foam_cx = (foam[0] + foam[2]) / 2
            foam_cy = (foam[1] + foam[3]) / 2
            # 计算泡棉与 ROI 的实际交叉面积
            inter_x1 = max(roi[0], foam[0])
            inter_y1 = max(roi[1], foam[1])
            inter_x2 = min(roi[2], foam[2])
            inter_y2 = min(roi[3], foam[3])
            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            coverage_ratio = round(inter_area / roi_area, 4)

        offset_x_px = round(foam_cx - roi_cx, 1)
        offset_y_px = round(foam_cy - roi_cy, 1)

        # 4) 判定结果（模拟识别逻辑）
        result = _build_result(
            defect_type=defect_type,
            offset_x_px=offset_x_px,
            offset_y_px=offset_y_px,
            coverage_ratio=coverage_ratio,
            score_threshold=score_threshold,
            coverage_threshold=coverage_threshold,
            max_offset_px=max_offset_px,
        )

        # 5) 归档原图 + 带 ROI 标注的结果图。
        original_path, w, h = image_io.save_image(scene, f'foam_raw_p{position_index}')
        annotated = image_io.annotate_foam(scene, roi, foam, result)
        result_path, _, _ = image_io.save_image(
            annotated, f'foam_result_p{position_index}', rel_dir='vision/results',
        )

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
            },
        })
        return result


def _build_result(*, defect_type, offset_x_px, offset_y_px, coverage_ratio,
                  score_threshold, coverage_threshold, max_offset_px):
    """根据缺陷类型和量化指标构建判定结果字典。"""
    if defect_type == FoamDefectType.NONE:
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
    elif defect_type == FoamDefectType.MISALIGNED:
        offset_px = (offset_x_px ** 2 + offset_y_px ** 2) ** 0.5
        score = round(max(0.0, 0.85 - offset_px / 200), 3)
        return {
            'is_present': True,
            'is_aligned': False,
            'has_lifted_edge': False,
            'defect_type': FoamDefectType.MISALIGNED,
            'score': score,
            'offset_x_px': offset_x_px,
            'offset_y_px': offset_y_px,
            'coverage_ratio': coverage_ratio,
            'is_passed': (
                abs(offset_x_px) <= max_offset_px
                and abs(offset_y_px) <= max_offset_px
                and coverage_ratio >= coverage_threshold
                and score >= score_threshold
            ),
        }
    elif defect_type == FoamDefectType.LIFTED_EDGE:
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
    else:  # MISSING
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
