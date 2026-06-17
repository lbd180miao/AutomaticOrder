from django.shortcuts import render

from .models import MesRecord


def record_list(request):
    records = (
        MesRecord.objects.select_related('product', 'rack').order_by('-created_at')[:200]
    )
    return render(request, 'mes/record_list.html', {'records': records})
