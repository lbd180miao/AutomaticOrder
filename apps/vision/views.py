import json
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

from apps.production.models import Rack, RackRecipe
from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionImage,
    VisionTask,
)
from .services import VisionService


def task_list(request):
    tasks = (
        VisionTask.objects.select_related('product', 'rack')
        .prefetch_related('images').order_by('-created_at')[:200]
    )
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
        position_index = body.get('position_index', 0)
        
        vision_service = VisionService()
        foam_result = vision_service.inspect_foam(
            product=None,
            rack=None,
            position_index=position_index,
            simulated_pass=True,
            use_camera=True,
        )
        
        # foam_result 是 FoamInspectionResult 对象
        # 通过 vision_task 获取关联的任务
        task = foam_result.vision_task
        result_image = task.images.filter(image_type='RESULT').first()
        original_image = task.images.filter(image_type='ORIGINAL').first()
        
        return JsonResponse({
            'success': True,
            'result': {
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
        result = inspector.inspect(
            position_index=position_index,
            inspection_config={
                'score_threshold': 0.8,
                'coverage_threshold': 0.75,
                'max_offset_px': 30,
            },
            image=image,
            camera_image_path=str(temp_path),
            simulated_pass=True,
        )
        
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
        
        return JsonResponse({
            'success': True,
            'result': {
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
                'result_image_url': result_img.file.url,
                'original_image_url': original_img.file.url,
            }
        })
        
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
    """料架定位工作台页面（操作员可手动触发定位、查看左右架偏差与层高）。"""
    return render(request, 'vision/rack_locator_panel.html')


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
