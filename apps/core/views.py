from django.shortcuts import redirect


def dashboard(request):
    """根路径直接进入设备页面。"""
    return redirect('devices:status')
