"""Versioned standard foam-mask management for 2D inspection recipes."""

import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.conf import settings

from .foam_geometry import geometry_config

from .foam_inspector import (
    FOAM_MASK_ALGORITHM_VERSION,
    compute_mask_centroid,
    generate_foam_mask,
)


class FoamTemplateExtractionError(ValueError):
    """The sample did not yield a usable component for a standard region."""


class StandardMaskManager:
    """Build standard masks in fixed, recipe-local search ROIs."""

    SIDES = ('left', 'right')

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or (Path(settings.MEDIA_ROOT) / 'standard_masks'))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _roi_key(side):
        return 'leftFoamROI' if side == 'left' else 'rightFoamROI'

    @staticmethod
    def _stored_path(path):
        try:
            path = path.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
        except ValueError:
            path = path.resolve()
        return str(path).replace('\\', '/')

    def _extract_side(self, image, recipe, side, cfg=None):
        if side not in self.SIDES:
            raise ValueError('side must be left or right')
        if image is None or image.ndim != 3 or image.shape[2] < 3:
            raise ValueError('standard sample must be a valid color image')

        roi = (recipe.roi_config or {}).get(self._roi_key(side))
        if not isinstance(roi, dict):
            raise ValueError(f'{side} foam search ROI is not configured')

        image_height, image_width = image.shape[:2]
        recipe_width = max(int(recipe.image_width or image_width), 1)
        recipe_height = max(int(recipe.image_height or image_height), 1)

        polygon_points = None
        if roi.get('type') == 'polygon':
            points = roi.get('points') or []
            if len(points) < 3:
                raise ValueError(f'{side} polygon ROI needs at least three points')
            polygon_points = np.asarray([
                [float(point[0]) * image_width, float(point[1]) * image_height]
                for point in points
            ], dtype=np.float32)
            x1 = max(0, int(np.floor(polygon_points[:, 0].min())))
            y1 = max(0, int(np.floor(polygon_points[:, 1].min())))
            x2 = min(image_width, int(np.ceil(polygon_points[:, 0].max())))
            y2 = min(image_height, int(np.ceil(polygon_points[:, 1].max())))
        elif all(key in roi for key in ('x1r', 'y1r', 'x2r', 'y2r')):
            x1 = max(0, int(round(float(roi['x1r']) * image_width)))
            y1 = max(0, int(round(float(roi['y1r']) * image_height)))
            x2 = min(image_width, int(round(float(roi['x2r']) * image_width)))
            y2 = min(image_height, int(round(float(roi['y2r']) * image_height)))
        else:
            scale_x = image_width / recipe_width
            scale_y = image_height / recipe_height
            x1 = max(0, int(round(float(roi.get('x', 0)) * scale_x)))
            y1 = max(0, int(round(float(roi.get('y', 0)) * scale_y)))
            x2 = min(image_width, int(round(
                (float(roi.get('x', 0)) + float(roi.get('width', 0))) * scale_x
            )))
            y2 = min(image_height, int(round(
                (float(roi.get('y', 0)) + float(roi.get('height', 0))) * scale_y
            )))

        if x2 - x1 < 5 or y2 - y1 < 5:
            raise ValueError(f'{side} foam search ROI is too small or outside the sample image')

        roi_image = image[y1:y2, x1:x2].copy()
        search_mask = None
        if polygon_points is not None:
            local_points = np.rint(
                polygon_points - np.array([x1, y1], dtype=np.float32)
            ).astype(np.int32)
            search_mask = np.zeros(roi_image.shape[:2], dtype=np.uint8)
            cv2.fillPoly(search_mask, [local_points], 255)
            roi_image = cv2.bitwise_and(roi_image, roi_image, mask=search_mask)

        mask = generate_foam_mask(roi_image, cfg or {})
        if search_mask is not None:
            mask = cv2.bitwise_and(mask, search_mask)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError(f'{"左侧" if side == "left" else "右侧"}标准框内未识别到泡棉，请检查图片和框的位置')

        # Keep all meaningful connected pieces. This preserves gaps/breaks while
        # discarding isolated segmentation noise from the standard sample.
        largest_area = max(cv2.contourArea(contour) for contour in contours)
        min_component_area = max(9.0, largest_area * 0.02)
        clean_mask = np.zeros_like(mask)
        kept = [contour for contour in contours if cv2.contourArea(contour) >= min_component_area]
        cv2.drawContours(clean_mask, kept, -1, 255, -1)

        search_area = int(np.count_nonzero(search_mask)) if search_mask is not None else clean_mask.size
        pixels = int(np.count_nonzero(clean_mask))
        coverage = pixels / max(search_area, 1)
        if coverage < 0.01:
            raise ValueError(f'{"左侧" if side == "left" else "右侧"}标准框内泡棉面积过小（{coverage:.1%}），请检查框的位置')
        # In layer mode these are tight reference boxes, not search regions.
        # A correctly drawn standard box may legitimately be entirely foam.
        if coverage > 0.98 and not (cfg or {}).get('layer_search_roi'):
            raise ValueError(
                f'{"左侧" if side == "left" else "右侧"}泡棉占满搜索框（{coverage:.1%}）。'
                '请扩大搜索框或检查曝光；使用三框模式时请配置本层搜索大框。'
            )

        centroid = compute_mask_centroid(clean_mask)
        bx, by, bw, bh = cv2.boundingRect(cv2.findNonZero(clean_mask))
        return {
            'mask': clean_mask,
            'side': side,
            'pixels': pixels,
            'search_area': search_area,
            'coverage_ratio': round(float(coverage), 4),
            'centroid_x': round(float(centroid[0]), 2),
            'centroid_y': round(float(centroid[1]), 2),
            'bounding_box': {'x': int(bx), 'y': int(by), 'width': int(bw), 'height': int(bh)},
            'roi_snapshot': deepcopy(roi),
        }

    def _write_mask(self, mask, target):
        temp_path = self.base_dir / f'.{target.stem}_{uuid4().hex}.png'
        try:
            if not cv2.imwrite(str(temp_path), mask):
                raise OSError(f'failed to write standard mask: {target}')
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)

    def create_from_sample(self, image, recipe, side, cfg=None):
        """Backward-compatible one-side teaching operation."""
        extracted = self._extract_side(image, recipe, side, cfg)
        target = self.base_dir / f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{side}.png'
        self._write_mask(extracted.pop('mask'), target)
        extracted['path'] = self._stored_path(target)
        return extracted

    def _extract_layer_set(self, image, recipe, cfg, *, verify_drawn_shape=False):
        from .foam_inspector import _inspect_layer_sides, _resolve_side_roi_config
        config = dict(cfg, standard_mask_space='layer-v3', _teach_layer=True)
        rois = _resolve_side_roi_config(config, recipe.pos)
        sides = _inspect_layer_sides(image, rois, config)
        masks = {side: data['mask'] for side, data in sides.items()}
        for side, mask in masks.items():
            label = '左侧' if side == 'left' else '右侧'
            if not np.any(mask):
                raise FoamTemplateExtractionError(f'{label}标准区域未能提取泡棉轮廓，请检查样件亮度和区域位置')
            if sides[side]['coverage_ratio'] < 0.01:
                raise FoamTemplateExtractionError(f'{label}标准区域与泡棉重叠过小，请检查框的位置')
            # A highlight alone is insufficient to accept a switch of algorithm.
            # Check both overlap and leakage against each hand-traced outline.
            if verify_drawn_shape and sides[side]['iou'] < 0.65:
                raise FoamTemplateExtractionError(f'{label}阴影识别轮廓与手绘区域吻合不足，请检查光照和描边')
        # Validate through the production path before writing any templates.
        check = _inspect_layer_sides(image, rois, dict(
            config, _teach_layer=False, standard_masks=masks))
        extracted = {}
        for side, mask in masks.items():
            data = check[side]
            if (abs(data['offset_x_px']) > 0.01 or abs(data['offset_y_px']) > 0.01
                    or data['coverage_ratio'] != 1.0):
                raise ValueError('标准原图自检失败：模板与检测结果不一致')
            center = compute_mask_centroid(mask)
            x, y, w, h = cv2.boundingRect(cv2.findNonZero(mask))
            extracted[side] = {
                'mask': mask, 'side': side, 'pixels': int(np.count_nonzero(mask)),
                'search_area': mask.size, 'coverage_ratio': float(np.count_nonzero(mask) / mask.size),
                'centroid_x': float(center[0]), 'centroid_y': float(center[1]),
                'bounding_box': {'x': x, 'y': y, 'width': w, 'height': h},
                'roi_snapshot': deepcopy(recipe.roi_config[self._roi_key(side)]),
            }
        return extracted

    def create_set_from_sample(self, image, recipe, version, cfg=None):
        """Teach left and right templates from the same qualified image."""
        cfg = dict(cfg or {})
        configured_mode = cfg.get('configured_foam_segmentation', cfg.get('foam_segmentation', 'fixed-threshold'))
        cfg['foam_segmentation'] = configured_mode
        layer_mode = bool(cfg.get('layer_search_roi'))
        if cfg.get('standard_from_roi'):
            # The drawn geometry is the reference; image segmentation only runs
            # during inspection and must never redefine a saved ROI.
            from .foam_inspector import _ratio_box_to_pixels
            width, height = image.shape[1], image.shape[0]
            bounds = _ratio_box_to_pixels(cfg['layer_search_roi'], width, height) if layer_mode else None
            extracted = {}
            for side in self.SIDES:
                box = _ratio_box_to_pixels(cfg['foam_rois'][str(recipe.pos)][side], width, height)
                a, b, c, d = bounds if layer_mode else box
                x1, y1, x2, y2 = box
                mask = np.zeros((d-b, c-a), np.uint8)
                mask[y1-b:y2-b, x1-a:x2-a] = 255
                polygon = cfg.get('polygon_rois', {}).get(str(recipe.pos), {}).get(side)
                if polygon:
                    mask[:] = 0
                    points = np.rint(np.asarray(polygon) * [width, height] - [a, b]).astype(np.int32)
                    cv2.fillPoly(mask, [points], 255)
                center = compute_mask_centroid(mask)
                if center is None:
                    raise ValueError('标准 ROI 面积不能为空')
                x, y, w, h = cv2.boundingRect(cv2.findNonZero(mask))
                extracted[side] = {
                    'mask': mask, 'side': side, 'pixels': int(np.count_nonzero(mask)),
                    'search_area': mask.size, 'coverage_ratio': float(np.count_nonzero(mask) / mask.size),
                    'centroid_x': float(center[0]), 'centroid_y': float(center[1]),
                    'bounding_box': {'x': x, 'y': y, 'width': w, 'height': h},
                    'roi_snapshot': deepcopy(recipe.roi_config[self._roi_key(side)]),
                }
        elif layer_mode:
            try:
                extracted = self._extract_layer_set(image, recipe, cfg)
            except FoamTemplateExtractionError:
                polygons = cfg.get('polygon_rois', {}).get(str(recipe.pos), {})
                if configured_mode != 'fixed-threshold' or not all(polygons.get(s) for s in self.SIDES):
                    raise
                cfg['foam_segmentation'] = 'shadow-graphcut-fast-v2'
                extracted = self._extract_layer_set(image, recipe, cfg, verify_drawn_shape=True)
        else:
            extracted = {side: self._extract_side(image, recipe, side, cfg) for side in self.SIDES}

        targets = {
            side: self.base_dir / (
                f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{version}_{side}.png'
            )
            for side in self.SIDES
        }
        source_target = self.base_dir / (
            f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{version}_source.png'
        )

        for side in self.SIDES:
            self._write_mask(extracted[side].pop('mask'), targets[side])
            extracted[side]['path'] = self._stored_path(targets[side])

        source_temp = self.base_dir / f'.{source_target.stem}_{uuid4().hex}.png'
        try:
            if not cv2.imwrite(str(source_temp), image, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
                raise OSError('failed to archive standard sample image')
            os.replace(source_temp, source_target)
        finally:
            source_temp.unlink(missing_ok=True)

        height, width = image.shape[:2]
        return {
            'version': version,
            'mask_algorithm_version': 'layer-v3' if layer_mode else FOAM_MASK_ALGORITHM_VERSION,
            'mask_space': 'layer-v3' if layer_mode else 'side',
            'configured_foam_segmentation': configured_mode,
            'material_type': cfg.get('material_type', 'unspecified'),
            'fragment_merge': geometry_config(cfg)['fragment_merge'],
            'segmentation_config': {k: cfg.get(k, v) for k, v in
                                    (('foam_min_v', 140), ('foam_max_s', 80))},
            'foam_segmentation': cfg['foam_segmentation'],
            'self_check_passed': layer_mode and not cfg.get('standard_from_roi'),
            'image_width': int(recipe.image_width),
            'image_height': int(recipe.image_height),
            'source_image_width': int(width),
            'source_image_height': int(height),
            'source_image_path': self._stored_path(source_target),
            'roi_config': deepcopy(recipe.roi_config or {}),
            'sides': extracted,
        }
