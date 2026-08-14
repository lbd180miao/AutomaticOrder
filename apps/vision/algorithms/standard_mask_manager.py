"""Versioned standard foam-mask management for 2D inspection recipes."""

import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.conf import settings

from .foam_inspector import (
    FOAM_MASK_ALGORITHM_VERSION,
    compute_mask_centroid,
    generate_foam_mask,
)


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
            raise ValueError(f'No foam was detected inside the {side} search ROI')

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
            raise ValueError(f'{side} standard foam area is too small ({coverage:.1%})')
        if coverage > 0.98:
            raise ValueError(
                f'{side} detected foam fills almost the entire search ROI ({coverage:.1%}); '
                'enlarge the search ROI or check exposure'
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

    def create_set_from_sample(self, image, recipe, version, cfg=None):
        """Teach left and right templates from the same qualified image."""
        extracted = {
            side: self._extract_side(image, recipe, side, cfg)
            for side in self.SIDES
        }

        targets = {
            side: self.base_dir / (
                f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{version}_{side}.png'
            )
            for side in self.SIDES
        }
        source_target = self.base_dir / (
            f'foam_recipe_{recipe.pk}_pos{recipe.pos}_{version}_source.jpg'
        )

        for side in self.SIDES:
            self._write_mask(extracted[side].pop('mask'), targets[side])
            extracted[side]['path'] = self._stored_path(targets[side])

        source_temp = self.base_dir / f'.{source_target.stem}_{uuid4().hex}.jpg'
        try:
            if not cv2.imwrite(str(source_temp), image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                raise OSError('failed to archive standard sample image')
            os.replace(source_temp, source_target)
        finally:
            source_temp.unlink(missing_ok=True)

        height, width = image.shape[:2]
        return {
            'version': version,
            'mask_algorithm_version': FOAM_MASK_ALGORITHM_VERSION,
            'image_width': int(recipe.image_width),
            'image_height': int(recipe.image_height),
            'source_image_width': int(width),
            'source_image_height': int(height),
            'source_image_path': self._stored_path(source_target),
            'roi_config': deepcopy(recipe.roi_config or {}),
            'sides': extracted,
        }
