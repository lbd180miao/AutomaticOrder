"""料架定位算法（3D 深度相机，方案A：单次拍摄覆盖全部料架）。

硬件已确认：
  - 3D 相机（杭州洛微 LWP-D322W-I）安装于机器人手臂末端（手眼）
  - 机器人移动至固定预设拍照位停下后，**一次拍摄同时覆盖左右两个料架**
  - 每个料架 3 层，两架并列摆放
  - 算法从同一张深度图中分别解析左侧区域和右侧区域，输出各自的
    X/Y/Z 偏差、各层高度、置信度和 plc_payload

主入口：
  locate_all()  — 单次拍摄，同时返回 {LEFT: ..., RIGHT: ...}（推荐）
  locate()      — 单侧定位（供测试/单独调用使用）

算法只输出结构化结果，不决定产线流程是否继续。
后期可在 _analyse_side() 内接入真实深度图/点云处理替换模拟部分。
"""
import random
from dataclasses import dataclass, field
from typing import Optional

from . import image_io


@dataclass
class LocatorConfig:
    """料架定位算法配置，可在构造 RackLocator 时传入覆盖默认值。"""
    min_confidence: float = 0.70      # 低于此置信度视为定位失败
    layer_count_expected: int = 3     # 料架预期层数（与实际设备 3 层一致）
    noise_std_mm: float = 0.8         # 模拟深度测量噪声标准差（mm）


class RackLocator:
    """Depth-camera rack location with simulated depth scene and ROI annotation.

    方案A：机器人停在固定拍照位，单次采集整个料架深度图，
    算法内部按 layer_count 推导各层高度与层距。
    """

    def __init__(self, *, simulate: bool = True,
                 config: Optional[LocatorConfig] = None):
        self.simulate = simulate
        self.config = config or LocatorConfig()

    def locate(self, *, side: str, recipe=None, calibration_profile=None,
               image=None, simulated_offsets=None, product_code: str = ''):
        """计算指定侧料架的 X/Y/Z 偏差、各层实测高度与置信度，生成可视化图。

        参数：
            side: 'LEFT' 或 'RIGHT'
            recipe: RackRecipe 实例，用于读取 layer_count / layer_height / layer_spacing
            calibration_profile: 手眼标定配置（真实接入后使用）
            image: 真实深度图数组（模拟模式忽略）
            simulated_offsets: 可注入的模拟偏移量字典，方便测试
            product_code: 产品编号，写入 plc_payload 供 PLC 追溯

        返回结构化字典：
            side / offset_x / offset_y / offset_z
            layer_count / layer_heights / layer_spacings
            measured_layer_height / measured_layer_spacing（均值，兼容旧字段）
            confidence / is_success
            plc_payload（可直接下发 PLC 的完整数据包）
            original_image / result_image / image_width / image_height
            pillar_roi / region_roi / result_data
        """
        if not self.simulate:
            raise NotImplementedError('真实深度相机定位算法尚未接入')

        cfg = self.config

        # ---- 1. 确定三轴偏移量 ----------------------------------------
        defaults = {
            'LEFT':  {'offset_x': 1.2,  'offset_y': -0.8, 'offset_z': 0.5},
            'RIGHT': {'offset_x': -1.0, 'offset_y':  0.6, 'offset_z': -0.4},
        }
        raw = simulated_offsets or defaults.get(side, defaults['LEFT'])
        offsets = {k: round(float(v), 3) for k, v in raw.items()
                   if k in ('offset_x', 'offset_y', 'offset_z')}

        # ---- 2. 从配方获取层数与标称值 ------------------------------------
        if recipe is not None:
            layer_count = int(recipe.layer_count) if recipe.layer_count else cfg.layer_count_expected
            nominal_height = float(recipe.layer_height)
            nominal_spacing = float(recipe.layer_spacing)
        else:
            layer_count = cfg.layer_count_expected
            nominal_height = 120.0
            nominal_spacing = 150.0

        # ---- 3. 模拟各层实测高度（单次拍摄，算法内推导） -----------------
        # 真实实现：从深度点云按层分割，提取各层中心面Z坐标差值
        rng = random.Random(hash(side) % (2 ** 32))   # 确定性随机（同侧同值）

        def _noisy(base):
            return round(base + rng.gauss(0, cfg.noise_std_mm), 3)

        layer_heights = [_noisy(nominal_height) for _ in range(layer_count)]
        layer_spacings = [_noisy(nominal_spacing) for _ in range(layer_count - 1)]

        # 均值（兼容旧 measured_layer_height / measured_layer_spacing 字段）
        measured_height = round(sum(layer_heights) / len(layer_heights), 3)
        measured_spacing = round(
            sum(layer_spacings) / len(layer_spacings), 3
        ) if layer_spacings else nominal_spacing

        # ---- 4. 计算置信度（层高方差越大置信度越低） ----------------------
        if layer_count > 1:
            variance = sum((h - measured_height) ** 2 for h in layer_heights) / layer_count
            # 方差 0 → confidence 0.98；方差 ≥ 5 mm² → confidence 0.70
            confidence = round(max(0.70, 0.98 - variance / 25), 4)
        else:
            confidence = 0.95

        is_success = confidence >= cfg.min_confidence

        # ---- 5. 是否与配方匹配 -------------------------------------------
        recipe_matched = True
        if recipe is not None:
            from decimal import Decimal
            tol = max(float(getattr(recipe, 'tolerance_z', 1)), 1.0)
            recipe_matched = (
                abs(measured_height - nominal_height) <= tol
                and abs(measured_spacing - nominal_spacing) <= tol
            )

        # ---- 6. 组装 plc_payload（可直接序列化下发 PLC） ----------------
        plc_payload = {
            'side': side,
            'offset_x': offsets['offset_x'],
            'offset_y': offsets['offset_y'],
            'offset_z': offsets['offset_z'],
            'layer_count': layer_count,
            'layer_heights': layer_heights,
            'layer_spacings': layer_spacings,
            'confidence': confidence,
            'recipe_matched': recipe_matched,
            'product_code': product_code,
        }

        # ---- 7. 取得深度相机伪彩色画面并归档 ------------------------------
        depth_img, pillar, region = image_io.generate_depth_scene(
            side=side, layer_count=layer_count,
        )
        original_path, w, h = image_io.save_image(
            depth_img, f'depth_{side.lower()}_raw',
        )
        annotated = image_io.annotate_depth(
            depth_img, pillar, region, side, offsets,
            confidence=confidence,
            layer_heights=layer_heights,
            recipe_matched=recipe_matched,
        )
        result_path, _, _ = image_io.save_image(
            annotated, f'depth_{side.lower()}_result', rel_dir='vision/results',
        )

        return {
            # 定位核心数据
            'side': side,
            'offset_x': offsets['offset_x'],
            'offset_y': offsets['offset_y'],
            'offset_z': offsets['offset_z'],
            # 分层测量数据
            'layer_count': layer_count,
            'layer_heights': layer_heights,
            'layer_spacings': layer_spacings,
            # 均值（兼容 VisionService 旧字段）
            'measured_layer_height': measured_height,
            'measured_layer_spacing': measured_spacing,
            # 质量评估
            'confidence': confidence,
            'recipe_matched': recipe_matched,
            'is_success': is_success,
            # PLC 数据包
            'plc_payload': plc_payload,
            # 图像归档
            'original_image': original_path,
            'result_image': result_path,
            'image_width': w,
            'image_height': h,
            'pillar_roi': pillar,
            'region_roi': region,
            # 调试 / 追溯元数据
            'result_data': {
                'algorithm': 'simulated_rack_locator_v2',
                'scan_mode': 'single_shot',   # 方案A
                'calibration': getattr(calibration_profile, 'version', None),
                'pillar_roi': pillar,
                'region_roi': region,
                'layer_heights': layer_heights,
                'layer_spacings': layer_spacings,
                'confidence': confidence,
                'plc_payload': plc_payload,
            },
        }

    # ------------------------------------------------------------------
    # locate_all: 单次拍摄覆盖双料架（硬件确认）
    # ------------------------------------------------------------------

    def locate_all(self, *, recipe=None, calibration_profile=None,
                   simulated_offsets_map=None, product_code=''):
        """单次拍摄同时覆盖左右两个料架，返回双侧定位结果。

        硬件确认：3D 相机一次拍摄即可覆盖全部料架区域，算法从同一张深度图
        中分别解析左侧区域和右侧区域，输出各自 X/Y/Z 偏差与 plc_payload。
        """
        if not self.simulate:
            raise NotImplementedError('真实深度相机 locate_all 尚未接入')

        sides = ('LEFT', 'RIGHT')
        offsets_map = simulated_offsets_map or {}
        layer_count = (
            int(recipe.layer_count)
            if recipe and getattr(recipe, 'layer_count', None)
            else self.config.layer_count_expected
        )

        # 1. 单次生成覆盖双料架的宽幅深度图
        dual_img, rois = image_io.generate_depth_scene_both(layer_count=layer_count)
        original_path, w, h = image_io.save_image(dual_img, 'depth_both_raw')

        # 2. 从同一张图中分别解析各侧数据
        all_side_data = {}
        for side in sides:
            all_side_data[side] = self._analyse_side(
                side=side, recipe=recipe, calibration_profile=calibration_profile,
                product_code=product_code, simulated_offsets=offsets_map.get(side),
            )

        # 3. 在合并图上绘制双侧标注后归档
        annotated = image_io.annotate_depth_both(
            dual_img, rois, all_side_data, layer_count=layer_count,
        )
        result_path, _, _ = image_io.save_image(
            annotated, 'depth_both_result', rel_dir='vision/results',
        )

        results = {}
        for side in sides:
            results[side] = {
                **all_side_data[side],
                'original_image': original_path,
                'result_image': result_path,
                'image_width': w,
                'image_height': h,
            }

        return {
            'LEFT': results['LEFT'],
            'RIGHT': results['RIGHT'],
            'original_image': original_path,
            'result_image': result_path,
            'image_width': w,
            'image_height': h,
        }

    def _analyse_side(self, *, side, recipe=None, calibration_profile=None,
                      product_code='', simulated_offsets=None):
        """从已采集的深度图中解析单侧料架数据（纯数值计算，不生成图像）。"""
        cfg = self.config
        defaults = {
            'LEFT':  {'offset_x': 1.2,  'offset_y': -0.8, 'offset_z': 0.5},
            'RIGHT': {'offset_x': -1.0, 'offset_y':  0.6, 'offset_z': -0.4},
        }
        raw = simulated_offsets or defaults.get(side, defaults['LEFT'])
        offsets = {k: round(float(v), 3) for k, v in raw.items()
                   if k in ('offset_x', 'offset_y', 'offset_z')}

        if recipe is not None:
            layer_count = (int(recipe.layer_count)
                           if getattr(recipe, 'layer_count', None)
                           else cfg.layer_count_expected)
            nominal_height  = float(recipe.layer_height)
            nominal_spacing = float(recipe.layer_spacing)
        else:
            layer_count     = cfg.layer_count_expected
            nominal_height  = 120.0
            nominal_spacing = 150.0

        rng = random.Random(hash(side) % (2 ** 32))

        def noisy(base):
            return round(base + rng.gauss(0, cfg.noise_std_mm), 3)

        layer_heights  = [noisy(nominal_height)  for _ in range(layer_count)]
        layer_spacings = [noisy(nominal_spacing) for _ in range(layer_count - 1)]
        measured_height  = round(sum(layer_heights) / len(layer_heights), 3)
        measured_spacing = (
            round(sum(layer_spacings) / len(layer_spacings), 3)
            if layer_spacings else nominal_spacing
        )

        variance = (
            sum((h - measured_height) ** 2 for h in layer_heights) / layer_count
            if layer_count > 1 else 0
        )
        confidence = round(max(0.70, 0.98 - variance / 25), 4) if layer_count > 1 else 0.95
        is_success = confidence >= cfg.min_confidence

        recipe_matched = True
        if recipe is not None:
            tol = max(float(getattr(recipe, 'tolerance_z', 1)), 1.0)
            recipe_matched = (
                abs(measured_height - nominal_height) <= tol
                and abs(measured_spacing - nominal_spacing) <= tol
            )

        plc_payload = {
            'side': side,
            'offset_x': offsets['offset_x'],
            'offset_y': offsets['offset_y'],
            'offset_z': offsets['offset_z'],
            'layer_count': layer_count,
            'layer_heights': layer_heights,
            'layer_spacings': layer_spacings,
            'confidence': confidence,
            'recipe_matched': recipe_matched,
            'product_code': product_code,
        }

        return {
            'side': side,
            'offset_x': offsets['offset_x'],
            'offset_y': offsets['offset_y'],
            'offset_z': offsets['offset_z'],
            'layer_count': layer_count,
            'layer_heights': layer_heights,
            'layer_spacings': layer_spacings,
            'measured_layer_height':  measured_height,
            'measured_layer_spacing': measured_spacing,
            'confidence': confidence,
            'recipe_matched': recipe_matched,
            'is_success': is_success,
            'plc_payload': plc_payload,
            'pillar_roi': None,
            'region_roi': None,
            'result_data': {
                'algorithm': 'simulated_rack_locator_v2',
                'scan_mode': 'single_shot_dual_rack',
                'calibration': getattr(calibration_profile, 'version', None),
                'layer_heights': layer_heights,
                'layer_spacings': layer_spacings,
                'confidence': confidence,
                'plc_payload': plc_payload,
            },
        }
