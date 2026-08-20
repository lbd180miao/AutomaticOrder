import json
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Product, ProductionBatch, Rack, RackRecipe
from .services import ProductionService
from apps.core.barcode_validator import validate_rack_barcode, validate_product_barcode


def product_list(request):
    return redirect('mes:record_list')


def rack_list(request):
    return redirect('/mes/records/?tab=bindings')


def recipe_list(request):
    return redirect('/mes/records/?tab=recipes')


@csrf_exempt
@require_http_methods(['POST'])
def validate_barcode_api(request):
    """
    POST /production/api/validate-barcode/
    即时校验条码合法性（空码、格式、重复码）
    Body (JSON): { "type": "rack"|"product", "code": "...", "rack_code": "...", "product_id": ... }
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '无效的 JSON'}, status=400)

    barcode_type = str(body.get('type', 'product')).lower()
    code = body.get('code', '')
    rack_code = body.get('rack_code')
    product_id = body.get('product_id')
    rack_id = body.get('rack_id')

    if barcode_type == 'rack':
        res = validate_rack_barcode(code, current_rack_id=rack_id, check_db_duplicate=True)
    else:
        res = validate_product_barcode(
            code,
            rack_code=rack_code,
            current_product_id=product_id,
            check_db_duplicate=True,
        )

    return JsonResponse({
        'success': res.is_valid,
        'is_valid': res.is_valid,
        'error_type': res.error_type,
        'error_message': res.error_message,
        'cleaned_code': res.cleaned_code,
    })


@csrf_exempt
@require_http_methods(['POST'])
def manual_rack_update_api(request):
    """
    POST /production/api/rack/manual-update/
    【新功能 1】：手动输入或修改料框码
    Body (JSON): { "rack_code": "RACK-001", "rack_id": 1 }
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '无效的 JSON'}, status=400)

    rack_code = body.get('rack_code')
    rack_id = body.get('rack_id')

    try:
        svc = ProductionService()
        rack = svc.update_or_create_rack_manual(rack_code, rack_id=rack_id)
        return JsonResponse({
            'success': True,
            'message': f'料框码已成功设置/更新为 {rack.rack_code}，并完成 MES 配方关联',
            'rack_id': rack.pk,
            'rack_code': rack.rack_code,
            'recipe_code': rack.current_recipe.recipe_code if rack.current_recipe else '',
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'服务器内部错误: {exc}'}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def manual_product_update_api(request):
    """
    POST /production/api/product/manual-update/
    【新功能 2】：手动修改产品条码
    Body (JSON): { "product_id": 1, "new_product_code": "P-001", "rack_code": "RACK-001" }
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '无效的 JSON'}, status=400)

    product_id = body.get('product_id')
    new_product_code = body.get('new_product_code')
    rack_code = body.get('rack_code')

    if not product_id:
        return JsonResponse({'success': False, 'error': '缺少 product_id'}, status=400)

    try:
        svc = ProductionService()
        res = svc.update_product_barcode_manual(product_id, new_product_code, rack_code=rack_code)
        return JsonResponse({
            'success': True,
            'message': res['message'],
            'product_id': res['product'].pk,
            'product_code': res['product'].product_code,
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'修改失败: {exc}'}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def product_defective_api(request):
    """
    POST /production/api/product/defective/
    【新功能 2】：标记残次品并支持一键解绑与新合格品条码替换
    Body (JSON):
      {
        "product_id": 1,
        "defect_reason": "泡棉贴附偏移 / 外观划痕",
        "replacement_code": "P-NEW-0001", # 可选替换条码
        "rack_code": "RACK-001"
      }
    """
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '无效的 JSON'}, status=400)

    product_id = body.get('product_id') or body.get('product_code')
    defect_reason = body.get('defect_reason', '残次品人工剔除')
    replacement_code = body.get('replacement_code')
    rack_code = body.get('rack_code')

    if not product_id:
        return JsonResponse({'success': False, 'error': '请指定要处理的产品 ID 或产品条码'}, status=400)

    try:
        svc = ProductionService()
        res = svc.mark_product_defective(
            product_id,
            defect_reason=defect_reason,
            replacement_code=replacement_code,
            rack_code=rack_code,
        )
        return JsonResponse({
            'success': True,
            'message': res['message'],
            'defective_product_id': res['defective_product'].pk,
            'defective_code': res['defective_product'].product_code,
            'replacement_code': res['replacement_product'].product_code if res['replacement_product'] else None,
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'处理残次品失败: {exc}'}, status=500)

