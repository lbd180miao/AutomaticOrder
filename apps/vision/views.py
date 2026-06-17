from django.shortcuts import get_object_or_404, render

from .models import FoamInspectionResult, RackLocationResult, VisionImage, VisionTask


def task_list(request):
    tasks = (
        VisionTask.objects.select_related('product', 'rack')
        .prefetch_related('images').order_by('-created_at')[:200]
    )
    return render(request, 'vision/task_list.html', {'tasks': tasks})


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
