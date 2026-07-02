import json
import logging
import tempfile
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from apps.devices.models import Device
from apps.production.models import Rack, RackRecipe
from .models import (
    CalibrationProfile,
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
    get_active_foam_2d_recipe_by_pos,
    serialize_recipe,
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
    sample_scene_median_xyz,
)

logger = logging.getLogger(__name__)


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
    result_img = next((i for i in images if i.image_type == 'RESULT'), None)
    rack_result = task.rack_results.first()
    foam_result = task.foam_results.first()
    return render(request, 'vision/task_detail.html', {
        'task': task,
        'original': original,
        'result_img': result_img,
        'rack_result': rack_result,
        'foam_result': foam_result,
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
    return render(request, 'vision/foam_result_detail.html', {'results': results})



def foam_inspector_interactive(request):
    """交互式泡棉检测页面"""
    return render(request, 'vision/foam_inspector_interactive.html')


def recipe_management(request):
    """视觉配方管理页面（独立页面）"""
    return render(request, 'vision/recipe_management.html')


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def _result_payload(foam_result):
    task = foam_result.vision_task
    result_image = task.images.filter(image_type='RESULT').first()
    original_image = task.images.filter(image_type='ORIGINAL').first()
    payload = {
        'task_id': task.id,
        'position_index': foam_result.position_index,
        'is_present': foam_result.is_present,
        'is_aligned': foam_result.is_aligned,
        'has_lifted_edge': foam_result.has_lifted_edge,
        'score': float(foam_result.score),
        'is_passed': foam_result.is_passed,
        'offset_x_px': float(foam_result.offset_x_px),
        'offset_y_px': float(foam_result.offset_y_px),
        'coverage_ratio': float(foam_result.coverage_ratio),
        'defect_type': foam_result.defect_type,
        'result_image_url': result_image.file.url if result_image else '',
        'original_image_url': original_image.file.url if original_image else '',
    }
    if foam_result.result_data.get('recipe'):
        payload['recipe'] = foam_result.result_data['recipe']
    return payload


@require_http_methods(['GET'])
def api_vision_recipes(request):
    ensure_default_foam_2d_recipes()
    qs = VisionRecipe.objects.all()
    recipe_type = request.GET.get('recipe_type')
    pos = request.GET.get('pos')
    camera_side = request.GET.get('camera_side')
    is_active = request.GET.get('is_active')
    if recipe_type:
        qs = qs.filter(recipe_type=recipe_type)
    if pos not in (None, ''):
        qs = qs.filter(pos=int(pos))
    if camera_side:
        qs = qs.filter(camera_side=camera_side)
    if is_active not in (None, ''):
        qs = qs.filter(is_active=_as_bool(is_active))
    return JsonResponse({
        'success': True,
        'recipes': [serialize_recipe(recipe) for recipe in qs.order_by('recipe_type', 'pos', '-updated_at')],
    })


@require_http_methods(['GET'])
def api_foam_recipe_by_pos(request):
    pos = int(request.GET.get('pos', 0))
    ensure_default_foam_2d_recipes()
    recipe = get_active_foam_2d_recipe_by_pos(pos)
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
        body = json.loads(request.body or '{}')
        pos = int(body.get('pos', 0))
        if pos < 0:
            raise ValueError('pos must be non-negative')
        roi_config = body.get('roi_config') or {}
        if not roi_config.get('leftFoamROI') or not roi_config.get('rightFoamROI'):
            raise ValueError('leftFoamROI and rightFoamROI are required')
        threshold_config = body.get('threshold_config') or {}
        recipe_id = body.get('id')
        if recipe_id:
            recipe = get_object_or_404(
                VisionRecipe, id=recipe_id, recipe_type='FOAM_2D'
            )
        else:
            recipe = get_active_foam_2d_recipe_by_pos(pos)
        if recipe is None:
            recipe = VisionRecipe(recipe_type='FOAM_2D', pos=pos, camera_side='both')
        recipe.name = body.get('name') or f'第{pos + 1}层泡棉检测配方'
        recipe.pos = pos
        recipe.camera_side = body.get('camera_side') or recipe.camera_side or 'both'
        recipe.image_width = int(body.get('image_width') or recipe.image_width or 1280)
        recipe.image_height = int(body.get('image_height') or recipe.image_height or 720)
        recipe.roi_config = roi_config
        recipe.threshold_config = threshold_config
        recipe.is_active = _as_bool(body.get('is_active'), True)
        recipe.remark = body.get('remark') or ''
        recipe.save()
        return JsonResponse({'success': True, 'recipe': serialize_recipe(recipe)})
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


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
def api_foam_recipe_create(request):
    """创建新的泡棉检测配方"""
    try:
        body = json.loads(request.body or '{}')
        pos = int(body.get('pos', 0))
        if pos < 0:
            raise ValueError('pos must be non-negative')
        
        # 检查该 POS 是否已存在配方
        existing = VisionRecipe.objects.filter(
            recipe_type='FOAM_2D',
            pos=pos,
            is_active=True
        ).first()
        
        if existing:
            return JsonResponse({
                'success': False,
                'error': f'POS {pos} 已存在配方，请先删除或编辑现有配方'
            }, status=400)
        
        # 默认 ROI 配置
        roi_config = body.get('roi_config') or {
            'leftFoamROI': {'x': 220, 'y': 140, 'width': 90, 'height': 70},
            'rightFoamROI': {'x': 780, 'y': 140, 'width': 110, 'height': 70}
        }
        
        # 默认阈值配置
        threshold_config = body.get('threshold_config') or {
            'coverage_threshold': 0.75,
            'score_threshold': 0.8,
            'max_offset_px': 30
        }
        
        recipe = VisionRecipe.objects.create(
            recipe_type='FOAM_2D',
            name=body.get('name') or f'第{pos + 1}层泡棉检测配方',
            pos=pos,
            camera_side=body.get('camera_side') or 'both',
            image_width=int(body.get('image_width') or 1280),
            image_height=int(body.get('image_height') or 720),
            roi_config=roi_config,
            threshold_config=threshold_config,
            is_active=True,
            remark=body.get('remark') or ''
        )
        
        return JsonResponse({'success': True, 'recipe': serialize_recipe(recipe)})
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


def _normalize_roi_ratio(values):
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
        
        adapter = CameraAdapter()
        result = adapter.capture(
            camera_code='CAM-INSPECT-FOAM-01',
            task_type='PREVIEW',
        )
        
        image_path = result.get('image_path')
        if not image_path:
            return JsonResponse({
                'success': False,
                'error': '相机返回的图像路径为空'
            })
        
        # 转换为相对于MEDIA_ROOT的路径
        image_path_obj = Path(image_path)
        media_root = Path(settings.MEDIA_ROOT)
        
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
    try:
        body = json.loads(request.body)
        position_index = int(body.get('position_index', 0))
        recipe_id = body.get('recipe_id') or None
        use_recipe = _as_bool(body.get('use_recipe'), True)
        
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
        
        return JsonResponse({
            'success': True,
            'result': _result_payload(foam_result),
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
        
        # 读取上传的图片
        file_bytes = uploaded_file.read()
        nparr = np.frombuffer(file_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return JsonResponse({
                'success': False,
                'error': '无法解码图片，请确保上传的是有效的图片文件'
            })
        
        # 保存上传的图片到临时位置
        temp_dir = Path(settings.MEDIA_ROOT) / 'temp_uploads'
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f'upload_{uploaded_file.name}'
        cv2.imwrite(str(temp_path), image)
        
        # 使用真实图片进行检测
        from .algorithms.foam_inspector import FoamInspector
        
        inspector = FoamInspector(simulate=False)
        recipe = None
        recipe_config = {}
        if use_recipe:
            if recipe_id:
                recipe = (
                    VisionRecipe.objects
                    .filter(id=recipe_id, recipe_type='FOAM_2D', is_active=True)
                    .first()
                )
            else:
                recipe = get_active_foam_2d_recipe_by_pos(position_index)
            if recipe:
                recipe_config = build_foam_inspection_config(recipe)
        inspection_config = {
            'score_threshold': 0.8,
            'coverage_threshold': 0.35,  # 根据实际场景调整为35%
            'max_offset_px': 30,
        }
        inspection_config.update(recipe_config)
        # 使用真实图像检测，simulated_pass参数不影响结果
        result = inspector.inspect(
            position_index=position_index,
            inspection_config=inspection_config,
            image=image,
            camera_image_path=str(temp_path),
            simulated_pass=True,  # 当image不为None时此参数被忽略
        )
        if recipe:
            result.setdefault('result_data', {})['recipe'] = serialize_recipe(recipe)
        
        # 创建视觉任务记录
        task = VisionTask.objects.create(
            task_type='FOAM_INSPECTION',
            status='SUCCESS',
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
            has_lifted_edge=result['has_lifted_edge'],
            score=result['score'],
            is_passed=result['is_passed'],
            offset_x_px=result['offset_x_px'],
            offset_y_px=result['offset_y_px'],
            coverage_ratio=result['coverage_ratio'],
            defect_type=result['defect_type'],
            result_data=result.get('result_data', {}),
        )
        
        # 保存图片记录
        original_img = VisionImage.objects.create(
            vision_task=task,
            image_type='ORIGINAL',
            file=result['original_image'],
        )
        
        result_img = VisionImage.objects.create(
            vision_task=task,
            image_type='RESULT',
            file=result['result_image'],
        )
        
        return JsonResponse({'success': True, 'result': _result_payload(foam_result)})
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': f'参数错误: {str(e)}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'检测失败: {str(e)}'
        })


# ------------------------------------------------------------------
# 料架定位工作台
# ------------------------------------------------------------------

def rack_locator_panel(request):
    """3D料架定位工作台：沿用原布局，业务改为位置/层号单次拍照补偿。"""
    latest = (
        RackLocationResult.objects
        .select_related('recipe', 'vision_task')
        .order_by('-created_at')
        .first()
    )
    recipes = RackLocationRecipe.objects.filter(enabled=True).order_by('position_no', 'layer_no')
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
            'image_width': 640,  # 默认值
            'image_height': 480,
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
    return JsonResponse({'success': True, 'data': data or {}, 'error': ''}, status=status)


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


def _serialize_rack_location_recipe(recipe):
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
        'roi_config': recipe.roi_config,
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
    semantics = locate_semantics(
        locate_type='GLOBAL' if int(recipe.layer_no or 0) == 0 else 'LAYER',
        layer_index=int(recipe.layer_no or 0),
    )
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
    """3D配方管理页面 - 独立页面"""
    recipes = RackLocationRecipe.objects.order_by('position_no', 'layer_no', '-updated_at')
    return render(request, 'vision/rack_location_recipes.html', {'recipes': recipes})


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
    recipe.roi_config = roi_config
    
    recipe.reference_feature_config = _json_config(data.get('reference_feature_config'), {})
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
        .select_related('recipe', 'vision_task')
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


@require_POST
def rack_location_preview_calculate(request):
    try:
        data = _request_data(request)
        output = RackLocationService().preview_calculate(
            recipe_data=data.get('recipe_data') or data,
            roi_config=data.get('roi_config') or {},
            recipe_id=data.get('recipe_id') or None,
        )
        payload = output.to_payload()
        return JsonResponse({'success': True, 'result': payload})
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'POST', 'PATCH', 'DELETE'])
def api_vision_3d_recipes(request):
    if request.method == 'GET':
        qs = RackLocationRecipe.objects.all().order_by('layer_no', '-updated_at')
        recipe_id = request.GET.get('id')
        layer_no = request.GET.get('layer_no')
        enabled = request.GET.get('enabled')
        if recipe_id:
            qs = qs.filter(id=recipe_id)
        if layer_no not in (None, ''):
            qs = qs.filter(layer_no=int(layer_no))
        if enabled not in (None, ''):
            qs = qs.filter(enabled=_as_bool(enabled))
        return JsonResponse({
            'success': True,
            'recipes': [_serialize_3d_recipe(recipe) for recipe in qs],
        })

    if request.method == 'PATCH':
        try:
            data = _request_data(request)
            recipe_id = data.get('id')
            if not recipe_id:
                return JsonResponse({'success': False, 'error': '缺少配方ID'}, status=400)
            recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
            
            # 更新字段
            if 'recipe_name' in data:
                recipe.recipe_name = data['recipe_name']
            if 'layer_no' in data:
                recipe.layer_no = _as_int(data['layer_no'], recipe.layer_no)
            if 'standard_x' in data:
                recipe.standard_x = _as_float(data['standard_x'], recipe.standard_x)
            if 'standard_y' in data:
                recipe.standard_y = _as_float(data['standard_y'], recipe.standard_y)
            if 'standard_z' in data:
                recipe.standard_z = _as_float(data['standard_z'], recipe.standard_z)
            if 'standard_rz' in data:
                recipe.standard_rz = _as_float(data['standard_rz'], recipe.standard_rz)
            if 'roi_config' in data:
                recipe.roi_config = data['roi_config']
            if data.get('hand_eye_config'):
                recipe.hand_eye_config = data['hand_eye_config']
            if data.get('capture_pose'):
                recipe.capture_pose = data['capture_pose']
            if 'enabled' in data:
                recipe.enabled = _as_bool(data['enabled'])
            
            recipe.position_no = 1  # 固定
            recipe.rack_side = 'BOTH'  # 固定
            recipe.save()
            return JsonResponse({
                'success': True,
                'recipe': _serialize_3d_recipe(recipe),
            })
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    if request.method == 'DELETE':
        try:
            data = _request_data(request)
            recipe_id = data.get('id')
            if not recipe_id:
                return JsonResponse({'success': False, 'error': '缺少配方ID'}, status=400)
            recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
            recipe_name = recipe.recipe_name
            recipe.delete()
            return JsonResponse({
                'success': True,
                'message': f'配方「{recipe_name}」已删除',
            })
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    # POST - 创建新配方
    try:
        data = _request_data(request)
        recipe = RackLocationRecipe.objects.create(
            recipe_name=data.get('recipe_name') or f"3D-L{data.get('layer_no', 1)}",
            rack_side='BOTH',  # 固定
            rack_type='',
            position_no=1,  # 固定
            layer_no=_as_int(data.get('layer_no'), 1),
            layer_count=3,  # 固定
            standard_x=_as_float(data.get('standard_x'), 0),
            standard_y=_as_float(data.get('standard_y'), 0),
            standard_z=_as_float(data.get('standard_z'), 0),
            standard_rz=_as_float(data.get('standard_rz'), 0),
            roi_config=data.get('roi_config') or {},
            capture_pose=data.get('capture_pose') or {},
            hand_eye_config=data.get('hand_eye_config') or {
                'matrix': 'identity',
                'skip_validation': True,
                'note': '开发测试模式',
            },
            enabled=_as_bool(data.get('enabled'), True),
        )
        return JsonResponse({
            'success': True,
            'recipe': _serialize_3d_recipe(recipe),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


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
            'hand_eye_config', 'enabled',
        ):
            if field in data:
                setattr(recipe, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        for field in ('position_no', 'layer_no', 'layer_count'):
            if field in data:
                setattr(recipe, field, _as_int(data[field], getattr(recipe, field)))
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

    try:
        data = _request_data(request)
        if data.get('locate_type') or data.get('layer_index') is not None:
            roi = Rack3DLocator().save_roi(
                recipe_id=data.get('recipe_id'),
                locate_type=data.get('locate_type') or 'LAYER',
                layer_index=(
                    data.get('layer_index')
                    if data.get('layer_index') is not None
                    else data.get('layer_no')
                ),
                alignment_token=data.get('alignment_token') or data.get('aligned_pointcloud_token'),
                roi_name=data.get('roi_name') or data.get('name') or '3D ROI',
                roi_3d={
                    'x_min': data.get('x_min'),
                    'x_max': data.get('x_max'),
                    'y_min': data.get('y_min'),
                    'y_max': data.get('y_max'),
                    'z_min': data.get('z_min'),
                    'z_max': data.get('z_max'),
                },
                enabled=_as_bool(data.get('enabled'), True),
            )
            return _api3d_success({'roi': _serialize_3d_roi(roi)})
        roi = RackLocationROI3D.objects.create(
            recipe_id=data.get('recipe_id'),
            roi_name=data.get('roi_name') or '3D ROI',
            mode=data.get('mode') or RackLocationROI3D.MODE_LOCAL,
            layer_no=data.get('layer_no') or None,
            coordinate_system=data.get('coordinate_system') or 'rack',
            x_min=data.get('x_min'),
            x_max=data.get('x_max'),
            y_min=data.get('y_min'),
            y_max=data.get('y_max'),
            z_min=data.get('z_min'),
            z_max=data.get('z_max'),
            enabled=_as_bool(data.get('enabled'), True),
        )
        return _api3d_success({'roi': _serialize_3d_roi(roi)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


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
        from apps.dm_camera.services import DMCameraService
        status = DMCameraService().get_status()
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
def api_vision_3d_align(request):
    return api_vision_3d_auto_align(request)


@require_POST
def api_vision_3d_auto_align(request):
    try:
        data = _request_data(request)
        payload = Rack3DLocator().auto_align(
            token=data.get('pointcloud_token'),
            recipe_id=data.get('recipe_id') or None,
        )
        return _api3d_success(payload)
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


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
            recipe_id=data.get('recipe_id') or None,
            rack_side=data.get('rack_side') or 'LEFT',
            layer_no=_as_int(data.get('layer_no'), 1),
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
        import traceback
        error_detail = traceback.format_exc()
        print(f"采集点云错误: {error_detail}")  # 输出到控制台便于调试
        return JsonResponse({'success': False, 'error': f'相机采集失败: {exc}'}, status=400)


@require_POST
def api_rack_location_workbench_calculate(request):
    """工作台「计算偏差」：按绘制的 ROI 裁剪持久化点云，仅预览不写库。
    
    优化：自动加载配方中保存的ROI坐标（如果有），避免每次都需要重新绘制。
    """
    try:
        data = _request_data(request)
        recipe_id = data.get('recipe_id') or None
        roi_config = data.get('roi_config') or {}
        
        # 优化：如果前端没有传入ROI配置，尝试从配方中加载已保存的ROI
        if recipe_id and not roi_config.get('target_roi'):
            recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
            if recipe and recipe.roi_config:
                saved_target_roi = recipe.roi_config.get('target_roi')
                if saved_target_roi:
                    roi_config['target_roi'] = saved_target_roi
                    logger.info(f"自动加载配方 {recipe_id} 的已保存ROI坐标")
        
        payload = RackLocationService().calculate_workbench(
            token=data.get('pointcloud_token'),
            roi_config=roi_config,
            recipe_id=recipe_id,
            recipe_data=data.get('recipe_data') or None,
            layer_no=_as_int(data.get('layer_no'), 1),
            roi_3d=data.get('roi_3d') or data.get('roi'),
            rack_side=data.get('rack_side') or 'LEFT',
        )
        return JsonResponse({'success': True, 'result': payload})
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_POST
def api_rack_location_workbench_save(request):
    """工作台「保存结果到数据库」：重新确定性计算后写入一条 RackLocationResult。
    
    简化版：只需传layer_no
    优化：自动保存ROI坐标到配方，实现首次绘制自动保存，下次自动复用。
    """
    try:
        data = _request_data(request)
        roi_config = data.get('roi_config') or {}
        recipe_id = data.get('recipe_id') or None
        layer_no = _as_int(data.get('layer_no'), 1)
        
        # 优化：将工作台上的 roi_config 保存回配方中，实现ROI坐标的持久化
        # 这样下次调用配方时，可以自动加载已保存的ROI，无需重新绘制
        if recipe_id and roi_config:
            recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
            if recipe and 'target_roi' in roi_config:
                current_config = recipe.roi_config or {}
                target_roi = roi_config['target_roi']
                
                # 保存ROI坐标（这些坐标已经是机器人基坐标系）
                current_config['target_roi'] = target_roi
                
                # 同时保存一个时间戳，方便追踪最后更新时间
                from django.utils import timezone
                current_config['target_roi_updated_at'] = timezone.now().isoformat()
                
                recipe.roi_config = current_config
                recipe.save(update_fields=['roi_config'])
                logger.info(f"已保存配方 {recipe_id} 的ROI坐标: {target_roi}")
        
        result = RackLocationService().save_workbench_result(
            token=data.get('pointcloud_token'),
            roi_config=roi_config,
            recipe_id=recipe_id,
            recipe_data=data.get('recipe_data') or None,
            layer_no=layer_no,
        )
        return JsonResponse({'success': True, 'result': rack_location_result_payload(result)})
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_POST
def api_rack_location_trigger(request):
    """触发3D定位（简化版：只需传layer_no）"""
    try:
        data = _request_data(request)
        layer_no = _as_int(data.get('layer_no'), 1)
        recipe_id = data.get('recipe_id') or None
        write_plc = _as_bool(data.get('write_plc'), False)
        
        # 使用简化的服务
        result = RackLocationService().trigger(
            layer_no=layer_no,
            recipe_id=recipe_id,
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
        recipe = RackLocationRecipe.objects.create(
            recipe_name=data.get('recipe_name') or f"3D-L{layer_no}",
            rack_type=data.get('rack_type') or '',
            rack_side='BOTH',
            position_no=1,
            layer_count=_as_int(data.get('layer_count'), 3),
            layer_no=layer_no,
            capture_pose_name=data.get('capture_pose_name') or '',
            standard_x=data.get('standard_x') or 0,
            standard_y=data.get('standard_y') or 0,
            standard_z=data.get('standard_z') or 0,
            standard_rz=data.get('standard_rz') or 0,
            roi_config=data.get('roi_config') or {},
            reference_feature_config=data.get('reference_feature_config') or {},
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
                setattr(recipe, field, _as_bool(data[field]) if field == 'enabled' else data[field])
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
        
        # 提取ROI坐标信息，方便前端使用
        roi_info = {
            'has_saved_roi': False,
            'target_roi': None,
            'roi_updated_at': None,
        }
        
        if recipe.roi_config:
            target_roi = recipe.roi_config.get('target_roi')
            if target_roi:
                roi_info['has_saved_roi'] = True
                roi_info['target_roi'] = target_roi
                roi_info['roi_updated_at'] = recipe.roi_config.get('target_roi_updated_at')
        
        serialized['roi_info'] = roi_info
        
        return JsonResponse({'success': True, 'recipe': serialized})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=404)


@require_http_methods(['GET'])
def api_rack_location_results(request):
    qs = (
        RackLocationResult.objects
        .select_related('recipe', 'vision_task')
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



def roi_3d_workbench(request):
    """3D ROI裁剪工作台页面"""
    return render(request, 'vision/roi_3d_workbench.html')
