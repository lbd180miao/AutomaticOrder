from django.shortcuts import render

from .services import DashboardService


def dashboard(request):
    context = DashboardService().get_summary()
    return render(request, 'dashboard.html', context)
