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
        reference_context = (recipe.local_template_std or {}).get('transform_context')
        converted = {}
        for name in ('A', 'B'):
            if reference_context:
                compensation = service._robot_compensation_payload(
                    {'matrix': groups[name]['delta_T']}, context, reference_context)
            else:
                compensation = service._robot_compensation_payload({'matrix': groups[name]['delta_T']}, context)
            if compensation is None:
                return {'robot_groups': {}, 'robot_conversion_error': '缺少手眼标定矩阵或拍照位姿，请在手眼标定页面配置并保存。',
                        'transform_context': context}
            if not np.isfinite(np.asarray(compensation['matrix'], dtype=float)).all():
                raise ValueError('机器人偏差矩阵包含无效数值')
            compensation.update(reference_point_motion(groups[name], compensation))
            converted[name] = compensation
        return {'robot_groups': converted, 'robot_conversion_error': '', 'transform_context': context,
                'robot_groups_message': ('使用标准帧与当前帧各自保存的拍照位姿换算；相机移动后须更新拍照位姿。'
                    if reference_context else '旧标准未保存拍照位姿，当前按相同拍照位姿换算；跨距离使用前请重新保存标准并更新当前拍照位姿。')}
    except (ValueError, TypeError, KeyError, np.linalg.LinAlgError) as exc:
        return {'robot_groups': {}, 'robot_conversion_error': f'手眼坐标换算失败：{exc}',
                        'transform_context': context}


def reference_point_motion(group, compensation):
    """Separate displacement at the fitted rack origin from matrix translation.

    A rigid delta has t = displacement(p) + (I-R)p. Its translation column
    therefore cannot be interpreted as displacement at an arbitrary workpoint.
    Keep the robot compensation matrix intact and expose both quantities.
    """
    current = np.asarray(group['frame'], dtype=float)[:, 3]
    delta = np.asarray(group['delta_T'], dtype=float)
    reference = np.linalg.solve(delta, current)
    base_camera = np.asarray(compensation['T_base_camera'], dtype=float)
    reference_camera = np.asarray(compensation.get('T_base_camera_standard', base_camera), dtype=float)
    displacement = (base_camera @ current - reference_camera @ reference)[:3]
    matrix_translation = np.asarray(compensation['matrix'], dtype=float)[:3, 3]
    return {
        'reference_point_displacement_mm': dict(zip('xyz', displacement.tolist())),
        'rotation_lever_term_mm': dict(zip('xyz', (matrix_translation - displacement).tolist())),
        'reference_point_meaning': 'fitted_pair_origin_in_robot_base',
    }


def legacy_axis_frames(service, points, rois, voxel_mm, frame_label, reference=None):
    import logging
    _logger = logging.getLogger(__name__)
    try:
        cropped = service._crop_local_template_clouds(points, rois)
    except ValueError as exc:
        raise ValueError(f'{frame_label} · {exc}') from exc
    # Reference normals prefer the same physical face but do not force weak matches.
    reference = reference or {}
    reference_planes = [reference.get('A', {}).get('plane_models', {}).get('beam'),
                        reference.get('A', {}).get('plane_models', {}).get('pillar'),
                        reference.get('B', {}).get('plane_models', {}).get('beam')]
    planes = [spatial.fit_region(part, name, frame_label, ref)
              for name, part, ref in zip(spatial.NAMES, cropped, reference_planes)]
    _logger.info('[legacy_axis_frames] %s 三平面拟合成功: %s',
                 frame_label,
                 {p['label'] if 'label' in p else name: {
                     'normal': [round(x,3) for x in p['normal']],
                     'rms_mm': round(p.get('rms_mm',0),3)
                  } for name, p in zip(spatial.NAMES, planes)})
    result = {}
    for key, index in [('A', 0), ('B', 2)]:
        try:
            result[key] = spatial.fit_pair(planes[index], planes[1], reference.get(key), key, frame_label)
            _logger.info('[legacy_axis_frames] %s %s组 fit_pair成功, origin=%s',
                         frame_label, key, [round(x,2) for x in result[key]['origin']])
        except ValueError as exc:
            _logger.warning('[legacy_axis_frames] %s %s组 fit_pair失败: %s', frame_label, key, exc)
            raise
    return result


def reference_axes_from_record(service, recipe, record):
    if record.recipe_id != recipe.pk:
        raise ValueError('标准来源记录与当前配方不一致')
    try:
        points = service._load_workbench_pointcloud(record.raw_data_path)
    except (ValueError, OSError) as exc:
        raise ValueError(
            f'标准记录 #{record.pk} 的原始点云不可用：{exc}。'
            '请恢复该标准点云及单位文件，或重新采集标准料架并保存标准；重新采集当前帧不能修复旧标准'
        ) from exc
    rois = (record.result_data or {}).get('local_template_rois') or (record.roi_data or {}).get('local_template_rois')
    return legacy_axis_frames(service, points, rois, float((recipe.roi_config or {}).get('voxel_mm', 0)),
                              f'标准帧（记录 #{record.pk}）')


def legacy_robot_groups(service, recipe, cloud, regions):
    """Prefer frozen dual-axis standards; recover older references only from their own record."""
    source_id = (recipe.local_template_std or {}).get('source_result_id')
    metadata = {'robot_groups_recipe_id': recipe.pk, 'robot_groups_reference_result_id': source_id}

    def pending_standard(reason=''):
        try:
            current = legacy_axis_frames(service, cloud, regions,
                float((recipe.roi_config or {}).get('voxel_mm', 0)), '当前帧')
        except (ValueError, TypeError, KeyError, OSError, np.linalg.LinAlgError) as exc:
            return {**metadata, 'groups': {}, 'robot_groups': {},
                    'robot_groups_status': 'calculation_failed',
                    'robot_conversion_error': f'当前帧交点计算失败：{exc}'}
        return {**metadata, 'groups': current, 'robot_groups': {}, 'robot_conversion_error': '',
                'quality_warnings': list(dict.fromkeys(w for g in current.values() for w in g.get('quality_warnings', []))),
                'robot_groups_status': 'standard_unavailable' if source_id else 'standard_not_set',
                'robot_groups_message': (
                    f'旧标准 #{source_id} 暂不可用；' if source_id else '尚未保存双组标准；'
                ) + '当前帧拟合和测量不受影响，暂不计算相对标准的 A/B 偏差。'
                    '需要偏差时，请在标准料架位置计算后点击“保存为标准”。',
                'standard_reference_diagnostic': reason}

    if not source_id:
        return pending_standard()
    try:
        snapshot = (recipe.local_template_std or {}).get('dual_axis_standard') or {}
        if snapshot:
            if snapshot.get('source_result_id') != source_id or snapshot.get('recipe_id') != recipe.pk:
                raise ValueError('双组标准快照与配方或来源记录不一致，请重新保存标准')
            standard = snapshot['groups']
        else:
            record = RackLocationResult.objects.get(pk=source_id, recipe_id=recipe.pk)
            standard = reference_axes_from_record(service, recipe, record)
    except (ValueError, TypeError, KeyError, OSError, RackLocationResult.DoesNotExist, np.linalg.LinAlgError) as exc:
        return pending_standard(str(exc))
    try:
        current = legacy_axis_frames(service, cloud, regions, float((recipe.roi_config or {}).get('voxel_mm', 0)),
                                     '当前帧', standard)
        for key in ('A', 'B'):
            delta = np.asarray(current[key]['frame']) @ np.linalg.inv(standard[key]['frame'])
            current[key]['delta_T'] = delta.tolist()
        warnings = list(dict.fromkeys(message for collection in (standard, current)
                                      for group in collection.values() for message in group.get('quality_warnings', [])))
        converted = robot_group_results(service, recipe, current)
        return {**converted, **metadata, 'quality_warnings': warnings,
                'groups': current,  # 添加当前帧的 groups 数据
                'robot_groups_status': 'ready' if converted.get('robot_groups') else 'conversion_unavailable'}
    except (ValueError, TypeError, KeyError, OSError, RackLocationResult.DoesNotExist, np.linalg.LinAlgError) as exc:
        import logging
        logging.getLogger(__name__).warning(
            '[legacy_robot_groups] 双组偏差计算失败 recipe=%s regions_keys=%s error=%s',
            recipe.pk,
            list(regions.keys()) if isinstance(regions, dict) else type(regions).__name__,
            exc)
        # 即使有标准但计算失败，仍然尝试单独算出当前帧的交点位置供前端显示
        try:
            current_only = legacy_axis_frames(service, cloud, regions,
                float((recipe.roi_config or {}).get('voxel_mm', 0)), '当前帧（无偏差）')
        except Exception:
            current_only = {}
        return {'robot_groups': {}, 'groups': current_only,
                'robot_conversion_error': f'双组偏差计算失败：{exc}',
                'robot_groups_status': 'calculation_failed', **metadata}


def calculate(service, *, token, recipe, layer_no=1, save_record=False, cloud=None):
    import logging
    logger = logging.getLogger(__name__)
    
    config = spatial_config(recipe.roi_config)
    if cloud is None:
        cloud = service._load_workbench_pointcloud(token)
    capture_metadata = service._frame_metadata(token, cloud)
    standard = recipe.local_template_std or {}
    
    # 即使没有标准模板,也计算当前的groups(允许查看当前交点位置)
    has_standard = bool(standard.get('algorithm_version') == spatial.VERSION and standard.get('groups'))
    
    logger.info(f"[spatial.calculate] has_standard={has_standard}, algorithm_version={standard.get('algorithm_version')}, spatial.VERSION={spatial.VERSION}")
    
    if has_standard:
        result = spatial.compute(cloud, config, standard)
        logger.info(f"[spatial.calculate] 有标准模板, groups keys: {list(result.get('groups', {}).keys())}")
    else:
        # 无标准模板:只计算当前frame,交点位置仍然会被计算
        result = spatial.compute(cloud, config, standard=None)
        logger.info(f"[spatial.calculate] 无标准模板, 只计算当前frame, groups keys: {list(result.get('groups', {}).keys())}")
    
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
    
    # 基础payload(无论是否有标准都包含当前groups)
    payload = {**result, 'recipe_id': recipe.pk, 'layer_no': int(layer_no), 'locate_ok': True,
               'capture_metadata': capture_metadata,
               'is_success': True, 'has_standard': has_standard, 'direct_detection_mode': True, 
               'confidence': min(1.0 - p['rms_mm']/100 for p in result.get('planes', {}).values()),
               'measured_layer_spacing': result['layer_spacing_mm'], 'layer_spacing_method': 'dual_axis_origins_3d',
               'spatial_rois': config['spatial_rois'], 'spatial_preview': visual,
               'result_image_url': settings.MEDIA_URL + image_path if image_path else '',
               'warning_message': '；'.join(filter(None, [
                   result.get('warning_message'), 
                   visual['projection_warning'],
                   '当前仅显示测量值,需要建立标准模板才能计算偏差' if not has_standard else None
               ])),
               'plc_payload': {'compensation_valid': False, 'groups': result['groups'],
                               'reason': '双组补偿需要分别绑定放置层，不能写入旧单组补偿寄存器' if has_standard else '未建立标准模板,无法计算补偿'}}
    
    # 只有存在标准时才进行机器人坐标转换
    if has_standard:
        payload.update(robot_group_results(service, recipe, result['groups']))
    
    else:
        payload.update(robot_groups={}, robot_groups_status='standard_not_set',
                       robot_conversion_error='',
                       robot_groups_message='当前交点已计算；未保存标准模板，暂不计算误差。')

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
        standard['transform_context'] = service._recipe_transform_context(recipe)
        # Persist editor positions for reload; spatial_config keeps them out of computation.
        editor_config = {key: (data.get('roi_config') or recipe.roi_config or {}).get(key)
                         for key in ('target_roi', 'local_template_rois', 'layer_spacing_line')}
        editor_config['local_template_rois'] = data.get('local_template_rois')
        candidate = signing.dumps({'recipe_id': recipe.pk, 'config': config, 'standard': standard, 'editor_config': editor_config}, salt='rack-spatial-teach', compress=True)
        return JsonResponse({'success': True, 'candidate': candidate, 'roi_config': config,
                             'standard': standard, 'preview': spatial.preview(cloud, config, standard)})
    except (ValueError, KeyError, TypeError, OSError, signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
