"""File-based standard foam mask management for factory recipes."""

import os
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.conf import settings

from .foam_inspector import compute_mask_centroid, generate_foam_mask


class StandardMaskManager:
    """Create one active left/right mask image per foam recipe."""

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or (Path(settings.MEDIA_ROOT) / 'standard_masks'))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_from_sample(self, image, recipe, side, cfg=None):
        if side not in {'left', 'right'}:
            raise ValueError('side must be left or right')
        if image is None or image.ndim != 3 or image.shape[2] < 3:
            raise ValueError('standard sample must be a valid color image')

        roi_key = 'leftFoamROI' if side == 'left' else 'rightFoamROI'
        roi = (recipe.roi_config or {}).get(roi_key)
        if not isinstance(roi, dict):
            raise ValueError(f'{side} foam ROI is not configured')

        image_height, image_width = image.shape[:2]
        recipe_width = max(int(recipe.image_width or image_width), 1)
        recipe_height = max(int(recipe.image_height or image_height), 1)
        scale_x = image_width / recipe_width
        scale_y = image_height / recipe_height
        x1 = max(0, int(round(float(roi.get('x', 0)) * scale_x)))
        y1 = max(0, int(round(float(roi.get('y', 0)) * scale_y)))
        x2 = min(image_width, int(round((float(roi.get('x', 0)) + float(roi.get('width', 0))) * scale_x)))
        y2 = min(image_height, int(round((float(roi.get('y', 0)) + float(roi.get('height', 0))) * scale_y)))
        if x2 - x1 < 5 or y2 - y1 < 5:
            raise ValueError(f'{side} foam ROI is too small or outside the sample image')

        mask = generate_foam_mask(image[y1:y2, x1:x2], cfg or {})
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError(
                f'在{"左" if side == "left" else "右"}侧 ROI 区域内未检测到泡棉，'
                '请检查 ROI 是否正确框住了泡棉，或图片曝光是否合适'
            )

        clean_mask = np.zeros_like(mask)
        largest = max(contours, key=cv2.contourArea)
        cv2.drawContours(clean_mask, [largest], -1, 255, -1)
        coverage = np.count_nonzero(clean_mask) / clean_mask.size
        if coverage < 0.01:
            raise ValueError(
                f'{"左" if side == "left" else "右"}侧标准模板面积太小（覆盖率 {coverage*100:.1f}%），'
                '请确认图片中有泡棉并重新框选 ROI'
            )
        if coverage > 0.98:
            raise ValueError(
                f'{"左" if side == "left" else "右"}侧检测到的泡棉几乎填满了整张图（覆盖率 {coverage*100:.1f}%），'
                '可能是背景被误识别，请检查图片或调整 ROI 范围'
            )

        target = self.base_dir / f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{side}.png'
        temp_path = self.base_dir / f'.{target.stem}_{uuid4().hex}.png'
        try:
            if not cv2.imwrite(str(temp_path), clean_mask):
                raise OSError(f'failed to write standard mask: {target}')
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)

        centroid = compute_mask_centroid(clean_mask)
        try:
            stored_path = target.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
        except ValueError:
            stored_path = target.resolve()
        return {
            'path': str(stored_path).replace('\\', '/'),
            'side': side,
            'pixels': int(np.count_nonzero(clean_mask)),
            'coverage_ratio': round(float(coverage), 4),
            'centroid_x': round(float(centroid[0]), 2),
            'centroid_y': round(float(centroid[1]), 2),
        }
