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
from .models import FoamInspectionResult, RackLocationResult, VisionImage, VisionTask
from .services import VisionService


def task_list(request):
    tasks = (
        VisionTask.objects.select_related('product', 'rack')
        .prefetch_related('images').order_by('-created_at')[:200]
    )
    return render(request, 'vision/task_list.html', {'tasks': tasks})


def capture_foam_roi(request):
    """Manual 2D foam ROI capture, mirroring a PLC sequence trigger."""
    if request.method != 'POST':
        messages.info(request, '请在视觉任务列表页点击“2D相机拍照检测ROI”按钮触发拍照。')
        return redirect('vision:task_list')

    raw_sequence = request.POST.get('plc_sequence', '0')
    try:
        position_index = int(raw_sequence)
    except (TypeError, ValueError):
        position_index = 0
    position_index = max(position_index, 0)

    try:
        result = VisionService().inspect_foam(
            product=None,
            rack=None,
            position_index=position_index,
            simulated_pass=True,
            use_camera=True,
        )
    except RuntimeError as exc:
        messages.error(request, f'2D相机拍照失败：{exc}')
        return redirect('vision:task_list')

    messages.success(
        request,
        f'2D相机已按PLC序号 {position_index} 完成拍照和ROI检测。',
    )
    return redirect('vision:task_detail', pk=result.vision_task_id)


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


@require_POST
def capture_depth_roi(request):
    """Manual depth-camera ROI capture for rack-location debugging."""
    rack, recipe = _get_depth_roi_debug_context()
    left, _right = VisionService().locate_both_racks(
        product=None,
        rack=rack,
        recipe=recipe,
    )
    messages.success(request, '深度相机已完成拍照和ROI定位调试。')
    return redirect('vision:task_detail', pk=left.vision_task_id)


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
