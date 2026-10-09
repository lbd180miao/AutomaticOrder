"""Teaching preview, spatial recipe persistence and online rack detection."""
import json
import os
import uuid
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import rack_spatial as spatial
from .algorithms import image_io
from .models import RackLocationRecipe, RackLocationResult, VisionTask, VisionTaskType, ResultStatus


def spatial_config(config):
    """Whitelist persisted fields; never retain image rectangles or pixel lines."""
    boxes = config['spatial_rois']
    for name in spatial.NAMES:
        spatial.bounds(boxes[name])
    return {'algorithm_version': spatial.VERSION, 'coordinate_system': 'camera', 'units': 'mm',
            'spatial_rois': {name: {f'{a}{b}': float(boxes[name][f'{a}{b}'])
                                  for a in 'XYZ' for b in ('min', 'max')} for name in spatial.NAMES},
            'voxel_mm': float(config.get('voxel_mm', 0)), 'margin_mm': float(config.get('margin_mm', 5))}


def robot_group_results(service, recipe, groups):
    """Use the same frozen configuration and conversion as the hand-eye workbench."""
    context = {}
    try:
        context = service._recipe_transform_context(recipe)
        converted = {}
        for name in ('A', 'B'):
            compensation = service._robot_compensation_payload({'matrix': groups[name]['delta_T']}, context)
            if compensation is None:
                return {'robot_groups': {}, 'robot_conversion_error': '缺少手眼标定矩阵或拍照位姿，请在手眼标定页面配置并保存。',
                        'transform_context': context}
            if not np.isfinite(np.asarray(compensation['matrix'], dtype=float)).all():
                raise ValueError('机器人偏差矩阵包含无效数值')
            converted[name] = compensation
        return {'robot_groups': converted, 'robot_conversion_error': '', 'transform_context': context}
    except (ValueError, TypeError, KeyError, np.linalg.LinAlgError) as exc:
        return {'robot_groups': {}, 'robot_conversion_error': f'手眼坐标换算失败：{exc}',
                'transform_context': context}


def legacy_axis_frames(service, points, rois, voxel_mm, frame_label, reference=None):
    try:
        cropped = service._crop_local_template_clouds(points, rois)
    except ValueError as exc:
        raise ValueError(f'{frame_label} · {exc}') from exc
    axes = [spatial.fit_region(part, voxel_mm, name, frame_label)
            for name, part in zip(spatial.NAMES, cropped)]
    return {key: spatial.fit_pair(axes[index], axes[1], (reference or {}).get(key), key, frame_label)
            for key, index in [('A', 0), ('B', 2)]}


def reference_axes_from_record(service, recipe, record):
    if record.recipe_id != recipe.pk:
        raise ValueError('标准来源记录与当前配方不一致')
    points = service._load_workbench_pointcloud(record.raw_data_path)
    rois = (record.result_data or {}).get('local_template_rois') or (record.roi_data or {}).get('local_template_rois')
    return legacy_axis_frames(service, points, rois, float((recipe.roi_config or {}).get('voxel_mm', 0)),
                              f'标准帧（记录 #{record.pk}）')


def legacy_robot_groups(service, recipe, cloud, regions):
    """Prefer frozen dual-axis standards; recover older references only from their own record."""
    source_id = (recipe.local_template_std or {}).get('source_result_id')
    metadata = {'robot_groups_recipe_id': recipe.pk, 'robot_groups_reference_result_id': source_id}
    try:
        if not source_id:
            raise ValueError('旧标准缺少来源点云记录，请保存双组标准')
        snapshot = (recipe.local_template_std or {}).get('dual_axis_standard') or {}
        if snapshot:
            if snapshot.get('source_result_id') != source_id or snapshot.get('recipe_id') != recipe.pk:
                raise ValueError('双组标准快照与配方或来源记录不一致，请重新保存标准')
            standard = snapshot['groups']
        else:
            record = RackLocationResult.objects.get(pk=source_id, recipe_id=recipe.pk)
            standard = reference_axes_from_record(service, recipe, record)
        current = legacy_axis_frames(service, cloud, regions, float((recipe.roi_config or {}).get('voxel_mm', 0)),
                                     '当前帧', standard)
        for key in ('A', 'B'):
            delta = np.asarray(current[key]['frame']) @ np.linalg.inv(standard[key]['frame'])
            current[key]['delta_T'] = delta.tolist()
        warnings = list(dict.fromkeys(message for collection in (standard, current)
                                      for group in collection.values() for message in group.get('quality_warnings', [])))
        return {**robot_group_results(service, recipe, current), **metadata, 'quality_warnings': warnings}
    except (ValueError, TypeError, KeyError, OSError, RackLocationResult.DoesNotExist, np.linalg.LinAlgError) as exc:
        return {'robot_groups': {}, 'robot_conversion_error': f'双组偏差计算失败：{exc}', **metadata}


def calculate(service, *, token, recipe, layer_no=1, save_record=False, cloud=None):
    config = spatial_config(recipe.roi_config)
    if cloud is None:
        cloud = service._load_workbench_pointcloud(token)
    standard = recipe.local_template_std or {}
    if standard.get('algorithm_version') != spatial.VERSION:
        raise ValueError('请先预览并保存双组轴线标准配方')
    result = spatial.compute(cloud, config, standard)
    if not result['has_standard']:
        raise ValueError('配方缺少 A/B 双组标准轴线，请重新示教')
    visual = spatial.preview(cloud, config, result)
    image = image_io.pointcloud_to_preview(cloud) if np.asarray(cloud).ndim == 3 else None
    image_path = ''
    if image is not None:
        for (name, box), color in zip(visual['boxes'].items(), ((255,190,60),(30,170,255),(210,70,240))):
            if box['pixels']:
                vertices = np.clip(np.asarray(box['pixels']), -100000, 100000).astype(int)
                for a,b in spatial.EDGES:
                    cv2.line(image, tuple(vertices[a]), tuple(vertices[b]), color, 2)
        if visual['spacing_pixels']:
            a,b = np.clip(visual['spacing_pixels'], -100000, 100000).astype(int)
            cv2.line(image, tuple(a), tuple(b), (70,230,80), 2)
            cv2.putText(image, f"{result['layer_spacing_mm']:.1f} mm", tuple(a), cv2.FONT_HERSHEY_SIMPLEX, .6, (70,230,80), 2)
        image_path, _, _ = image_io.save_image(image, 'rack_dual_axis', rel_dir='vision/rack_workbench')
    # Two outputs must not silently collapse into the legacy one-pose PLC format.
    payload = {**result, 'recipe_id': recipe.pk, 'layer_no': int(layer_no), 'locate_ok': True,
               'is_success': True, 'direct_detection_mode': True, 'confidence': min(a['linearity'] for a in result['axes'].values()),
               'measured_layer_spacing': result['layer_spacing_mm'], 'layer_spacing_method': 'dual_axis_origins_3d',
               'spatial_rois': config['spatial_rois'], 'spatial_preview': visual,
               'result_image_url': settings.MEDIA_URL + image_path if image_path else '',
               'warning_message': '；'.join(filter(None, [result.get('warning_message'), visual['projection_warning']])),
               'plc_payload': {'compensation_valid': False, 'groups': result['groups'],
                               'reason': '双组补偿需要分别绑定放置层，不能写入旧单组补偿寄存器'}}
    payload.update(robot_group_results(service, recipe, result['groups']))
    if save_record:
        with transaction.atomic():
            task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS,
                                             started_at=timezone.now(), finished_at=timezone.now())
            record = RackLocationResult.objects.create(vision_task=task, recipe=recipe,
                side=recipe.rack_side, position_no=recipe.position_no, layer_no=int(layer_no),
                is_success=True, is_recipe_matched=True, confidence=payload['confidence'],
                measured_layer_spacing=result['layer_spacing_mm'], raw_data_path=token or '',
                result_image_path=image_path, roi_data=config, result_data={k:v for k,v in payload.items() if k != 'spatial_preview'},
                plc_write_status='SKIPPED')
        payload['result_id'] = record.pk
    return payload


@require_POST
def teach(request):
    try:
        from .rack_location import RackLocationService
        data = json.loads(request.body)
        recipe = RackLocationRecipe.objects.get(pk=data.get('recipe_id'))
        service = RackLocationService()
        action = data.get('action', 'preview')
        if action == 'save':
            candidate = signing.loads(data['candidate'], salt='rack-spatial-teach', max_age=1800)
            if candidate['recipe_id'] != recipe.pk:
                raise ValueError('预览与当前配方不一致，请重新预览')
            config = {**candidate.get('editor_config', {}), **spatial_config(candidate['config'])}
            standard = candidate['standard']
            root = Path(settings.MEDIA_ROOT) / 'vision' / 'rack_recipes' / str(recipe.pk)
            root.mkdir(parents=True, exist_ok=True)
            path = root / 'roi_config.json'
            temporary = root / f'.{uuid.uuid4().hex}.tmp'
            try:
                temporary.write_text(json.dumps({**config, 'standard_axes': standard}, ensure_ascii=False, indent=2), encoding='utf-8')
                with transaction.atomic():
                    locked = RackLocationRecipe.objects.select_for_update().get(pk=recipe.pk)
                    locked.roi_config = config
                    locked.local_template_std = standard
                    locked.save(update_fields=['roi_config', 'local_template_std'])
                    os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return JsonResponse({'success': True, 'roi_config': config, 'local_template_std': standard})
        if action != 'preview':
            raise ValueError('不支持的示教操作')
        cloud = service._load_workbench_pointcloud(data.get('pointcloud_token'))
        config = spatial_config({'spatial_rois': spatial.teach_boxes(cloud, data.get('local_template_rois'), data.get('margin_mm', 0)),
                                 'voxel_mm': data.get('voxel_mm', 0), 'margin_mm': data.get('margin_mm', 0)})
        standard = spatial.compute(cloud, config)
        # Persist editor positions for reload; spatial_config keeps them out of computation.
        editor_config = {key: (data.get('roi_config') or recipe.roi_config or {}).get(key)
                         for key in ('target_roi', 'local_template_rois', 'layer_spacing_line')}
        editor_config['local_template_rois'] = data.get('local_template_rois')
        candidate = signing.dumps({'recipe_id': recipe.pk, 'config': config, 'standard': standard, 'editor_config': editor_config}, salt='rack-spatial-teach', compress=True)
        return JsonResponse({'success': True, 'candidate': candidate, 'roi_config': config,
                             'standard': standard, 'preview': spatial.preview(cloud, config, standard)})
    except (ValueError, KeyError, TypeError, OSError, signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
