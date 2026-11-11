from django import forms
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.mes.models import PkgTypeMapping
from apps.mes.rack_types import layer_count, canonical_rack_type
from .plc_db100 import DB_NUMBER, POINTS_BY_NAME


@require_http_methods(['GET'])
def plc_mapping_library(request):
    return render(request, 'devices/plc_mapping_library.html')


class MappingForm(forms.ModelForm):
    plc_value = forms.IntegerField(min_value=-32768, max_value=32767, label='PLC 写入值')

    def clean_rack_type(self):
        count = layer_count(self.cleaned_data['rack_type'])
        if count is None:
            raise forms.ValidationError('层数必须为大于 0 的整数')
        return canonical_rack_type(count)

    class Meta:
        model = PkgTypeMapping
        fields = ('pkg_type_code', 'rack_type', 'plc_value', 'enabled')

    def clean_pkg_type_code(self):
        code = self.cleaned_data['pkg_type_code'].strip()
        if not code:
            raise forms.ValidationError('请输入 PkgTypeCode')
        return code


@require_http_methods(['GET', 'POST'])
def rack_type_mappings(request):
    if request.method == 'GET':
        rows = PkgTypeMapping.objects.all()
        query = request.GET.get('q', '').strip()
        if query:
            rows = rows.filter(pkg_type_code__icontains=query)
        point = POINTS_BY_NAME['rack_type_code']
        return JsonResponse({'items': list(rows.values('id', 'pkg_type_code', 'rack_type', 'plc_value', 'enabled')),
                             'target': f'DB{DB_NUMBER}.DBW{point.offset}', 'data_type': point.data_type})
    action = request.POST.get('action')
    if action not in ('save', 'delete'):
        return JsonResponse({'error': '无效操作'}, status=400)
    instance = None
    if request.POST.get('id'):
        try:
            instance = PkgTypeMapping.objects.get(pk=int(request.POST['id']))
        except (ValueError, PkgTypeMapping.DoesNotExist):
            return JsonResponse({'error': '映射不存在，请刷新列表'}, status=404)
    if action == 'delete':
        if instance is None:
            return JsonResponse({'error': '请选择需要删除的映射'}, status=400)
        instance.delete()
        return JsonResponse({'success': True})
    form = MappingForm(request.POST, instance=instance)
    if not form.is_valid():
        return JsonResponse({'error': '；'.join(f'{form.fields[key].label if key in form.fields else key}：{message}'
                            for key, errors in form.errors.items() for message in errors)}, status=400)
    try:
        with transaction.atomic():
            row = form.save()
    except IntegrityError:
        return JsonResponse({'error': '该 PkgTypeCode 已存在，请刷新后重试'}, status=409)
    return JsonResponse({'success': True, 'id': row.pk})
