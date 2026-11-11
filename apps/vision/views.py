import json
import logging
import shutil
import tempfile
import time
import uuid
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from apps.core.constants import RackSide
from apps.devices.models import Device
from apps.production.models import Rack, RackRecipe, RackRecipeVisionMapping
from apps.production.rack_recipe_service import (
    RackPositionResolver,
    serialize_rack_recipe,
    validate_rack_recipe,
)
from .algorithms.standard_mask_manager import StandardMaskManager
from .models import (
    CalibrationProfile,
    FoamProductLayout,
    FoamInspectionResult,
    RackLocationROI3D,
    RackLocationRecipe,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)
from .recipe_utils import (
    build_foam_inspection_config,
    ensure_default_foam_2d_recipes,
    get_foam_standard_template_status,
    get_active_foam_2d_recipe_by_pos,
    has_complete_foam_template_side_metadata,
    serialize_recipe,
    foam_identity_summary,
)
from .services import VisionService
from .rack_location import (
    PlcVisionResultWriter,
    Rack3DLocator,
    RackLocationService,
    locate_semantics,
    normalize_locate_type,
    result_payload as rack_location_result_payload,
    roi3d_to_dict,
)

logger = logging.getLogger(__name__)


def _decode_uploaded_image(uploaded_file):
    if uploaded_file is None:
        raise ValueError('未上传图片文件')

    max_bytes = int(getattr(settings, 'VISION_MAX_UPLOAD_BYTES', 25 * 1024 * 1024))
    if uploaded_file.size > max_bytes:
        raise ValueError(f'图片不能超过 {max_bytes // (1024 * 1024)} MB')

    image = cv2.imdecode(
        np.frombuffer(uploaded_file.read(), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    if image is None:
        raise ValueError('无法解码图片，请确保上传的是有效的图片文件')

    max_pixels = int(getattr(settings, 'VISION_MAX_IMAGE_PIXELS', 25_000_000))
    if image.shape[0] * image.shape[1] > max_pixels:
        raise ValueError(f'图片像素数不能超过 {max_pixels}')
    return image


def task_list(request):
    """视觉任务列表页面，显示最近200条任务记录
    
    优化查询性能并处理可能的数据库错误：
    1. 使用 select_related 预加载外键关联（product, rack）
    2. 使用 prefetch_related 预加载反向关联（images, foam_results, rack_results）
    3. 限制返回最近 200 条记录
    """
    try:
        # 尝试标准查询
        tasks = (
            VisionTask.objects
            .select_related('product', 'rack')
            .prefetch_related('images', 'foam_results', 'rack_results')
            .order_by('-created_at')[:200]
        )
        # 强制执行查询以检测错误
        list(tasks[:1])
    except Exception as e:
        # 如果 select_related 失败（可能是外键表问题），尝试不使用它
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f'VisionTask query with select_related failed: {str(e)}')
        
        try:
            tasks = (
                VisionTask.objects
                .prefetch_related('images', 'foam_results', 'rack_results')
                .order_by('-created_at')[:200]
            )
            # 强制执行查询
            list(tasks[:1])
        except Exception as e2:
            # 最后尝试：只查询基本字段
            logger.error(f'VisionTask query with prefetch_related also failed: {str(e2)}')
            try:
                tasks = VisionTask.objects.all().order_by('-created_at')[:200]
                list(tasks[:1])
            except Exception as e3:
                # 完全失败，返回空列表并显示错误
                logger.error(f'All VisionTask queries failed: {str(e3)}')
                messages.error(request, f'数据库查询错误：{str(e3)}。请检查数据库迁移状态。')
                tasks = []
    
    return render(request, 'vision/task_list.html', {'tasks': tasks})


def _get_depth_roi_debug_context():
    recipe, _ = RackRecipe.objects.get_or_create(
        recipe_code='DEBUG-DEPTH-ROI',
        defaults={
            'name': '深度相机ROI调试配方',
            'rack_type': 'DEBUG',
            'layer_count': 4,
            'quantity_per_layer': 6,
            'total_quantity': 24,
            'layer_height': 120,
            'layer_spacing': 150,
            'tolerance_x': 2,
            'tolerance_y': 2,
            'tolerance_z': 3,
            'is_active': True,
        },
    )
    rack, _ = Rack.objects.get_or_create(
        rack_code='DEBUG-RACK',
        defaults={
            'rack_type': 'DEBUG',
            'current_recipe': recipe,
            'status': 'DEBUG',
            'position_side': 'BOTH',
        },
    )
    if rack.current_recipe_id != recipe.id:
        rack.current_recipe = recipe
        rack.save(update_fields=['current_recipe', 'updated_at'])
    return rack, recipe


def task_detail(request, pk):
    """单个视觉任务详情：并排展示原图与带 ROI 的结果图。"""
    task = get_object_or_404(
        VisionTask.objects.select_related('product', 'rack'), pk=pk
    )
    images = list(task.images.all())
    original = next((i for i in images if i.image_type == 'ORIGINAL'), None)
    depth_img = next((i for i in images if i.image_type == 'DEPTH'), None)
    if original is None:
        original = depth_img
    result_img = next((i for i in images if i.image_type == 'RESULT'), None)
    rack_result = task.rack_results.first()
    foam_result = task.foam_results.first()

    # Pre-compute dual-point XYZ delta rows for the template
    dp_rows = []
    if rack_result and rack_result.result_data.get('source') in ('dual_point_evaluate', 'cloud_match'):
        result = rack_result.result_data.get('result') or {}
        reference = (rack_result.result_data.get('reference') or {}).get('measurement') or result.get('reference') or {}
        ref_points = {p['name']: p for p in reference.get('points') or []}
        for pt in result.get('points') or []:
            name = pt.get('name', '')
            cur = pt.get('xyz')
            ref = ref_points.get(name, {}).get('xyz')
            fmt3 = lambda v: f'{v:.3f}' if isinstance(v, (int, float)) else '—'
            if cur and len(cur) == 3:
                cur_str = ' / '.join(fmt3(v) for v in cur)
            else:
                cur_str = '—'
            if ref and len(ref) == 3:
                ref_str = ' / '.join(fmt3(v) for v in ref)
            else:
                ref_str = '—'
            if cur and ref and len(cur) == 3 and len(ref) == 3:
                delta_str = ' / '.join(fmt3(cur[i] - ref[i]) for i in range(3))
            else:
                delta_str = '—'
            dp_rows.append({'name': name, 'ref': ref_str, 'cur': cur_str, 'delta': delta_str})

    return render(request, 'vision/task_detail.html', {
        'task': task,
        'original': original,
        'result_img': result_img,
        'depth_img': depth_img,
        'rack_result': rack_result,
        'foam_result': foam_result,
        'dp_rows': dp_rows,
    })



@require_POST
def delete_task(request, pk):
    """Delete a vision task record and its related database results."""
    task = get_object_or_404(VisionTask, pk=pk)
    task_label = f'{task.get_task_type_display()} #{task.pk}'
    task.delete()
    messages.success(request, f'已删除视觉记录：{task_label}')
    return redirect('vision:task_list')


def rack_results(request):
    results = (
        RackLocationResult.objects
        .select_related('vision_task', 'rack', 'vision_task__product')
        .prefetch_related('vision_task__images')
        .order_by('-created_at')[:200]
    )
    return render(request, 'vision/rack_result_detail.html', {'results': results})


def foam_results(request):
    results = (
        FoamInspectionResult.objects
        .select_related('vision_task', 'product', 'rack')
        .prefetch_related('vision_task__images')
        .order_by('-created_at')[:200]
    )
    for result in results:
        snapshot = result.result_data or {}
        algorithm = snapshot.get('effective_config') or (snapshot.get('recipe') or {}).get('algorithm_config') or {}
        result.foam_identity = foam_identity_summary(algorithm) if algorithm else {'material_label': '未标注颜色', 'segmentation_label': '未记录算法'}
        result.saved_image_url = (
            f'/vision/api/foam/records/{result.id}/image/original/'
            if (foam_archive.root() / f'{result.id}_original.png').is_file() else ''
        )
    return render(request, 'vision/foam_result_detail.html', {'results': results})



def foam_inspector_interactive(request):
    """One workbench for foam ROI teaching and inspection."""
    if request.GET.get('new') == '1':
        return redirect('/vision/recipes/?tab=foam2d')
    return render(request, 'vision/foam_inspector_interactive.html', {
        'foam_layout_id': request.GET.get('layout_id', ''),
        'workbench_title': '2D 泡棉工作台',
    })


def recipe_management(request):
    """视觉配方管理页面（独立页面）"""
    return render(request, 'vision/recipe_management.html')


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


from . import foam_archive


def _result_payload(foam_result):
    task = foam_result.vision_task
    result_image = task.images.filter(image_type='RESULT').first()
    original_image = task.images.filter(image_type='ORIGINAL').first()
    payload = {
        'result_id': foam_result.id,
        'task_id': task.id,
        'position_index': foam_result.position_index,
        'is_present': foam_result.is_present,
        'is_aligned': foam_result.is_aligned,
        'has_lifted_edge': foam_result.has_lifted_edge,
        'score': float(foam_result.score),
        'is_passed': foam_result.is_passed,
        'offset_x_px': float(foam_result.offset_x_px),
        'offset_y_px': float(foam_result.offset_y_px),
        'offset_x_mm': float(foam_result.offset_x_mm),
        'offset_y_mm': float(foam_result.offset_y_mm),
        'coverage_ratio': float(foam_result.coverage_ratio),
        'defect_type': foam_result.defect_type,
        'result_image_url': result_image.file.url if result_image else '',
        'original_image_url': original_image.file.url if original_image else '',
    }
    for key in (
        'offset_distance_px',
        'offset_distance_mm',
        'iou',
        'detected_pixels',
        'standard_pixels',
        'is_complete',
        'sides',
        'timings_ms',
        'inspection_status', 'quality_failures', 'quality_version', 'effective_config',
        'product_registration', 'coordinate_space',
    ):
        if key in foam_result.result_data:
            payload[key] = foam_result.result_data[key]
    if foam_result.result_data.get('recipe'):
        payload['recipe'] = foam_result.result_data['recipe']
    for kind in ('original', 'result'):
        if foam_archive.has_image(foam_result.id, kind):
            payload[f'{kind}_image_url'] = f'/vision/api/foam/records/{foam_result.id}/image/{kind}/'
    return payload


def _save_foam_standard_template(recipe, image, source_metadata=None):
    """Persist both foam masks and their ROI-local position metadata."""
    version = timezone.now().strftime('v%Y%m%d%H%M%S%f')
    template = StandardMaskManager().create_set_from_sample(
        image,
        recipe,
        version,
        build_foam_inspection_config(recipe),
    )
    built_at = timezone.now()
    template['built_at'] = built_at.isoformat()
    if source_metadata:
        template['source'] = dict(source_metadata)

    thresholds = dict(recipe.threshold_config or {})
    thresholds['standardMaskPaths'] = {
        side: template['sides'][side]['path'] for side in ('left', 'right')
    }
    thresholds['requireStandardTemplate'] = True
    recipe.threshold_config = thresholds
    recipe.standard_template_config = template
    recipe.standard_template_version = version
    recipe.standard_template_built_at = built_at
    recipe.save(update_fields=[
        'threshold_config',
        'standard_template_config',
        'standard_template_version',
        'standard_template_built_at',
        'updated_at',
    ])
    return template


@require_http_methods(['GET'])
def api_vision_recipes(request):
    qs = VisionRecipe.objects.filter(recipe_type__in=[item[0] for item in VisionRecipe.RECIPE_TYPE_CHOICES]).select_related('foam_product_layout__rack_spec')
    recipe_type = request.GET.get('recipe_type')
    pos = request.GET.get('pos')
    camera_side = request.GET.get('camera_side')
    is_active = request.GET.get('is_active')
    layout_id = request.GET.get('layout_id')
    if recipe_type:
        qs = qs.filter(recipe_type=recipe_type)
    if pos not in (None, ''):
        qs = qs.filter(pos=int(pos))
    if camera_side:
        qs = qs.filter(camera_side=camera_side)
    if is_active not in (None, ''):
        qs = qs.filter(is_active=_as_bool(is_active))
    if layout_id not in (None, ''):
        qs = qs.filter(foam_product_layout_id=int(layout_id))
    return JsonResponse({
        'success': True,
        'recipes': [serialize_recipe(recipe) for recipe in qs.order_by('recipe_type', 'pos', '-updated_at')],
    })


@require_http_methods(['GET'])
def api_foam_recipe_by_pos(request):
    pos = int(request.GET.get('pos', 0))
    layout_id = request.GET.get('layout_id')
    try:
        recipe = get_active_foam_2d_recipe_by_pos(pos, layout_id=layout_id)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'recipe': serialize_recipe(recipe) if recipe else None,
    })


@require_POST
def api_foam_recipe_defaults(request):
    recipes = ensure_default_foam_2d_recipes()
    return JsonResponse({
        'success': True,
        'recipes': [serialize_recipe(recipe) for recipe in recipes],
    })


@require_POST
def api_foam_recipe_save(request):
    try:
        with transaction.atomic():
            body = json.loads(request.POST.get('payload', '{}') if request.content_type == 'multipart/form-data' else (request.body or '{}'))
            if body.get('roi_only'):
                current = get_object_or_404(VisionRecipe.objects.select_for_update(),
                                            pk=body.get('id'), recipe_type='FOAM_2D')
                body = {key: body[key] for key in ('id', 'roi_config', 'image_width',
                        'image_height', 'preview_capture_token') if key in body}
                body.update({'simple_save': True, 'pos': current.pos,
                             'name': current.name, 'remark': current.remark,
                             'is_active': current.is_active})
            pos = int(body.get('pos', 0))
            if pos < 0:
                raise ValueError('pos must be non-negative')
            roi_config = body.get('roi_config') or {}
            if not roi_config.get('leftFoamROI') or not roi_config.get('rightFoamROI'):
                raise ValueError('leftFoamROI and rightFoamROI are required')
            incoming_threshold_config = body.get('threshold_config') or {}
            if not isinstance(incoming_threshold_config, dict):
                raise ValueError('threshold_config must be an object')

            recipe_id = body.get('id')
            layout_id = None if body.get('shared_recipe') else (body.get('layout_id') or body.get('foam_product_layout_id'))
            layout = None
            if layout_id not in (None, ''):
                layout = get_object_or_404(
                    FoamProductLayout.objects.select_related('rack_spec'),
                    id=int(layout_id),
                    is_active=True,
                )
                if pos >= layout.total_positions:
                    raise ValueError(f'POS {pos} 超出当前产品容量 0～{layout.total_positions - 1}')
            create_new = _as_bool(body.get('create_new'), False)
            save_mode = str(body.get('save_mode') or '').lower()
            if recipe_id:
                recipe = get_object_or_404(
                    VisionRecipe, id=recipe_id, recipe_type='FOAM_2D'
                )
            elif create_new:
                recipe = None
            else:
                recipe = get_active_foam_2d_recipe_by_pos(pos, layout_id=layout_id)
            if recipe is None:
                recipe = VisionRecipe(recipe_type='FOAM_2D', pos=pos, camera_side='both')
            # 阈值表单只编辑少数字段。合并而不是整体替换，避免清除模板路径、
            # 毫米标定和模板必选开关；标准模板位置本体保存在独立模型字段中。
            threshold_config = dict(recipe.threshold_config or {})
            threshold_config.update(incoming_threshold_config)
            recipe.name = body.get('name') or f'第{pos + 1}层泡棉检测配方'
            recipe.pos = pos
            if body.get('shared_recipe'):
                recipe.foam_product_layout = None
                recipe.product_code = ''
            if layout is not None:
                recipe.foam_product_layout = layout
                recipe.rack_type = layout.rack_spec.rack_type
                recipe.product_code = layout.product_code
            recipe.camera_side = body.get('camera_side') or recipe.camera_side or 'both'
            image_width = int(body.get('image_width') or recipe.image_width or 1280)
            image_height = int(body.get('image_height') or recipe.image_height or 720)
            # Older clients resend unchanged pixel ROIs with the newly imported
            # image dimensions. Convert using their original coordinate space.
            if recipe.pk and (image_width, image_height) != (recipe.image_width, recipe.image_height):
                from .recipe_utils import _pixel_roi_to_ratio
                roi_config = dict(roi_config)
                for key in ('leftFoamROI', 'rightFoamROI', 'layerSearchROI'):
                    raw = roi_config.get(key)
                    if (raw and raw == (recipe.roi_config or {}).get(key)
                            and raw.get('type') != 'polygon' and 'x1r' not in raw):
                        bounds = _pixel_roi_to_ratio(raw, recipe.image_width, recipe.image_height)
                        if bounds is None:
                            raise ValueError('原配方 ROI 无效，请重新框选后保存')
                        roi_config[key] = dict(zip(('x1r', 'y1r', 'x2r', 'y2r'), bounds))
            recipe.image_width = image_width
            recipe.image_height = image_height
            recipe.roi_config = roi_config
            recipe.threshold_config = threshold_config
            if 'algorithm_config' in body:
                algorithm = body['algorithm_config']
                if not isinstance(algorithm, dict):
                    raise ValueError('algorithm_config must be an object')
                allowed = {'material_type', 'foam_segmentation', 'segmentation_config',
                           'product_registration', 'fragment_merge'}
                if set(algorithm) - allowed:
                    raise ValueError('Unsupported algorithm_config field')
                recipe.algorithm_config = {**(recipe.algorithm_config or {}), **algorithm}
            if save_mode in {'draft', 'publish'}:
                recipe.is_active = save_mode == 'publish'
            else:
                recipe.is_active = _as_bool(body.get('is_active'), True)
            recipe.remark = body.get('remark') or ''
            from .recipe_utils import build_foam_inspection_config
            build_foam_inspection_config(recipe)
            recipe.save()
            if body.get('simple_save'):
                if not roi_config.get('layerSearchROI'):
                    raise ValueError('请画出左右标准框和本层搜索大框')
                uploaded = request.FILES.get('image')
                token = body.get('preview_capture_token')
                if uploaded or token:
                    image = _decode_uploaded_image(uploaded) if uploaded else _camera_image_from_preview_token(token)
                    _save_foam_standard_template(recipe, image, {'type': 'recipe_save'})
                elif not get_foam_standard_template_status(recipe)['ready']:
                    raise ValueError('请先拍照或导入合格样件图，保存时将自动建立标准模板')
            # POS identifies the inspection position, not a unique recipe slot.
            # Publishing this recipe must not unpublish other recipes at that POS.
            return JsonResponse({'success': True, 'recipe': serialize_recipe(recipe)})
    except (TypeError, ValueError, signing.BadSignature) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


def _camera_image_from_preview_token(preview_capture_token, max_age=1800):
    token_data = signing.loads(
        preview_capture_token,
        salt='foam-camera-preview',
        max_age=max_age,
    )
    candidate = Path(token_data['image_path']).resolve(strict=True)
    output_dir = Path(
        getattr(settings, 'AUTOMATIC_ORDER', {})
        .get('HIK_CAMERA', {})
        .get('OUTPUT_DIR', Path(settings.MEDIA_ROOT) / 'hik_captures')
    ).resolve(strict=True)
    candidate.relative_to(output_dir)
    if candidate.suffix.lower() not in {'.bmp', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}:
        raise ValueError('unsupported camera image format')
    image = cv2.imread(str(candidate), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('无法读取预览原图')
    return image


@require_POST
def api_foam_standard_template_teach(request, recipe_id):
    """Teach left/right standard templates atomically from one qualified image."""
    try:
        recipe = VisionRecipe.objects.filter(
            id=recipe_id,
            recipe_type='FOAM_2D',
        ).first()
        if recipe is None:
            return JsonResponse({'success': False, 'error': '未找到启用的泡棉配方'}, status=404)
        if not (recipe.roi_config or {}).get('leftFoamROI') or not (
            recipe.roi_config or {}
        ).get('rightFoamROI'):
            raise ValueError('请先保存左右两个固定搜索 ROI，再进行标准模板示教')

        uploaded = request.FILES.get('image')
        if uploaded:
            image = _decode_uploaded_image(uploaded)
        else:
            body = json.loads(request.body or '{}')
            preview_capture_token = body.get('preview_capture_token') or ''
            if preview_capture_token:
                image = _camera_image_from_preview_token(preview_capture_token)
            else:
                from apps.devices.adapters.camera import CameraAdapter

                capture_result = CameraAdapter().capture(
                    camera_code='CAM-INSPECT-FOAM-01',
                    task_type='FOAM_STANDARD_TEMPLATE',
                )
                image_path = capture_result.get('image_path', '')
                image = cv2.imread(image_path, cv2.IMREAD_COLOR) if image_path else None
                if image is None:
                    raise ValueError('相机未返回可用的标准样件图像')

        template = _save_foam_standard_template(
            recipe,
            image,
            {'type': 'qualified_image_teach'},
        )

        return JsonResponse({
            'success': True,
            'template': template,
            'recipe': serialize_recipe(recipe),
        })
    except (TypeError, ValueError, signing.BadSignature, signing.SignatureExpired) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('2D foam standard-template teaching failed')
        return JsonResponse({'success': False, 'error': f'标准模板示教失败: {exc}'}, status=500)


@require_POST
def api_foam_standard_template_from_result(request, recipe_id, result_id):
    """Promote one persisted inspection image to the recipe's standard template."""
    try:
        recipe = VisionRecipe.objects.filter(
            id=recipe_id,
            recipe_type='FOAM_2D',
        ).first()
        if recipe is None:
            return JsonResponse({'success': False, 'error': '未找到泡棉配方'}, status=404)

        inspection = (
            FoamInspectionResult.objects
            .select_related('vision_task')
            .filter(id=result_id)
            .first()
        )
        if inspection is None:
            return JsonResponse({'success': False, 'error': '未找到本次泡棉检测记录'}, status=404)

        result_recipe = (inspection.result_data or {}).get('recipe') or {}
        result_recipe_id = result_recipe.get('id')
        if result_recipe_id and int(result_recipe_id) != recipe.id:
            raise ValueError('检测结果使用的配方与目标配方不一致')
        if inspection.position_index != recipe.pos:
            raise ValueError('检测结果的 POS 与目标配方不一致')

        sides = (inspection.result_data or {}).get('sides') or {}
        missing = [
            label for side, label in (('left', '左侧'), ('right', '右侧'))
            if not (sides.get(side) or {}).get('is_present')
        ]
        if missing:
            raise ValueError('不能保存为模板：' + '、'.join(missing) + '泡棉未有效检出')

        original = inspection.vision_task.images.filter(image_type='ORIGINAL').first()
        original_path = foam_archive.image_path(inspection.id, 'original')
        content = foam_archive.image_bytes(inspection.id, 'original')
        if content is not None:
            image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        else:
            image = cv2.imread(str(original.file.path), cv2.IMREAD_COLOR) if original else None
        if image is None:
            raise ValueError('无法读取本次检测原图')

        template = _save_foam_standard_template(
            recipe,
            image,
            {
                'type': 'inspection_result',
                'result_id': inspection.id,
                'task_id': inspection.vision_task_id,
                'original_image': str(original_path),
            },
        )
        return JsonResponse({
            'success': True,
            'template': template,
            'recipe': serialize_recipe(recipe),
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('Saving foam inspection result as standard template failed')
        return JsonResponse({'success': False, 'error': f'保存标准模板失败: {exc}'}, status=500)


@require_POST
def api_foam_standard_mask_upload(request):
    """Create and activate a left/right standard mask from a qualified sample."""
    try:
        recipe_id = int(request.POST.get('recipe_id') or 0)
        side = request.POST.get('side', '').lower()
        if side not in ('left', 'right'):
            return JsonResponse({'success': False, 'error': 'side 必须是 left 或 right'}, status=400)
        recipe = VisionRecipe.objects.filter(
            id=recipe_id, recipe_type='FOAM_2D'
        ).first()
        if recipe is None:
            return JsonResponse(
                {'success': False, 'error': f'未找到 ID={recipe_id} 的泡棉检测配方'},
                status=404,
            )
        uploaded = request.FILES.get('image')
        if not uploaded:
            return JsonResponse({'success': False, 'error': '请上传图片文件'}, status=400)
        image = _decode_uploaded_image(uploaded)
        if image is None:
            return JsonResponse({'success': False, 'error': '无法解码上传的图片，请确认格式正确（JPG / PNG 等）'}, status=400)
        result = StandardMaskManager().create_from_sample(
            image,
            recipe,
            side,
            build_foam_inspection_config(recipe),
        )

        thresholds = dict(recipe.threshold_config or {})
        mask_paths = dict(
            thresholds.get('standardMaskPaths')
            or thresholds.get('standard_mask_paths')
            or {}
        )
        mask_paths[side] = result['path']
        thresholds['standardMaskPaths'] = mask_paths
        thresholds.setdefault('minIoU', 0.70)
        thresholds.setdefault('maxOffsetMm', 2.0)
        recipe.threshold_config = thresholds
        recipe.save(update_fields=['threshold_config', 'updated_at'])

        return JsonResponse({
            'success': True,
            'mask': result,
            'recipe': serialize_recipe(recipe),
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('标准模板上传失败')
        return JsonResponse({'success': False, 'error': f'服务器内部错误: {exc}'}, status=500)


def api_foam_standard_mask_status(request, recipe_id):
    """查询某配方左/右标准模板的配置状态。

    GET /api/recipes/foam-2d/<recipe_id>/standard-mask/
    返回每侧是否已配置，以及覆盖率、质心等摘要信息。
    """
    recipe = VisionRecipe.objects.filter(
        id=recipe_id, recipe_type='FOAM_2D'
    ).first()
    if recipe is None:
        return JsonResponse({'success': False, 'error': '未找到配方'}, status=404)
    status = get_foam_standard_template_status(recipe)
    if status.get('source') == 'roi':
        return JsonResponse({'success': True, 'recipe_id': recipe_id, **status})
    sides_info = {}
    for side in ('left', 'right'):
        metadata = dict((status.get('sides') or {}).get(side) or {})
        path_str = status['paths'].get(side, '')
        mask_path = Path(path_str) if path_str else None
        if mask_path is not None and not mask_path.is_absolute():
            mask_path = Path(settings.MEDIA_ROOT) / mask_path
        file_exists = bool(mask_path and mask_path.is_file())
        metadata_complete = has_complete_foam_template_side_metadata(metadata)
        usable = bool(file_exists and metadata_complete)
        metadata.update({
            'exists': usable,
            'file_exists': file_exists,
            'metadata_complete': metadata_complete,
            'path': path_str,
        })
        if path_str and not file_exists:
            metadata['error'] = '模板文件不存在'
        elif path_str and not metadata_complete:
            metadata['error'] = '旧模板缺少面积、中心或边界框数据，请重新示教'
        sides_info[side] = metadata

    ready = bool(status['ready'] and all(item['exists'] for item in sides_info.values()))
    reason = status['reason']
    if status['ready'] and not ready:
        reason = '标准模板文件不存在，需要重新示教'
    return JsonResponse({
        'success': True,
        'recipe_id': recipe_id,
        'ready': ready,
        'reason': reason,
        'version': status['version'],
        'built_at': status['built_at'],
        'sides': sides_info,
    })


@require_POST
def api_foam_standard_mask_capture(request, recipe_id):
    """拍照并生成标准模板。

    POST /api/recipes/foam-2d/<recipe_id>/standard-mask/capture/
    Body JSON: {"side": "left"|"right"}

    调用相机拍一张图，然后调用 StandardMaskManager 生成标准掩膜并保存到配方。
    """
    try:
        body = json.loads(request.body or '{}')
        side = body.get('side', '').lower()
        if side not in ('left', 'right'):
            return JsonResponse({'success': False, 'error': 'side 必须是 left 或 right'}, status=400)

        recipe = VisionRecipe.objects.filter(
            id=recipe_id, recipe_type='FOAM_2D'
        ).first()
        if recipe is None:
            return JsonResponse({'success': False, 'error': '未找到配方'}, status=404)

        # 触发相机拍照
        from apps.devices.adapters.camera import CameraAdapter
        adapter = CameraAdapter()
        capture_result = adapter.capture(
            camera_code='CAM-INSPECT-FOAM-01',
            task_type='FOAM_MASK_SAMPLE',
        )
        image_path = capture_result.get('image_path', '')
        if not image_path:
            return JsonResponse({'success': False, 'error': '相机返回的图像路径为空'}, status=500)

        # 读取图像
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            return JsonResponse({'success': False, 'error': f'无法读取拍摄图像: {image_path}'}, status=500)

        # 生成标准模板
        result = StandardMaskManager().create_from_sample(
            image,
            recipe,
            side,
            build_foam_inspection_config(recipe),
        )

        # 保存路径到配方
        thresholds = dict(recipe.threshold_config or {})
        mask_paths = dict(
            thresholds.get('standardMaskPaths')
            or thresholds.get('standard_mask_paths')
            or {}
        )
        mask_paths[side] = result['path']
        thresholds['standardMaskPaths'] = mask_paths
        thresholds.setdefault('minIoU', 0.70)
        thresholds.setdefault('maxOffsetMm', 2.0)
        recipe.threshold_config = thresholds
        recipe.save(update_fields=['threshold_config', 'updated_at'])

        return JsonResponse({
            'success': True,
            'mask': result,
            'recipe': serialize_recipe(recipe),
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('拍照生成标准模板失败')
        return JsonResponse({'success': False, 'error': f'拍照失败: {exc}'}, status=500)


@require_POST
def api_foam_standard_mask_delete(request, recipe_id, side):
    """删除某侧标准模板。

    POST /api/recipes/foam-2d/<recipe_id>/standard-mask/<side>/delete/
    从配方的 threshold_config 中移除该侧路径，并删除 PNG 文件。
    """
    try:
        if side not in ('left', 'right'):
            return JsonResponse({'success': False, 'error': 'side 必须是 left 或 right'}, status=400)

        recipe = VisionRecipe.objects.filter(
            id=recipe_id, recipe_type='FOAM_2D'
        ).first()
        if recipe is None:
            return JsonResponse({'success': False, 'error': '未找到配方'}, status=404)

        thresholds = dict(recipe.threshold_config or {})
        mask_paths = dict(
            thresholds.get('standardMaskPaths')
            or thresholds.get('standard_mask_paths')
            or {}
        )

        path_str = mask_paths.pop(side, '')
        thresholds['standardMaskPaths'] = mask_paths
        recipe.threshold_config = thresholds
        recipe.save(update_fields=['threshold_config', 'updated_at'])

        # 尝试删除 PNG 文件
        deleted_file = False
        if path_str:
            mask_path = Path(path_str)
            if not mask_path.is_absolute():
                mask_path = Path(settings.MEDIA_ROOT) / mask_path
            if mask_path.is_file():
                mask_path.unlink(missing_ok=True)
                deleted_file = True

        return JsonResponse({
            'success': True,
            'deleted_file': deleted_file,
            'recipe': serialize_recipe(recipe),
        })
    except Exception as exc:
        logger.exception('删除标准模板失败')
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@require_POST
def api_foam_recipe_delete(request, recipe_id):
    """删除指定的泡棉检测配方"""
    try:
        recipe = get_object_or_404(VisionRecipe, id=recipe_id, recipe_type='FOAM_2D')
        recipe_name = recipe.name
        recipe.delete()
        return JsonResponse({
            'success': True,
            'message': f'配方 "{recipe_name}" 已删除'
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_POST
@transaction.atomic
def api_foam_recipe_create(request):
    """创建新的泡棉检测配方"""
    try:
        body = json.loads(request.body or '{}')
        pos = int(body.get('pos', 0))
        if pos < 0:
            raise ValueError('pos must be non-negative')

        # A recipe is selected once and reused for the entire rack.
        layout = None
        source_recipe_id = body.get('source_recipe_id')
        source = None
        if source_recipe_id not in (None, ''):
            source = get_object_or_404(
                VisionRecipe,
                pk=int(source_recipe_id),
                recipe_type='FOAM_2D',
            )

        # 默认 ROI 配置；复制模式完整继承算法、阈值和模板数据。
        roi_config = deepcopy(body.get('roi_config') or (source.roi_config if source else None) or {
            'leftFoamROI': {'x': 220, 'y': 140, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 140, 'width': 110, 'height': 70}
        })
        
        # 默认阈值配置（与算法默认值保持一致）
        threshold_config = deepcopy(body.get('threshold_config') or (source.threshold_config if source else None) or {
            'coverage_threshold': 0.75,
            'score_threshold': 0.8,      # 80% 综合得分
            'max_offset_mm': 2.0
        })
        
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name=body.get('name') or '整架泡棉检测配方',
            foam_product_layout=layout,
            rack_type=body.get('rack_type') or '',
            product_code='',
            pos=pos,
            camera_side=body.get('camera_side') or (source.camera_side if source else 'both'),
            image_width=int(body.get('image_width') or (source.image_width if source else 1280)),
            image_height=int(body.get('image_height') or (source.image_height if source else 720)),
            roi_config=roi_config,
            threshold_config=threshold_config,
            algorithm_config=deepcopy(source.algorithm_config) if source else {},
            standard_template_config=deepcopy(source.standard_template_config) if source else {},
            standard_template_built_at=source.standard_template_built_at if source else None,
            standard_template_version=source.standard_template_version if source else '',
            is_active=False,
            remark=body.get('remark') or (source.remark if source else '') or '',
        )
        
        if source:
            _copy_foam_template_files(recipe)
        return JsonResponse({'success': True, 'recipe': serialize_recipe(recipe)})
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


def _copy_foam_template_files(recipe):
    """Copies own their masks: deleting a source mask must not break a copy."""
    media = Path(settings.MEDIA_ROOT).resolve()
    destination = media / 'vision' / 'foam_templates' / f'copy_{recipe.pk}_{uuid.uuid4().hex}'
    copied = {}

    def copy_path(value):
        if not value or value in copied:
            return copied.get(value, value)
        source = Path(value)
        if not source.is_absolute():
            source = media / source
        if not source.is_file():
            return value  # Preserve the existing missing-template status.
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f'{len(copied)}_{source.name}'
        shutil.copy2(source, target)
        copied[value] = target.relative_to(media).as_posix()
        return copied[value]

    template = recipe.standard_template_config or {}
    if template.get('source_image_path'):
        template['source_image_path'] = copy_path(template['source_image_path'])
    for side in (template.get('sides') or {}).values():
        if side.get('path'):
            side['path'] = copy_path(side['path'])
    thresholds = recipe.threshold_config or {}
    for key in ('standardMaskPaths', 'standard_mask_paths'):
        if isinstance(thresholds.get(key), dict):
            thresholds[key] = {side: copy_path(path) for side, path in thresholds[key].items()}
    recipe.standard_template_config = template
    recipe.threshold_config = thresholds
    recipe.save(update_fields=['standard_template_config', 'threshold_config'])


def _normalize_roi_ratio(values):
    if isinstance(values, dict) and values.get('type') == 'polygon':
        points = values.get('points')
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError('Polygon ROI must contain at least 3 points')
        return values
        
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('ROI must contain four ratio values')
    ratios = [float(value) for value in values]
    if any(value < 0 or value > 1 for value in ratios):
        raise ValueError('ROI ratio values must be between 0 and 1')
    if ratios[0] >= ratios[2] or ratios[1] >= ratios[3]:
        raise ValueError('ROI x1/y1 must be less than x2/y2')
    return ratios


@require_http_methods(["GET"])
def api_foam_calibration(request):
    device_code = request.GET.get('device_code', 'CAM-INSPECT-FOAM-01')
    profile = (
        CalibrationProfile.objects
        .filter(device_code=device_code, version='foam-roi-v1', is_active=True)
        .order_by('-updated_at')
        .first()
    )
    return JsonResponse({
        'success': True,
        'profile': profile.transform_data if profile else {},
        'profile_name': profile.name if profile else '',
    })


@require_POST
def api_foam_calibration_save(request):
    try:
        body = json.loads(request.body or '{}')
        device_code = body.get('device_code') or 'CAM-INSPECT-FOAM-01'
        position_index = int(body.get('position_index', 0))
        if position_index < 0:
            raise ValueError('position_index must be non-negative')
        left = _normalize_roi_ratio(body.get('left'))
        right = _normalize_roi_ratio(body.get('right'))
        thresholds = body.get('thresholds') or {}
        if not isinstance(thresholds, dict):
            raise ValueError('thresholds must be an object')

        CalibrationProfile.objects.filter(
            device_code=device_code,
            version='foam-roi-v1',
            is_active=True,
        ).update(is_active=False)

        latest = (
            CalibrationProfile.objects
            .filter(device_code=device_code, version='foam-roi-v1')
            .order_by('-updated_at')
            .first()
        )
        transform_data = dict(latest.transform_data) if latest else {}
        foam_rois = dict(transform_data.get('foam_rois') or {})
        foam_rois[str(position_index)] = {'left': left, 'right': right}
        transform_data['foam_rois'] = foam_rois
        merged_thresholds = dict(transform_data.get('thresholds') or {})
        merged_thresholds.update(thresholds)
        transform_data['thresholds'] = merged_thresholds

        profile = CalibrationProfile.objects.create(
            name=f'{device_code} foam roi',
            device_code=device_code,
            version='foam-roi-v1',
            is_active=True,
            transform_data=transform_data,
        )
        return JsonResponse({
            'success': True,
            'profile_id': profile.id,
            'profile': profile.transform_data,
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_POST
def api_camera_preview(request):
    """获取相机实时预览画面（不保存到数据库）"""
    try:
        from apps.devices.adapters.camera import CameraAdapter
        
        camera_code = request.POST.get('camera_code') or 'CAM-INSPECT-FOAM-01'
        allowed_camera_codes = {'CAM-INSPECT-FOAM-01', 'CAM-INSPECT-RACK-01'}
        if camera_code not in allowed_camera_codes:
            return JsonResponse({'success': False, 'error': '不支持的相机编号'}, status=400)
        task_type = (
            'RACK_CAMERA_PREVIEW'
            if camera_code == 'CAM-INSPECT-RACK-01'
            else 'PREVIEW'
        )

        adapter = CameraAdapter()
        result = adapter.capture(
            camera_code=camera_code,
            task_type=task_type,
        )
        
        image_path = result.get('image_path')
        if not image_path:
            return JsonResponse({
                'success': False,
                'error': '相机返回的图像路径为空'
            })
        
        # 转换为相对于MEDIA_ROOT的路径
        raw_image_path = str(Path(image_path).resolve())
        capture_token = signing.dumps(
            {'image_path': raw_image_path},
            salt='foam-camera-preview',
            compress=True,
        )
        image_path_obj = Path(image_path)
        media_root = Path(settings.MEDIA_ROOT)
        source_image_width = 0
        source_image_height = 0

        # The industrial camera produces a 4096x2460 BMP (~30 MB). Sending that
        # file for every preview frame makes the browser appear frozen and turns
        # polling into a disk/network bottleneck. Keep the original capture for
        # inspection, but publish a bounded JPEG for the live workbench preview.
        try:
            preview_image = cv2.imread(str(image_path_obj), cv2.IMREAD_COLOR)
            if preview_image is None:
                raise RuntimeError(f'OpenCV could not decode {image_path_obj}')
            height, width = preview_image.shape[:2]
            source_image_width = width
            source_image_height = height
            max_width = 1280
            if width > max_width:
                scale = max_width / width
                preview_image = cv2.resize(
                    preview_image,
                    (max_width, max(1, int(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            temp_dir = media_root / 'temp_previews'
            temp_dir.mkdir(parents=True, exist_ok=True)
            preview_name = (
                'rack_camera_preview.jpg'
                if camera_code == 'CAM-INSPECT-RACK-01'
                else 'camera_live_preview.jpg'
            )
            preview_path = temp_dir / preview_name
            with tempfile.NamedTemporaryFile(dir=temp_dir, suffix='.jpg', delete=False) as tmp:
                temp_preview_path = Path(tmp.name)
            try:
                saved = cv2.imwrite(
                    str(temp_preview_path),
                    preview_image,
                    [cv2.IMWRITE_JPEG_QUALITY, 82],
                )
                if not saved:
                    raise RuntimeError('OpenCV failed to encode the preview JPEG')
                temp_preview_path.replace(preview_path)
            finally:
                temp_preview_path.unlink(missing_ok=True)
            image_path_obj = preview_path
        except Exception as preview_exc:
            logger.warning('Unable to optimize camera preview: %s', preview_exc)
        
        try:
            rel_path = image_path_obj.relative_to(media_root)
            image_url = f"{settings.MEDIA_URL}{rel_path.as_posix()}"
        except ValueError:
            # 如果不在MEDIA_ROOT下，复制到临时位置
            temp_dir = media_root / 'temp_previews'
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            import shutil
            dest_path = temp_dir / image_path_obj.name
            shutil.copy2(image_path_obj, dest_path)
            
            rel_path = dest_path.relative_to(media_root)
            image_url = f"{settings.MEDIA_URL}{rel_path.as_posix()}"
        
        return JsonResponse({
            'success': True,
            'image_url': image_url,
            'capture_token': capture_token,
            'image_width': source_image_width,
            'image_height': source_image_height,
            'timestamp': result.get('timestamp', ''),
        })
        
    except RuntimeError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'预览失败: {str(e)}'
        })


@require_POST
def api_foam_capture_inspect(request):
    """拍照并进行泡棉检测"""
    request_started = time.perf_counter()
    try:
        body = json.loads(request.body)
        position_index = int(body.get('position_index', 0))
        recipe_id = body.get('recipe_id') or None
        use_recipe = _as_bool(body.get('use_recipe'), True)
        # A production inspection always acquires a new frame after the click.
        # Preview tokens remain available for recipe teaching, never inspection.
        vision_service = VisionService()
        foam_result = vision_service.inspect_foam(
            product=None,
            rack=None,
            position_index=position_index,
            simulated_pass=True,
            use_camera=True,
            recipe_id=recipe_id,
            use_recipe=use_recipe,
        )
        
        payload = _result_payload(foam_result)
        timings = payload.setdefault('timings_ms', {})
        timings['api_total'] = round((time.perf_counter() - request_started) * 1000, 1)
        logger.info('Foam capture API timing timings_ms=%s', timings)
        return JsonResponse({
            'success': True,
            'result': payload,
        })
        
    except RuntimeError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'检测失败: {str(e)}'
        })


@require_POST
def api_foam_upload_inspect(request):
    """上传图片并进行泡棉检测"""
    request_started = time.perf_counter()
    timings = {}
    try:
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({
                'success': False,
                'error': '未上传图片文件'
            })
        
        position_index = int(request.POST.get('position_index', 0))
        recipe_id = request.POST.get('recipe_id') or None
        use_recipe = _as_bool(request.POST.get('use_recipe'), True)
        
        phase_started = time.perf_counter()
        image = _decode_uploaded_image(uploaded_file)
        timings['image_decode'] = round((time.perf_counter() - phase_started) * 1000, 1)
        
        # 使用真实图片进行检测
        from .algorithms.foam_inspector import FoamInspector
        
        inspector = FoamInspector(simulate=False)
        recipe = None
        recipe_config = {}
        if use_recipe:
            if recipe_id:
                recipe = (
                    VisionRecipe.objects
                    .filter(id=recipe_id, recipe_type='FOAM_2D')
                    .first()
                )
            else:
                recipe = get_active_foam_2d_recipe_by_pos(position_index)
            if recipe:
                recipe_config = build_foam_inspection_config(recipe)
        inspection_config = {
            'score_threshold': 0.8,
            'coverage_threshold': 0.35,  # 根据实际场景调整为35%
            'max_offset_mm': 2.0,
        }
        inspection_config.update(recipe_config)
        # 使用真实图像检测，simulated_pass参数不影响结果
        phase_started = time.perf_counter()
        result = inspector.inspect(
            position_index=position_index,
            inspection_config=inspection_config,
            image=image,
            camera_image_path=f'upload:{Path(uploaded_file.name).name[:128]}',
            simulated_pass=True,  # 当image不为None时此参数被忽略
        )
        if recipe:
            result.setdefault('result_data', {})['recipe'] = serialize_recipe(recipe)
        timings['algorithm_and_archive'] = round((time.perf_counter() - phase_started) * 1000, 1)
        result.setdefault('result_data', {})['timings_ms'] = timings
        
        # 创建视觉任务记录
        task = VisionTask.objects.create(
            task_type='FOAM_INSPECTION',
            status='SUCCESS' if result['is_passed'] else 'FAILED',
        )
        task.started_at = task.created_at
        task.finished_at = task.created_at
        task.save()
        
        # 保存检测结果
        foam_result = FoamInspectionResult.objects.create(
            vision_task=task,
            position_index=result['position_index'],
            is_present=result['is_present'],
            is_aligned=result['is_aligned'],
            has_lifted_edge=result.get('has_lifted_edge', False),
            score=result.get('score', 0.0),
            is_passed=result['is_passed'],
            offset_x_px=result['offset_x_px'],
            offset_y_px=result['offset_y_px'],
            offset_x_mm=result.get('offset_x_mm', 0),
            offset_y_mm=result.get('offset_y_mm', 0),
            coverage_ratio=result['coverage_ratio'],
            defect_type=result['defect_type'],
            result_data=result.get('result_data', {}),
        )
        
        timings['total'] = round((time.perf_counter() - request_started) * 1000, 1)
        foam_result.save(update_fields=['result_data'])
        foam_archive.archive(foam_result, result)

        return JsonResponse({'success': True, 'result': _result_payload(foam_result)})
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': f'参数错误: {str(e)}'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'检测失败: {str(e)}'
        }, status=500)


def api_foam_inspection_records(request):
    """获取2D泡棉检测历史记录（含原图URL），供「从记录导入」功能调用"""
    try:
        limit = min(int(request.GET.get('limit', 50)), 200)
        records = (
            FoamInspectionResult.objects
            .select_related('vision_task')
            .prefetch_related('vision_task__images')
            .order_by('-created_at')[:limit]
        )
        data = []
        for r in records:
            task = r.vision_task
            original_img = task.images.filter(image_type='ORIGINAL').first()
            result_img = task.images.filter(image_type='RESULT').first()
            saved_original = foam_archive.root() / f'{r.id}_original.png'
            if not original_img and not saved_original.is_file():
                continue  # 数据记录没有永久图片，不能用于导入
            data.append({
                'id': r.id,
                'task_id': task.id,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'position_index': r.position_index,
                'is_passed': r.is_passed,
                'is_present': r.is_present,
                'score': float(r.score),
                'coverage_ratio': float(r.coverage_ratio),
                'original_image_url': original_img.file.url if original_img else f'/vision/api/foam/records/{r.id}/image/original/',
                'result_image_url': result_img.file.url if result_img else '',
            })
        return JsonResponse({'success': True, 'records': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ------------------------------------------------------------------
# 料架定位工作台
# ------------------------------------------------------------------

def rack_locator_panel(request):
    """3D料架定位工作台：按整料架配方选择并加载示教数据。"""
    latest = (
        RackLocationResult.objects
        .select_related('recipe', 'vision_task')
        .order_by('-created_at')
        .first()
    )
    recipes = RackLocationRecipe.objects.filter(enabled=True).order_by('rack_type', 'recipe_name')
    return render(request, 'vision/rack_locator_panel.html', {
        'latest': latest,
        'recipes': recipes,
    })


@require_POST
def api_rack_locate(request):
    """手动触发双料架定位（单次拍摄同时覆盖左右两个料架）。"""
    try:
        rack, recipe = _get_depth_roi_debug_context()
        left_result, right_result = VisionService().locate_both_racks(
            product=None,
            rack=rack,
            recipe=recipe,
        )

        def _side_payload(res, task):
            result_img = task.images.filter(image_type='RESULT').first()
            return {
                'is_success':             res.is_success,
                'offset_x':              float(res.offset_x),
                'offset_y':              float(res.offset_y),
                'offset_z':              float(res.offset_z),
                'confidence':            float(res.result_data.get('confidence', 0)),
                'recipe_matched':        res.is_recipe_matched,
                'measured_layer_height': float(res.measured_layer_height),
                'measured_layer_spacing':float(res.measured_layer_spacing),
                'recipe_layer_height':   float(res.recipe_layer_height),
                'recipe_layer_spacing':  float(res.recipe_layer_spacing),
                'layer_heights':         res.result_data.get('layer_heights', []),
                'layer_spacings':        res.result_data.get('layer_spacings', []),
                'result_image_url':      result_img.file.url if result_img else '',
            }

        left_task  = left_result.vision_task
        right_task = right_result.vision_task

        return JsonResponse({
            'success': True,
            'LEFT':  _side_payload(left_result,  left_task),
            'RIGHT': _side_payload(right_result, right_task),
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)})


@require_http_methods(['GET'])
def api_rack_results(request):
    """返回最近 20 条料架定位结果（左右架分开记录）。"""
    try:
        qs = (
            RackLocationResult.objects
            .select_related('vision_task')
            .order_by('-created_at')[:20]
        )
        results = []
        for r in qs:
            results.append({
                'id':                    r.id,
                'created_at':            r.created_at.strftime('%m-%d %H:%M:%S') if r.created_at else '',
                'side':                  r.side,
                'offset_x':             float(r.offset_x),
                'offset_y':             float(r.offset_y),
                'offset_z':             float(r.offset_z),
                'confidence':           float(r.result_data.get('confidence', 0)),
                'measured_layer_height': float(r.measured_layer_height),
                'measured_layer_spacing':float(r.measured_layer_spacing),
                'is_recipe_matched':    r.is_recipe_matched,
                'is_success':           r.is_success,
            })
        return JsonResponse({'success': True, 'results': results})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)})


@require_POST
@csrf_exempt
def api_rack_locator_offline_test(request):
    """
    3D料架定位离线测试：导入数据并保存到指定路径
    保存深度数据(.npy)和2D图片(.png)到 C:\\Users\\11410\\Desktop\\pic
    """
    import os
    import numpy as np
    from PIL import Image
    from datetime import datetime
    
    try:
        data = json.loads(request.body)
        
        # 获取上传的点云数据
        pointcloud_data = data.get('pointcloud')
        if not pointcloud_data:
            return JsonResponse({'success': False, 'error': '缺少点云数据'}, status=400)
        
        # 获取2D图片数据（base64或URL）
        image_data = data.get('image')
        image_width = data.get('image_width', 640)
        image_height = data.get('image_height', 480)
        
        # 创建保存目录
        save_dir = r'C:\Users\11410\Desktop\pic'
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成时间戳文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        
        # 1. 保存深度数据为.npy文件
        pointcloud = np.array(pointcloud_data, dtype=np.float32)
        depth_file = os.path.join(save_dir, f'depth_{timestamp}.npy')
        np.save(depth_file, pointcloud)
        
        # 2. 保存2D图片
        image_file = os.path.join(save_dir, f'image_{timestamp}.png')
        
        if image_data:
            # 如果提供了图片数据
            if image_data.startswith('data:image'):
                # Base64格式
                import base64
                header, encoded = image_data.split(',', 1)
                image_bytes = base64.b64decode(encoded)
                with open(image_file, 'wb') as f:
                    f.write(image_bytes)
            elif os.path.exists(image_data):
                # 文件路径
                import shutil
                shutil.copy(image_data, image_file)
        else:
            # 如果没有提供图片，从深度数据生成伪彩色图
            # 将点云转换为深度图
            if pointcloud.shape[1] >= 3:
                z_values = pointcloud[:, 2]
                # 归一化深度值
                z_min, z_max = z_values.min(), z_values.max()
                if z_max > z_min:
                    z_normalized = ((z_values - z_min) / (z_max - z_min) * 255).astype(np.uint8)
                else:
                    z_normalized = np.zeros(len(z_values), dtype=np.uint8)
                
                # 重塑为图像（假设点云是规则网格）
                # 如果没有宽高信息，尝试推断
                total_points = len(z_values)
                if image_width * image_height == total_points:
                    depth_image = z_normalized.reshape(image_height, image_width)
                else:
                    # 使用默认尺寸
                    side = int(np.sqrt(total_points))
                    if side * side == total_points:
                        depth_image = z_normalized.reshape(side, side)
                    else:
                        # 无法重塑，创建一个简单的可视化
                        depth_image = np.zeros((image_height, image_width), dtype=np.uint8)
                
                # 应用简单的伪彩色映射（蓝->绿->红）
                # 创建RGB图像
                colored = np.zeros((depth_image.shape[0], depth_image.shape[1], 3), dtype=np.uint8)
                
                # 蓝色通道：深度值越小越蓝
                colored[:, :, 2] = 255 - depth_image
                # 绿色通道：中间值为绿
                colored[:, :, 1] = 255 - np.abs(depth_image - 128) * 2
                # 红色通道：深度值越大越红
                colored[:, :, 0] = depth_image
                
                img = Image.fromarray(colored)
                img.save(image_file)
        
        logger.info(f'离线测试数据已保存: {depth_file}, {image_file}')
        
        return JsonResponse({
            'success': True,
            'message': '数据保存成功',
            'files': {
                'depth': depth_file,
                'image': image_file
            },
            'pointcloud_shape': pointcloud.shape,
            'timestamp': timestamp
        })
        
    except Exception as e:
        logger.exception("离线测试保存失败")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@csrf_exempt
def api_rack_locator_load_latest(request):
    """
    加载最新的离线测试数据（从保存目录读取）
    用于"导入数据"功能 - 加载上一次的数据进行测试
    """
    import os
    import glob
    import numpy as np
    from django.conf import settings
    import shutil
    
    try:
        # 从保存目录读取最新的文件
        save_dir = r'C:\Users\11410\Desktop\pic'
        
        if not os.path.exists(save_dir):
            return JsonResponse({
                'success': False,
                'error': f'保存目录不存在: {save_dir}'
            }, status=404)
        
        # 查找最新的.npy文件
        depth_files = glob.glob(os.path.join(save_dir, 'depth_*.npy'))
        
        if not depth_files:
            return JsonResponse({
                'success': False,
                'error': '未找到保存的点云数据文件'
            }, status=404)
        
        # 按修改时间排序，获取最新的
        latest_depth_file = max(depth_files, key=os.path.getmtime)
        
        # 尝试找对应的图片文件
        timestamp = os.path.basename(latest_depth_file).replace('depth_', '').replace('.npy', '')
        image_file = os.path.join(save_dir, f'image_{timestamp}.png')
        
        logger.info(f'加载最新数据: {latest_depth_file}')
        
        # 加载点云数据
        pointcloud = np.load(latest_depth_file)
        
        # 将点云保存到工作台的临时目录（模拟采集过程）
        # 使用与采集点云相同的存储机制
        workbench_dir = os.path.join(settings.MEDIA_ROOT, 'vision/rack_workbench')
        os.makedirs(workbench_dir, exist_ok=True)
        
        # 生成临时token
        from datetime import datetime
        temp_token_name = f'imported_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]}.npy'
        temp_token_path = os.path.join(workbench_dir, temp_token_name)
        
        # 保存到临时位置
        np.save(temp_token_path, pointcloud)
        
        # 生成token（相对路径）
        token = os.path.join('vision/rack_workbench', temp_token_name)
        
        # 生成预览图（伪彩色深度图）
        from apps.vision.algorithms import image_io
        preview = image_io.pointcloud_to_preview(pointcloud)
        preview_rel, _, _ = image_io.save_image(
            preview, 'imported_preview', rel_dir='vision/rack_workbench'
        )
        
        logger.info(f'已加载点云: {pointcloud.shape}, token={token}')
        
        return JsonResponse({
            'success': True,
            'message': '成功加载上一次的数据',
            'pointcloud_token': token,
            'pointcloud_preview_url': settings.MEDIA_URL + preview_rel,
            'preview_image_url': settings.MEDIA_URL + preview_rel,
            'image_width': int(preview.shape[1]),
            'image_height': int(preview.shape[0]),
            'source': f'imported from {os.path.basename(latest_depth_file)}',
            'source_file': latest_depth_file,
            'pointcloud_shape': list(pointcloud.shape),
            'file_timestamp': timestamp,
        })
        
    except Exception as e:
        logger.exception("加载最新数据失败")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
@csrf_exempt
def api_rack_locator_import_npy(request):
    """
    解析上传的.npy文件并返回点云数据
    """
    import numpy as np
    import tempfile
    
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': '未上传文件'}, status=400)
        
        uploaded_file = request.FILES['file']
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.npy') as tmp_file:
            for chunk in uploaded_file.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name
        
        try:
            # 加载.npy文件
            pointcloud = np.load(tmp_path)
            
            # 确保是2D数组且至少有3列
            if pointcloud.ndim != 2 or pointcloud.shape[1] < 3:
                return JsonResponse({
                    'success': False,
                    'error': f'点云格式错误：期望 (N, 3)，实际 {pointcloud.shape}'
                }, status=400)
            
            # 转换为列表格式
            pointcloud_list = pointcloud[:, :3].tolist()
            
            return JsonResponse({
                'success': True,
                'pointcloud': pointcloud_list,
                'shape': pointcloud.shape,
                'point_count': len(pointcloud_list)
            })
            
        finally:
            # 清理临时文件
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
    except Exception as e:
        logger.exception("解析.npy文件失败")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ------------------------------------------------------------------
# 3D 深度相机料架定位：按配方位置/层号单次拍照补偿
# ------------------------------------------------------------------

def _request_data(request):
    if request.content_type and 'application/json' in request.content_type:
        return json.loads(request.body or '{}')
    return request.POST


def _api3d_success(data=None, status=200):
    data = data or {}
    return JsonResponse({'success': True, 'data': data, 'error': '', **data}, status=status)


def _api3d_error(message, status=400):
    return JsonResponse({'success': False, 'data': {}, 'error': str(message)}, status=status)


def _as_int(value, default=1):
    if value in (None, ''):
        return default
    return int(value)


def _as_float(value, default=0):
    if value in (None, ''):
        return default
    return float(value)


def _json_config(value, default=None):
    if value in (None, ''):
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _merge_rack_roi_config(existing, incoming, *, stamp_measurement=False):
    """Only current cloud configuration is editable."""
    from .rack_cloud_roi import cloud_config
    merged = cloud_config(existing)
    incoming = dict(incoming or {})
    unsupported = {'local_template_rois', 'spatial_rois', 'layer_spacing_line', 'target_roi'} & incoming.keys()
    if unsupported:
        raise ValueError('旧定位 ROI 已移除，请在点云模板工作台框选并保存')
    merged.update(incoming)
    return cloud_config(merged)


def _serialize_rack_location_recipe(recipe):
    from .rack_cloud_roi import cloud_config
    return {
        'id': recipe.id,
        'recipe_name': recipe.recipe_name,
        'rack_type': recipe.rack_type,
        'rack_side': recipe.rack_side,
        'position_no': recipe.position_no,
        'layer_count': recipe.layer_count,
        'layer_no': recipe.layer_no,
        'camera_device_id': recipe.camera_device_id,
        'camera_config_id': recipe.camera_config_id,
        'capture_pose_name': recipe.capture_pose_name,
        'standard_x': float(recipe.standard_x),
        'standard_y': float(recipe.standard_y),
        'standard_z': float(recipe.standard_z),
        'standard_rz': float(recipe.standard_rz),
        'roi_config': cloud_config(recipe.roi_config),
        'reference_feature_config': recipe.reference_feature_config,
        'hand_eye_config': recipe.hand_eye_config,
        'max_offset_x': float(recipe.max_offset_x),
        'max_offset_y': float(recipe.max_offset_y),
        'max_offset_z': float(recipe.max_offset_z),
        'max_offset_rz': float(recipe.max_offset_rz),
        'confidence_threshold': float(recipe.confidence_threshold),
        'enabled': recipe.enabled,
    }


def _serialize_3d_recipe(recipe):
    payload = _serialize_rack_location_recipe(recipe)
    layer_index = int(recipe.layer_no or 0)
    locate_type = 'GLOBAL' if layer_index == 0 else 'LAYER'
    try:
        semantics = locate_semantics(
            locate_type=locate_type,
            layer_index=layer_index,
        )
    except ValueError as exc:
        # 历史数据可能包含当前定位链路不支持的层号。列表和详情接口仍需
        # 返回这类记录，方便用户修正或删除，不能让一条异常记录拖垮整页。
        semantics = {
            'locate_type': locate_type,
            'layer_index': layer_index,
        }
        payload['semantic_validation_error'] = str(exc)
    payload.update({
        'locate_type': semantics['locate_type'],
        'layer_index': semantics['layer_index'],
        'total_layers': int(recipe.layer_count or 3),
        'photo_pose_name': recipe.capture_pose_name,
        'robot_pose_code': (recipe.reference_feature_config or {}).get('robot_pose_code', ''),
    })
    return payload


def _serialize_3d_roi(roi):
    payload = roi3d_to_dict(roi)
    semantics = locate_semantics(mode=roi.mode, layer_index=roi.layer_no or 0)
    payload.update({
        'locate_type': semantics['locate_type'],
        'layer_index': semantics['layer_index'],
    })
    return payload


@require_http_methods(['GET'])
def api_vision_3d_recipe_current(request):
    try:
        recipe = Rack3DLocator().get_current_recipe(
            locate_type=request.GET.get('locate_type') or 'LAYER',
            layer_index=request.GET.get('layer_index') or request.GET.get('layer_no') or 1,
            rack_type=request.GET.get('rack_type') or None,
        )
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe) if recipe else None})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


def rack_location_workbench(request):
    return redirect('vision:rack_locator_panel')


def rack_location_recipes(request):
    """兼容旧入口，统一跳转到视觉配方模块的 3D 标签页。"""
    return redirect(f'{reverse("vision:recipe_management")}?tab=rack3d')


def _rack_location_recipe_form_context(recipe=None, prefill: dict | None = None):
    sample = RackLocationService().capture_standard_image(recipe_id=getattr(recipe, 'id', None))
    devices = Device.objects.filter(enabled=True).order_by('code')
    
    # 默认3D ROI坐标（机器人基坐标系，单位：mm）
    # 例如第2层的参考范围
    default_roi_3d = {
        'x_min': 900,
        'x_max': 1300,
        'y_min': 400,
        'y_max': 850,
        'z_min': 700,
        'z_max': 880,
    }
    
    # 尝试从默认ROI计算标准坐标的中心点
    try:
        seed_x = (default_roi_3d['x_min'] + default_roi_3d['x_max']) / 2
        seed_y = (default_roi_3d['y_min'] + default_roi_3d['y_max']) / 2
        seed_z = (default_roi_3d['z_min'] + default_roi_3d['z_max']) / 2
    except Exception:  # noqa: BLE001
        seed_x, seed_y, seed_z = 0.0, 0.0, 1090.0
    
    defaults = {
        'recipe_name': '3D-POS-1-L1',
        'rack_type': '',
        'rack_side': 'LEFT',
        'position_no': 1,
        'layer_count': 3,
        'layer_no': 1,
        'capture_pose_name': 'POSE-POS-1-L1',
        'standard_x': round(seed_x, 3),
        'standard_y': round(seed_y, 3),
        'standard_z': round(seed_z, 3),
        'standard_rz': 0,
        'roi_config': {
            'coordinate_system': 'robot',
            **default_roi_3d,
        },
        'reference_feature_config': {},
        'hand_eye_config': {
            'matrix': 'identity',
            'skip_validation': True,
            'note': '开发测试模式 - 使用单位矩阵（相机坐标系=机器人坐标系）',
        },
        'enabled': True,
    }
    
    # 从recipe对象提取ROI 3D坐标
    roi_defaults = default_roi_3d.copy()
    if recipe:
        for key in ['recipe_name', 'rack_type', 'rack_side', 'position_no', 'layer_count', 
                    'layer_no', 'capture_pose_name', 'standard_x', 'standard_y', 'standard_z', 
                    'standard_rz', 'reference_feature_config', 'hand_eye_config', 'enabled']:
            defaults[key] = getattr(recipe, key)
        
        # 从roi_config中提取3D坐标
        if recipe.roi_config:
            roi_defaults = {
                'x_min': recipe.roi_config.get('x_min', default_roi_3d['x_min']),
                'x_max': recipe.roi_config.get('x_max', default_roi_3d['x_max']),
                'y_min': recipe.roi_config.get('y_min', default_roi_3d['y_min']),
                'y_max': recipe.roi_config.get('y_max', default_roi_3d['y_max']),
                'z_min': recipe.roi_config.get('z_min', default_roi_3d['z_min']),
                'z_max': recipe.roi_config.get('z_max', default_roi_3d['z_max']),
            }
    
    # 支持从 GET 参数预填（配方管理页 Modal 弹窗跳转时使用）
    if prefill:
        for k, v in prefill.items():
            if k in defaults and v not in (None, ''):
                try:
                    if isinstance(defaults[k], bool):
                        defaults[k] = v in (True, 'true', '1', 'True')
                    elif isinstance(defaults[k], int):
                        defaults[k] = int(v)
                    elif isinstance(defaults[k], float):
                        defaults[k] = float(v)
                    else:
                        defaults[k] = v
                except (ValueError, TypeError):
                    pass
    
    return {
        'recipe': recipe,
        'recipe_defaults': defaults,
        'roi_defaults': roi_defaults,  # 3D ROI坐标
        'roi_config_json': json.dumps(defaults['roi_config'], ensure_ascii=False),
        'reference_feature_config_json': json.dumps(defaults['reference_feature_config'], ensure_ascii=False),
        'hand_eye_config_json': json.dumps(defaults['hand_eye_config'], ensure_ascii=False),
        'capture_pose_json': json.dumps(getattr(recipe, 'capture_pose', {}) or {}, ensure_ascii=False),
        'devices': devices,
        'sample_preview': sample,
    }


def _save_rack_location_recipe_from_request(request, recipe=None):
    data = _request_data(request)
    recipe = recipe or RackLocationRecipe()
    recipe.recipe_name = data.get('recipe_name') or f"3D-POS-{data.get('position_no', 1)}-L{data.get('layer_no', 1)}"
    recipe.rack_type = data.get('rack_type') or ''
    recipe.rack_side = data.get('rack_side') or 'LEFT'
    recipe.position_no = _as_int(data.get('position_no'), 1)
    recipe.layer_count = _as_int(data.get('layer_count'), 3)
    recipe.layer_no = _as_int(data.get('layer_no'), 1)
    recipe.capture_pose_name = data.get('capture_pose_name') or ''
    recipe.standard_x = _as_float(data.get('standard_x'), 0)
    recipe.standard_y = _as_float(data.get('standard_y'), 0)
    recipe.standard_z = _as_float(data.get('standard_z'), 0)
    recipe.standard_rz = _as_float(data.get('standard_rz'), 0)
    
    # 保存3D ROI坐标到roi_config（机器人基坐标系）
    roi_config = {
        'coordinate_system': 'robot',  # 机器人基坐标系
        'x_min': _as_float(data.get('roi_x_min'), 0),
        'x_max': _as_float(data.get('roi_x_max'), 0),
        'y_min': _as_float(data.get('roi_y_min'), 0),
        'y_max': _as_float(data.get('roi_y_max'), 0),
        'z_min': _as_float(data.get('roi_z_min'), 0),
        'z_max': _as_float(data.get('roi_z_max'), 0),
    }
    camera_roi_fields = {
        key: data.get(f'camera_roi_{key}')
        for key in ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
    }
    if all(value not in (None, '') for value in camera_roi_fields.values()):
        roi_config['camera_roi'] = {
            key: _as_float(value) for key, value in camera_roi_fields.items()
        }
    for key in ('margin_mm', 'voxel_mm'):
        if data.get(key) not in (None, ''): roi_config[key] = data[key]
    recipe.roi_config = _merge_rack_roi_config(recipe.roi_config, roi_config)
    
    recipe.reference_feature_config = dict(
        _json_config(data.get('reference_feature_config'), {}),
    )
    recipe.hand_eye_config = _json_config(data.get('hand_eye_config'), {'matrix': 'identity'})
    recipe.capture_pose = _json_config(data.get('capture_pose'), recipe.capture_pose or {})
    
    # 允许偏差字段保留默认值，不再从表单读取（保留用于数据库兼容性）
    recipe.enabled = _as_bool(data.get('enabled'), True)
    camera_device_id = data.get('camera_device') or data.get('camera_device_id') or None
    recipe.camera_device_id = camera_device_id or None
    recipe.save()
    return recipe


@require_http_methods(['GET', 'POST'])
def rack_location_recipe_create(request):
    if request.method == 'POST':
        try:
            recipe = _save_rack_location_recipe_from_request(request)
            messages.success(request, f'3D料架定位配方已保存：{recipe.recipe_name}')
            return redirect('vision:rack_location_recipe_edit', recipe_id=recipe.id)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            messages.error(request, f'保存失败：{exc}')
    # 支持 GET 参数预填（从配方管理页 Modal 跳转而来）
    prefill = {k: v for k, v in request.GET.items() if v not in (None, '')}
    return render(request, 'vision/rack_location_recipe_form.html',
                  _rack_location_recipe_form_context(prefill=prefill or None))


@require_http_methods(['GET', 'POST'])
def rack_location_recipe_edit(request, recipe_id):
    recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
    if request.method == 'POST':
        try:
            recipe = _save_rack_location_recipe_from_request(request, recipe)
            messages.success(request, f'3D料架定位配方已更新：{recipe.recipe_name}')
            return redirect('vision:rack_location_recipe_edit', recipe_id=recipe.id)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            messages.error(request, f'保存失败：{exc}')
    return render(request, 'vision/rack_location_recipe_form.html', _rack_location_recipe_form_context(recipe))


def rack_location_history(request):
    qs = (
        RackLocationResult.objects
        .select_related('recipe', 'recipe__hand_eye_calibration', 'vision_task')
        .order_by('-created_at')
    )
    # GET 参数筛选
    position_no = request.GET.get('position_no')
    layer_no = request.GET.get('layer_no')
    locate_ok = request.GET.get('locate_ok')
    plc_status = request.GET.get('plc_status')
    if position_no not in (None, ''):
        qs = qs.filter(position_no=int(position_no))
    if layer_no not in (None, ''):
        qs = qs.filter(layer_no=int(layer_no))
    if locate_ok not in (None, ''):
        qs = qs.filter(is_success=_as_bool(locate_ok))
    if plc_status not in (None, ''):
        qs = qs.filter(plc_write_status=plc_status)
    results = qs[:200]
    return render(request, 'vision/rack_location_history.html', {
        'results': results,
        'filter_position_no': position_no or '',
        'filter_layer_no': layer_no or '',
        'filter_locate_ok': locate_ok or '',
        'filter_plc_status': plc_status or '',
    })


@require_POST
def rack_location_capture(request):
    try:
        data = _request_data(request)
        payload = RackLocationService().capture_standard_image(recipe_id=data.get('recipe_id') or None)
        return JsonResponse({'success': True, **payload})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': f'相机采集失败: {exc}'}, status=400)




@require_http_methods(['GET', 'POST', 'PATCH', 'DELETE'])
def api_vision_3d_recipes(request):
    if request.method == 'GET':
        qs = RackLocationRecipe.objects.all().order_by('rack_type', 'recipe_name', '-updated_at')
        recipe_id = request.GET.get('id')
        layer_no = request.GET.get('layer_no')
        enabled = request.GET.get('enabled')
        if recipe_id:
            qs = qs.filter(id=recipe_id)
        if layer_no not in (None, ''):
            qs = qs.filter(layer_no=int(layer_no))
        if enabled not in (None, ''):
            qs = qs.filter(enabled=_as_bool(enabled))
        return _api3d_success({
            'recipes': [_serialize_3d_recipe(recipe) for recipe in qs],
        })

    if request.method == 'PATCH':
        try:
            data = _request_data(request)
            recipe_id = data.get('id')
            if not recipe_id:
                return _api3d_error('缺少配方ID')
            recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
            
            # 更新字段
            if 'recipe_name' in data:
                recipe.recipe_name = data['recipe_name']
            if 'layer_no' in data:
                layer_no = _as_int(data['layer_no'], recipe.layer_no)
                locate_semantics(
                    locate_type='GLOBAL' if layer_no == 0 else 'LAYER',
                    layer_index=layer_no,
                )
                recipe.layer_no = layer_no
            if 'position_no' in data:
                recipe.position_no = _as_int(data['position_no'], recipe.position_no)
            if 'rack_side' in data:
                recipe.rack_side = str(data['rack_side']).upper()
            if 'rack_type' in data:
                recipe.rack_type = data['rack_type']
            if 'layer_count' in data:
                recipe.layer_count = _as_int(data['layer_count'], recipe.layer_count)
            if 'standard_x' in data:
                recipe.standard_x = _as_float(data['standard_x'], recipe.standard_x)
            if 'standard_y' in data:
                recipe.standard_y = _as_float(data['standard_y'], recipe.standard_y)
            if 'standard_z' in data:
                recipe.standard_z = _as_float(data['standard_z'], recipe.standard_z)
            if 'standard_rz' in data:
                recipe.standard_rz = _as_float(data['standard_rz'], recipe.standard_rz)
            if 'roi_config' in data:
                recipe.roi_config = _merge_rack_roi_config(
                    recipe.roi_config,
                    data['roi_config'],
                    stamp_measurement=True,
                )
            if 'reference_feature_config' in data:
                recipe.reference_feature_config = dict(
                    data['reference_feature_config'] or {},
                )
            if data.get('hand_eye_config'):
                recipe.hand_eye_config = data['hand_eye_config']
            if data.get('capture_pose'):
                recipe.capture_pose = data['capture_pose']
            if 'enabled' in data:
                recipe.enabled = _as_bool(data['enabled'])
            
            recipe.save()
            return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
        except Exception as exc:  # noqa: BLE001
            return _api3d_error(exc)

    if request.method == 'DELETE':
        try:
            data = _request_data(request)
            recipe_id = data.get('id')
            if not recipe_id:
                return _api3d_error('缺少配方ID')
            recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
            recipe_name = recipe.recipe_name
            recipe.delete()
            return _api3d_success({'message': f'配方「{recipe_name}」已删除'})
        except Exception as exc:  # noqa: BLE001
            return _api3d_error(exc)

    # POST - 创建新配方
    try:
        data = _request_data(request)
        source_recipe_id = data.get('source_recipe_id')
        if source_recipe_id:
            source = get_object_or_404(RackLocationRecipe, pk=source_recipe_id)
            recipe_name = str(data.get('recipe_name') or '').strip()
            rack_no = str(data.get('rack_type') or '').strip()
            layer_count = _as_int(data.get('layer_count'), source.layer_count)
            if not recipe_name:
                return _api3d_error('请填写副本配方名称')
            if not rack_no:
                return _api3d_error('请填写副本料架号')
            if layer_count not in (2, 3):
                return _api3d_error('料架层数只能是 2 或 3')

            with transaction.atomic():
                recipe = deepcopy(source)
                recipe.pk = None
                recipe.id = None
                recipe._state.adding = True
                recipe.recipe_name = recipe_name
                recipe.rack_type = rack_no
                recipe.layer_count = layer_count
                # 新增副本会立即进入工作台编辑，因此即使源配方已禁用，
                # 副本也必须出现在工作台的“已启用配方”下拉框中。
                recipe.enabled = True
                recipe.save(force_insert=True)

                for related_name in ('rois_3d', 'enhanced_rois_3d'):
                    for source_roi in getattr(source, related_name).all():
                        copied_roi = deepcopy(source_roi)
                        copied_roi.pk = None
                        copied_roi.id = None
                        copied_roi._state.adding = True
                        copied_roi.recipe = recipe
                        copied_roi.save(force_insert=True)

            return _api3d_success({
                'recipe': _serialize_3d_recipe(recipe),
                'message': f'已复制配方「{source.recipe_name}」',
            })

        layer_no = _as_int(data.get('layer_no'), 1)
        locate_semantics(
            locate_type='GLOBAL' if layer_no == 0 else 'LAYER',
            layer_index=layer_no,
        )
        reference_feature_config = dict(
            data.get('reference_feature_config') or {},
        )
        reference = None
        recipe = RackLocationRecipe.objects.create(
            recipe_name=data.get('recipe_name') or f"3D-L{data.get('layer_no', 1)}",
            rack_side=str(data.get('rack_side') or RackSide.BOTH).upper(),
            rack_type=data.get('rack_type') or '',
            position_no=_as_int(data.get('position_no'), 1),
            layer_no=layer_no,
            layer_count=_as_int(data.get('layer_count'), 3),
            standard_x=float(reference['center_array'][0]) if reference else _as_float(data.get('standard_x'), 0),
            standard_y=float(reference['center_array'][1]) if reference else _as_float(data.get('standard_y'), 0),
            standard_z=float(reference['center_array'][2]) if reference else _as_float(data.get('standard_z'), 0),
            standard_rz=_as_float(data.get('standard_rz'), 0),
            roi_config=data.get('roi_config') or {},
            capture_pose=data.get('capture_pose') or {},
            reference_feature_config=reference_feature_config,
            hand_eye_config=data.get('hand_eye_config') or {
                'matrix': 'identity',
                'skip_validation': True,
                'note': '开发测试模式',
            },
            enabled=_as_bool(data.get('enabled'), True),
        )
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


_RACK_MASTER_TEXT_FIELDS = (
    'recipe_code', 'name', 'product_code', 'rack_type',
    'loading_direction', 'full_condition',
)
_RACK_MASTER_INTEGER_FIELDS = (
    'station_position_count', 'layer_count', 'quantity_per_layer',
    'total_quantity', 'version',
)
_RACK_MASTER_DECIMAL_FIELDS = (
    'layer_height', 'layer_spacing', 'tolerance_x', 'tolerance_y', 'tolerance_z',
)


def _assign_rack_master_fields(recipe, data):
    for field in _RACK_MASTER_TEXT_FIELDS:
        if field in data:
            setattr(recipe, field, str(data[field] or '').strip())
    for field in _RACK_MASTER_INTEGER_FIELDS:
        if field in data:
            setattr(recipe, field, _as_int(data[field], getattr(recipe, field)))
    for field in _RACK_MASTER_DECIMAL_FIELDS:
        if field in data:
            setattr(recipe, field, _as_float(data[field], getattr(recipe, field)))
    if 'is_active' in data:
        recipe.is_active = _as_bool(data['is_active'])


@require_http_methods(['GET', 'POST', 'PATCH'])
def api_rack_master_recipes(request):
    """Manage MES/master rack recipes without rewriting legacy vision recipes."""
    if request.method == 'GET':
        recipes = (
            RackRecipe.objects
            .prefetch_related('vision_mappings__rack_location_recipe')
            .order_by('-is_active', 'recipe_code')
        )
        recipe_id = request.GET.get('id')
        if recipe_id:
            recipes = recipes.filter(pk=recipe_id)
        return _api3d_success({
            'recipes': [serialize_rack_recipe(recipe) for recipe in recipes],
        })

    try:
        data = _request_data(request)
        with transaction.atomic():
            if request.method == 'PATCH':
                recipe_id = data.get('id')
                if not recipe_id:
                    return _api3d_error('缺少料架主配方ID')
                recipe = get_object_or_404(RackRecipe, pk=recipe_id)
            else:
                recipe = RackRecipe()
            _assign_rack_master_fields(recipe, data)
            recipe.full_clean()
            recipe.save()
        return _api3d_success({
            'recipe': serialize_rack_recipe(recipe),
            'message': '料架主配方已更新' if request.method == 'PATCH' else '料架主配方已创建',
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_rack_master_mapping_save(request):
    try:
        data = _request_data(request)
        recipe = get_object_or_404(RackRecipe, pk=data.get('rack_recipe_id'))
        station_position_no = _as_int(data.get('station_position_no'), 0)
        layer_no = _as_int(data.get('layer_no'), 0)
        vision_recipe_id = data.get('rack_location_recipe_id') or None
        vision_recipe = None
        if vision_recipe_id:
            vision_recipe = get_object_or_404(RackLocationRecipe, pk=vision_recipe_id)
        with transaction.atomic():
            mapping, _ = RackRecipeVisionMapping.objects.get_or_create(
                rack_recipe=recipe,
                station_position_no=station_position_no,
                layer_no=layer_no,
            )
            mapping.rack_location_recipe = vision_recipe
            mapping.robot_target_code = str(data.get('robot_target_code') or '').strip()
            mapping.enabled = _as_bool(data.get('enabled'), True)
            mapping.full_clean()
            mapping.save()
        recipe.refresh_from_db()
        return _api3d_success({
            'recipe': serialize_rack_recipe(recipe),
            'message': f'{station_position_no}号位第{layer_no}层映射已保存',
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET'])
def api_rack_master_recipe_validate(request, recipe_id):
    recipe = get_object_or_404(RackRecipe, pk=recipe_id)
    return _api3d_success({'validation': validate_rack_recipe(recipe)})


@require_http_methods(['GET'])
def api_rack_master_recipe_resolve(request, recipe_id):
    try:
        recipe = get_object_or_404(RackRecipe, pk=recipe_id)
        completed_quantity = _as_int(request.GET.get('completed_quantity'), 0)
        station_position_no = _as_int(request.GET.get('station_position_no'), 1)
        if not 1 <= station_position_no <= recipe.station_position_count:
            return _api3d_error('工位位置超出当前配方范围')
        return _api3d_success({
            'resolution': RackPositionResolver(recipe).resolve(
                completed_quantity,
                station_position_no,
            ),
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET', 'PUT'])
def api_vision_3d_recipe_detail(request, recipe_id):
    recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
    if request.method == 'GET':
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    try:
        data = _request_data(request)
        for field in (
            'recipe_name', 'rack_side', 'rack_type', 'capture_pose_name',
            'standard_x', 'standard_y', 'standard_z', 'standard_rz',
            'roi_config', 'reference_feature_config', 'hand_eye_config',
            'capture_pose', 'enabled',
        ):
            if field in data:
                if field == 'roi_config':
                    recipe.roi_config = _merge_rack_roi_config(
                        recipe.roi_config,
                        data[field],
                        stamp_measurement=True,
                    )
                else:
                    setattr(recipe, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        recipe.reference_feature_config = dict(
            recipe.reference_feature_config or {},
        )
        for field in ('position_no', 'layer_no', 'layer_count'):
            if field in data:
                value = _as_int(data[field], getattr(recipe, field))
                if field == 'layer_no':
                    locate_semantics(
                        locate_type='GLOBAL' if value == 0 else 'LAYER',
                        layer_index=value,
                    )
                setattr(recipe, field, value)
        recipe.save()
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET', 'POST'])
def api_vision_3d_rois(request):
    if request.method == 'GET':
        qs = RackLocationROI3D.objects.select_related('recipe').all()
        recipe_id = request.GET.get('recipe_id')
        if recipe_id not in (None, ''):
            qs = qs.filter(recipe_id=recipe_id)
        return _api3d_success({'rois': [_serialize_3d_roi(roi) for roi in qs.order_by('mode', 'layer_no')]})

    return _api3d_error('旧 3D ROI 示教已移除，请在点云模板工作台保存区域')


@require_http_methods(['PUT'])
def api_vision_3d_roi_detail(request, roi_id):
    try:
        roi = get_object_or_404(RackLocationROI3D, pk=roi_id)
        data = _request_data(request)
        for field in (
            'roi_name', 'mode', 'layer_no', 'coordinate_system',
            'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max', 'enabled',
        ):
            if field in data:
                setattr(roi, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        roi.save()
        return _api3d_success({'roi': _serialize_3d_roi(roi)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_vision_3d_capture(request):
    """3D视觉采集点云API"""
    try:
        data = _request_data(request)
        payload = Rack3DLocator().capture(
            recipe_id=data.get('recipe_id') or None,
            rack_side=data.get('rack_side') or 'LEFT',
            layer_no=_as_int(data.get('layer_no'), 1),
        )
        return _api3d_success(payload)
    except json.JSONDecodeError as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"JSON解析失败 in api_vision_3d_capture: {exc}")
        return _api3d_error(f'请求数据格式错误: {exc}')
    except Exception as exc:  # noqa: BLE001
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"采集点云失败: {exc}\n{traceback.format_exc()}")
        return _api3d_error(exc)


@require_POST
def api_vision_3d_camera_test(request):
    try:
        from apps.rvc_camera.services import RvcCameraService
        status = RvcCameraService().get_status()
        return _api3d_success({
            'online': bool(status.get('connected') or status.get('streaming')),
            'status': status,
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_success({
            'online': False,
            'status': {'error': str(exc)},
        })






@require_POST
def api_vision_3d_locate(request):
    try:
        data = _request_data(request)
        semantics = locate_semantics(
            locate_type=(
                data.get('locate_type')
                or ('GLOBAL' if _as_int(data.get('layer_index'), 1) == 0 else 'LAYER')
            ),
            layer_index=(
                data.get('layer_index')
                if data.get('layer_index') is not None
                else data.get('layer_no')
            ),
        )
        result = Rack3DLocator().locate(
            rack_side=data.get('rack_side') or 'BOTH',
            layer_no=semantics['layer_no'],
            recipe_id=data.get('recipe_id') or None,
            write_plc=_as_bool(data.get('write_plc'), False),
        )
        return _api3d_success({'result': rack_location_result_payload(result)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_vision_3d_test_locate(request):
    try:
        data = _request_data(request)
        payload = Rack3DLocator().test_locate(
            token=data.get('pointcloud_token'),
            roi_3d=data.get('roi') or data.get('roi_3d') or {},
            roi_config=data.get('roi_config'),
            recipe_id=data.get('recipe_id') or None,
            rack_side=data.get('rack_side') or 'LEFT',
            layer_no=_as_int(data.get('layer_no'), 1),
            save_record=data.get('save_record', False),
        )
        return _api3d_success({'result': payload})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET'])
def api_vision_3d_results_latest(request):
    result = (
        RackLocationResult.objects
        .select_related('recipe', 'vision_task')
        .order_by('-created_at')
        .first()
    )
    return _api3d_success({'result': rack_location_result_payload(result) if result else None})


@require_http_methods(['GET'])
def api_vision_3d_results(request):
    qs = RackLocationResult.objects.select_related('recipe', 'vision_task').order_by('-created_at')
    layer_index = request.GET.get('layer_index')
    if layer_index not in (None, ''):
        qs = qs.filter(layer_no=int(layer_index))

    locate_type = request.GET.get('locate_type')
    if locate_type:
        expected = normalize_locate_type(locate_type)
        results = [
            result for result in qs[:200]
            if (result.result_data or {}).get('locate_type') == expected
            or (expected == 'GLOBAL' and int(result.layer_no or 0) == 0)
            or (expected == 'LAYER' and int(result.layer_no or 0) in {1, 2, 3})
        ]
        return _api3d_success({'results': [rack_location_result_payload(result) for result in results]})

    return _api3d_success({'results': [rack_location_result_payload(result) for result in qs[:100]]})


@require_POST
def api_vision_3d_write_plc(request):
    try:
        data = _request_data(request)
        result = get_object_or_404(RackLocationResult, pk=data.get('result_id'))
        response = Rack3DLocator().write_result_to_plc(result)
        result.refresh_from_db()
        return _api3d_success({
            'plc_response': response,
            'result': rack_location_result_payload(result),
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_rack_location_workbench_capture(request):
    """工作台「采集点云」：真实 3D 相机优先，离线回退模拟，返回预览图与 token。"""
    try:
        data = _request_data(request)
        payload = RackLocationService().capture_workbench(recipe_id=data.get('recipe_id') or None)
        return JsonResponse({'success': True, **payload})
    except json.JSONDecodeError as exc:
        return JsonResponse({'success': False, 'error': f'JSON解析失败: {exc}'}, status=400)
    except Exception as exc:  # noqa: BLE001
        logger.exception('工作台点云采集失败')
        return JsonResponse({'success': False, 'error': f'相机采集失败: {exc}'}, status=400)






@require_POST
def api_rack_location_trigger(request):
    """Trigger 3D location using the requested workstation, layer and side."""
    try:
        data = _request_data(request)
        layer_no = _as_int(data.get('layer_no'), 1)
        recipe_id = data.get('recipe_id') or None
        write_plc = _as_bool(data.get('write_plc'), False)
        
        # 使用简化的服务
        result = RackLocationService().trigger(
            position_no=_as_int(data.get('position_no'), 1),
            layer_no=layer_no,
            recipe_id=recipe_id,
            rack_side=data.get('rack_side') or RackSide.BOTH,
            write_plc=write_plc,
        )
        return JsonResponse({'success': True, 'result': rack_location_result_payload(result)})
    except RackLocationRecipe.DoesNotExist:
        return JsonResponse({'success': False, 'error': '未找到启用的3D料架定位配方'}, status=404)
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@require_POST
def api_rack_location_write_plc(request):
    try:
        data = _request_data(request)
        result = get_object_or_404(RackLocationResult, pk=data.get('result_id'))
        response = PlcVisionResultWriter().write(result)
        result.refresh_from_db()
        return JsonResponse({
            'success': bool(response.get('success')),
            'plc_response': response,
            'result': rack_location_result_payload(result),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'POST'])
def api_rack_location_recipes(request):
    if request.method == 'GET':
        qs = RackLocationRecipe.objects.all()
        position_no = request.GET.get('position_no')
        layer_no = request.GET.get('layer_no')
        enabled = request.GET.get('enabled')
        if position_no not in (None, ''):
            qs = qs.filter(position_no=int(position_no))
        if layer_no not in (None, ''):
            qs = qs.filter(layer_no=int(layer_no))
        if enabled not in (None, ''):
            qs = qs.filter(enabled=_as_bool(enabled))
        return JsonResponse({
            'success': True,
            'recipes': [_serialize_rack_location_recipe(recipe) for recipe in qs.order_by('layer_no', '-updated_at')],
        })

    try:
        data = _request_data(request)
        layer_no = _as_int(data.get('layer_no'), 1)
        enabled = _as_bool(data.get('enabled'), True)
        position_no = 1  # 固定为1
        # 唯一性校验：同一层下只允许一个启用配方
        if enabled and RackLocationRecipe.objects.filter(
            position_no=1, layer_no=layer_no, enabled=True,
        ).exists():
            return JsonResponse({
                'success': False,
                'error': f'层号 {layer_no} 已存在启用的配方，请先禁用或编辑现有配方',
            }, status=400)
        reference_feature_config = dict(
            data.get('reference_feature_config') or {},
        )
        reference = None
        recipe = RackLocationRecipe.objects.create(
            recipe_name=data.get('recipe_name') or f"3D-L{layer_no}",
            rack_type=data.get('rack_type') or '',
            rack_side='BOTH',
            position_no=1,
            layer_count=_as_int(data.get('layer_count'), 3),
            layer_no=layer_no,
            capture_pose_name=data.get('capture_pose_name') or '',
            standard_x=float(reference['center_array'][0]) if reference else data.get('standard_x') or 0,
            standard_y=float(reference['center_array'][1]) if reference else data.get('standard_y') or 0,
            standard_z=float(reference['center_array'][2]) if reference else data.get('standard_z') or 0,
            standard_rz=data.get('standard_rz') or 0,
            roi_config=data.get('roi_config') or {},
            reference_feature_config=reference_feature_config,
            hand_eye_config=data.get('hand_eye_config') or {'matrix': 'identity'},
            max_offset_x=data.get('max_offset_x') or 10,
            max_offset_y=data.get('max_offset_y') or 10,
            max_offset_z=data.get('max_offset_z') or 10,
            max_offset_rz=data.get('max_offset_rz') or 5,
            confidence_threshold=data.get('confidence_threshold') or 0.7,
            enabled=_as_bool(data.get('enabled'), True),
        )
        return JsonResponse({'success': True, 'recipe': _serialize_rack_location_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_POST
def api_rack_location_recipe_update(request, recipe_id):
    try:
        recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
        data = _request_data(request)
        updatable = [
            'recipe_name', 'rack_type', 'capture_pose_name',
            'standard_x', 'standard_y', 'standard_z', 'standard_rz',
            'roi_config', 'reference_feature_config', 'hand_eye_config',
            'max_offset_x', 'max_offset_y', 'max_offset_z', 'max_offset_rz',
            'confidence_threshold', 'enabled',
        ]
        for field in updatable:
            if field in data:
                if field == 'roi_config':
                    recipe.roi_config = _merge_rack_roi_config(
                        recipe.roi_config,
                        data[field],
                        stamp_measurement=True,
                    )
                else:
                    setattr(recipe, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        recipe.reference_feature_config = dict(
            recipe.reference_feature_config or {},
        )
        # 固定position_no=1
        recipe.position_no = 1
        if 'layer_no' in data:
            recipe.layer_no = _as_int(data.get('layer_no'), recipe.layer_no)
        if 'layer_count' in data:
            recipe.layer_count = _as_int(data.get('layer_count'), recipe.layer_count)
        recipe.rack_side = 'BOTH'
        recipe.save()
        return JsonResponse({'success': True, 'recipe': _serialize_rack_location_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)




@require_http_methods(['GET'])
def api_rack_location_recipe_detail(request, recipe_id):
    """获取配方详情，包含已保存的ROI坐标"""
    try:
        recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
        serialized = _serialize_rack_location_recipe(recipe)
        
        from .rack_cloud_roi import config_status
        roi_info = config_status((recipe.roi_config or {}).get('cloud_match_config'))

        serialized['roi_info'] = roi_info
        
        return JsonResponse({'success': True, 'recipe': serialized})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)


@require_http_methods(['GET'])
def api_rack_location_results(request):
    try:
        qs = (
            RackLocationResult.objects
            .select_related('recipe', 'recipe__hand_eye_calibration', 'vision_task')
            .order_by('-created_at')
        )
        position_no = request.GET.get('position_no')
        layer_no = request.GET.get('layer_no')
        locate_ok = request.GET.get('locate_ok')
        if position_no not in (None, ''):
            qs = qs.filter(position_no=int(position_no))
        if layer_no not in (None, ''):
            qs = qs.filter(layer_no=int(layer_no))
        if locate_ok not in (None, ''):
            qs = qs.filter(is_success=_as_bool(locate_ok))
        return JsonResponse({
            'success': True,
            'results': [rack_location_result_payload(result) for result in qs[:100]],
        })
    except (TypeError, ValueError) as exc:
        return JsonResponse({
            'success': False,
            'error': f'筛选参数格式无效：{exc}',
        }, status=400)
    except Exception:  # noqa: BLE001
        logger.exception('加载3D相机记录失败')
        return JsonResponse({
            'success': False,
            'error': '加载3D相机记录失败，请查看服务日志',
        }, status=500)





def roi_3d_workbench(request):
    """3D ROI裁剪工作台页面"""
    return redirect('vision:rack_locator_panel')


@require_POST
def api_foam_save_images(request, result_id):
    try:
        if not FoamInspectionResult.objects.filter(pk=result_id).exists():
            return JsonResponse({'success': False, 'error': '检测记录不存在'}, status=404)
        directory = foam_archive.save_images(result_id)
        return JsonResponse({'success': True, 'directory': directory})
    except (ValueError, OSError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


def api_foam_record_image(request, result_id, kind):
    from django.http import HttpResponse, Http404
    try:
        content = foam_archive.image_bytes(result_id, kind)
        if content is None:
            raise Http404('图片不存在或缓存已过期')
        mime = 'image/jpeg' if content.startswith(b'\xff\xd8') else ('image/bmp' if content.startswith(b'BM') else 'image/png')
        response = HttpResponse(content, content_type=mime)
        response['Cache-Control'] = 'no-store'
        return response
    except (ValueError, OSError):
        raise Http404('图片不存在或缓存已过期')
