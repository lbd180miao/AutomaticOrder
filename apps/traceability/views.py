from django.shortcuts import render

from .services import TraceabilityService


def search(request):
    query = request.GET.get('q', '').strip()
    mode = request.GET.get('mode', 'product')
    context = {'query': query, 'mode': mode, 'result': None, 'rack_result': None}

    if query:
        service = TraceabilityService()
        if mode == 'rack':
            context['rack_result'] = service.trace_by_rack_code(query)
            if context['rack_result'] is None:
                context['not_found'] = True
        else:
            context['result'] = service.trace_by_product_code(query)
            if context['result'] is None:
                context['not_found'] = True
    return render(request, 'traceability/search.html', context)
