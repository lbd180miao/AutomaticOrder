from datetime import datetime, time, timedelta

from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.alarms.models import Alarm
from apps.core.constants import AlarmStatus
from apps.devices.models import DeviceSignalRecord
from apps.mes.models import MesRecord
from apps.production.models import Product

from .services import TraceabilityService


def search(request):
    query = request.GET.get('q', '').strip()
    mode = request.GET.get('mode', 'product')
    start_date_raw = request.GET.get('start_date', '').strip()
    end_date_raw = request.GET.get('end_date', '').strip()
    start_date = parse_date(start_date_raw) if start_date_raw else None
    end_date = parse_date(end_date_raw) if end_date_raw else None
    date_error = ''

    if start_date_raw and not start_date:
        date_error = '开始日期格式不正确'
    elif end_date_raw and not end_date:
        date_error = '结束日期格式不正确'
    elif start_date and end_date and start_date > end_date:
        date_error = '开始日期不能晚于结束日期'

    current_tz = timezone.get_current_timezone()
    start_at = None
    end_before = None
    if not date_error:
        if start_date:
            start_at = timezone.make_aware(datetime.combine(start_date, time.min), current_tz)
        if end_date:
            end_before = timezone.make_aware(
                datetime.combine(end_date + timedelta(days=1), time.min), current_tz,
            )

    products = Product.objects.select_related('rack').order_by('-created_at')
    mes_records = MesRecord.objects.select_related('product', 'rack').order_by('-created_at')
    signals = DeviceSignalRecord.objects.select_related('device').order_by('-recorded_at')
    alarms = Alarm.objects.select_related('product', 'rack').order_by('-created_at')

    if start_at:
        products = products.filter(created_at__gte=start_at)
        mes_records = mes_records.filter(created_at__gte=start_at)
        signals = signals.filter(recorded_at__gte=start_at)
        alarms = alarms.filter(created_at__gte=start_at)
    if end_before:
        products = products.filter(created_at__lt=end_before)
        mes_records = mes_records.filter(created_at__lt=end_before)
        signals = signals.filter(recorded_at__lt=end_before)
        alarms = alarms.filter(created_at__lt=end_before)

    time_filter_active = bool(start_at or end_before)
    result_limit = 100 if time_filter_active else 8
    if start_date and end_date and not date_error:
        record_scope_label = f'{start_date:%Y-%m-%d} 至 {end_date:%Y-%m-%d}'
    elif start_date and not date_error:
        record_scope_label = f'{start_date:%Y-%m-%d} 起'
    elif end_date and not date_error:
        record_scope_label = f'截至 {end_date:%Y-%m-%d}'
    else:
        record_scope_label = '最近 8 条'

    context = {
        'query': query,
        'mode': mode,
        'start_date': start_date_raw,
        'end_date': end_date_raw,
        'date_error': date_error,
        'time_filter_active': time_filter_active,
        'record_scope_label': record_scope_label,
        'result': None,
        'rack_result': None,
        'recent_products': products[:result_limit],
        'recent_mes_records': mes_records[:result_limit],
        'recent_signals': signals[:result_limit],
        'recent_alarms': alarms[:result_limit],
        'record_stats': {
            'total_products': products.count(),
            'mes_total': mes_records.count(),
            'mes_failed': mes_records.filter(success=False).count(),
            'open_alarms': alarms.exclude(status=AlarmStatus.CLOSED).count(),
        },
    }

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


def product_detail(request, product_code):
    result = TraceabilityService().trace_by_product_code(product_code)
    if result is None:
        raise Http404(f'未找到产品 {product_code}')
    return render(request, 'traceability/product_detail.html', {'result': result})
