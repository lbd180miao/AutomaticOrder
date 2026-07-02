from django.shortcuts import render


def workbench(request):
    return render(request, 'coordinates/workbench.html')
