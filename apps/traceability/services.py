"""追溯服务：按产品条码/料框码/批次聚合各模块数据形成查询视图。

本模块不拥有复杂业务表，主要读取其他模块数据。
"""
from apps.production.models import Product, Rack


class TraceabilityService:
    """Builds read models from product, workflow, vision, MES, and alarm records."""

    def trace_by_product_code(self, product_code):
        try:
            product = (
                Product.objects
                .select_related('batch', 'rack', 'rack__current_recipe')
                .get(product_code=product_code)
            )
        except Product.DoesNotExist:
            return None
        return self._build_product_view(product)

    def trace_by_rack_code(self, rack_code):
        from apps.workflow.models import StationCycle

        try:
            rack = Rack.objects.select_related('current_recipe').get(rack_code=rack_code)
        except Rack.DoesNotExist:
            return None
        products = (
            Product.objects.filter(rack=rack).select_related('batch').order_by('created_at')
        )
        recipe = rack.current_recipe
        layer_count = int(recipe.layer_count) if recipe else 0
        quantity_per_layer = int(recipe.quantity_per_layer) if recipe else 0
        slot_rows = []
        if layer_count and quantity_per_layer:
            for layer_no in range(1, layer_count + 1):
                cells = []
                for slot_no in range(1, quantity_per_layer + 1):
                    global_position = (layer_no - 1) * quantity_per_layer + slot_no
                    cells.append({
                        'layer_no': layer_no,
                        'slot_no': slot_no,
                        'global_position': global_position,
                    })
                slot_rows.append({'layer_no': layer_no, 'cells': cells})
        latest_cycle = (
            StationCycle.objects
            .filter(workflow__product__rack=rack)
            .select_related('workflow__product')
            .order_by('-created_at')
            .first()
        )
        return {
            'rack': rack,
            'recipe': recipe,
            'products': list(products),
            'product_count': products.count(),
            'latest_cycle': latest_cycle,
            'slot_rows': slot_rows,
            'planned_quantity': (
                latest_cycle.planned_quantity
                if latest_cycle and latest_cycle.planned_quantity
                else recipe.total_quantity if recipe else 0
            ),
            # 当前 Product 模型还没有层号/槽位号字段，不能推测绑定位置。
            'position_binding_available': False,
        }

    def _build_product_view(self, product):
        from apps.workflow.models import WorkflowInstance, WorkflowEvent
        from apps.vision.models import RackLocationResult, FoamInspectionResult
        from apps.mes.models import MesRecord
        from apps.alarms.models import Alarm

        workflow = WorkflowInstance.objects.filter(product=product).first()
        events = []
        if workflow:
            events = list(
                WorkflowEvent.objects.filter(workflow=workflow).order_by('created_at')
            )

        rack_results = list(
            RackLocationResult.objects.filter(vision_task__product=product)
            .select_related('vision_task').order_by('created_at')
        )
        foam_results = list(
            FoamInspectionResult.objects.filter(product=product)
            .select_related('vision_task').order_by('position_index')
        )
        mes_records = list(
            MesRecord.objects.filter(product=product).order_by('created_at')
        )
        alarms = list(
            Alarm.objects.filter(product=product).order_by('-created_at')
        )

        return {
            'product': product,
            'batch': product.batch,
            'rack': product.rack,
            'workflow': workflow,
            'events': events,
            'rack_results': rack_results,
            'foam_results': foam_results,
            'mes_records': mes_records,
            'alarms': alarms,
        }
