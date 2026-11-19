"""Video debugging and live camera controls, with separate I/O ownership."""
import json
from pathlib import Path
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import foam_video_sessions as videos


def owner(request):
    if not request.session.get('foam_video_owner'):
        request.session['foam_video_owner'] = uuid.uuid4().hex
    return request.session['foam_video_owner']


@require_GET
def configuration(request):
    path = videos.profile_path()
    profile = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    return JsonResponse({'success':True,'ready':profile is not None,
        'profile_name':profile['name'] if profile else '',
        'scope':profile.get('scope','') if profile else '请先配置正常泡棉标准模板',
        'samples':[p.name for p in (Path(settings.BASE_DIR)/'2d_SDK/pic2').glob('*.avi')],
        'max_upload_mb':256,
        'plc_enabled':False,
        'auto_start':getattr(settings,'FOAM_STREAM_AUTO_START',False)})


@require_POST
def open_video(request):
    path = None
    owned = False
    try:
        if request.FILES.get('video'):
            upload = request.FILES['video']
            suffix = Path(upload.name).suffix.lower()
            if suffix not in {'.avi','.mp4','.mov','.mkv'} or upload.size > 256*1024*1024:
                raise ValueError('支持 AVI / MP4 / MOV / MKV，文件不超过 256 MB')
            directory = Path(settings.MEDIA_ROOT)/'vision/foam_video_debug'
            directory.mkdir(parents=True,exist_ok=True)
            path = directory/(uuid.uuid4().hex+suffix)
            owned = True
            with path.open('xb') as output:
                for chunk in upload.chunks():
                    output.write(chunk)
        else:
            data = json.loads(request.body or '{}')
            if not isinstance(data, dict):
                raise ValueError('请求内容必须是 JSON 对象')
            sample = data.get('sample','')
            allowed = {p.name:p for p in (Path(settings.BASE_DIR)/'2d_SDK/pic2').glob('*.avi')}
            if sample not in allowed:
                raise ValueError('请选择视频文件或列表中的测试素材')
            path = allowed[sample]
        token, metadata = videos.create(path,owned=owned,owner=owner(request))
        if request.FILES.get('video'):
            metadata['filename'] = Path(request.FILES['video'].name).name
        return JsonResponse({'success':True,'session':token,**metadata})
    except (ValueError,OSError,KeyError) as exc:
        if owned and path:
            path.unlink(missing_ok=True)
        return JsonResponse({'success':False,'error':str(exc)},status=400)


@require_POST
def video_frame(request, token):
    try:
        data = json.loads(request.body or '{}')
        if not isinstance(data, dict):
            raise ValueError('请求内容必须是 JSON 对象')
        result = videos.get(token,owner(request)).next(data.get('seek'))
        return JsonResponse({'success':True,**result})
    except (ValueError,OSError,KeyError) as exc:
        return JsonResponse({'success':False,'error':str(exc)},status=400)


@require_POST
def close_video(request, token):
    videos.close(token,owner(request))
    return JsonResponse({'success':True})


@require_POST
def live_control(request):
    from .foam_live import runtime
    try:
        data = json.loads(request.body or '{}')
        if not isinstance(data, dict):
            raise ValueError('请求内容必须是 JSON 对象')
        action = data.get('action')
        if action in ('start', 'enter_manual'):
            runtime.set_manual(True)
        elif action in ('stop', 'resume_auto'):
            runtime.set_manual(False)
        elif action == 'reset':
            runtime.reset()
        else:
            raise ValueError('未知相机操作')
        return JsonResponse({'success':True,**runtime.status(),'manual':runtime.manual_status()})
    except (ValueError,OSError,RuntimeError) as exc:
        return JsonResponse({'success':False,'error':str(exc)},status=400)


@require_GET
def live_status(request):
    from .foam_live import runtime
    try:
        return JsonResponse({'success':True,**runtime.status(),'manual':runtime.manual_status()})
    except RuntimeError as exc:
        return JsonResponse({'success':False,'error':str(exc)},status=409)
