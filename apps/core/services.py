"""跨 app 共享的只读汇总服务。

注意：本模块只做读取与聚合，不承载具体业务流程，避免变成杂物模块。
"""
from datetime import timedelta

from django.utils import timezone

from apps.core.constants import (
    AlarmStatus,
    DeviceStatus,
    DeviceType,
    MesUploadStatus,
    TERMINAL_STATES,
    WorkflowState,
)


WORKFLOW_ORDER = [value for value, _label in WorkflowState.choices]


def _stage_cards(current_state, demo_mode=False):
    """将旧流程状态压缩为与 DB100 一致的六个操作员步骤。"""
    if demo_mode:
        states = ['done', 'done', 'done', 'done', 'active', 'pending']
    else:
        current_index = WORKFLOW_ORDER.index(current_state) if current_state in WORKFLOW_ORDER else 0
        boundaries = [
            WORKFLOW_ORDER.index(WorkflowState.BARCODE_READ),
            WORKFLOW_ORDER.index(WorkflowState.RECIPE_LOADED),
            WORKFLOW_ORDER.index(WorkflowState.RACK_LOCATED),
            WORKFLOW_ORDER.index(WorkflowState.RECIPE_VERIFIED),
            WORKFLOW_ORDER.index(WorkflowState.FOAM_INSPECTING),
            WORKFLOW_ORDER.index(WorkflowState.COMPLETED),
        ]
        states = []
        previous = -1
        for boundary in boundaries:
            if current_index > boundary:
                states.append('done')
            elif previous < current_index <= boundary:
                states.append('active')
            else:
                states.append('pending')
            previous = boundary
        if current_state == WorkflowState.COMPLETED:
            states = ['done'] * 6

    content = [
        ('01', '产品条码', 'DBX24 → DBX25/26'),
        ('02', '料框配方', 'DBX50 → DBX51/52'),
        ('03', '3D 定位', 'DBX56 → DBD60 / DBX57/58'),
        ('04', '配方核对', 'DBX53 → DBX54/55'),
        ('05', '泡棉检测', 'DBX64/65 → DBX66'),
        ('06', 'MES 上传', 'DBX67 → DBX68/69'),
    ]
    return [
        {'number': number, 'name': name, 'description': description, 'status': status}
        for (number, name, description), status in zip(content, states)
    ]


def _station_stage_cards(phase, resume_phase=''):
    from apps.workflow.models import StationPhase

    groups = [
        {StationPhase.WAIT_PRODUCT, StationPhase.WAIT_MARK_RESET},
        {StationPhase.WAIT_RACK, StationPhase.WAIT_RACK_RESET},
        {StationPhase.WAIT_POSITION, StationPhase.WAIT_POSITION_RESET},
        {StationPhase.WAIT_RECIPE_VERIFY, StationPhase.WAIT_RECIPE_RESET},
        {StationPhase.WAIT_FOAM, StationPhase.WAIT_FOAM_RESET},
        {StationPhase.WAIT_BOXING, StationPhase.WAIT_BOXING_RESET},
    ]
    effective_phase = resume_phase if phase == StationPhase.LOCKED and resume_phase else phase
    active_index = next(
        (index for index, values in enumerate(groups) if effective_phase in values), 3,
    )
    if phase == StationPhase.COMPLETED:
        states = ['done'] * 6
    else:
        states = [
            'done' if index < active_index else (
                'active' if index == active_index else 'pending'
            )
            for index in range(6)
        ]
    content = [
        ('01', '产品条码', 'DBX24 → DBX25/26'),
        ('02', '料框配方', 'DBX50 → DBX51/52'),
        ('03', '3D 定位', 'DBX56 → DBD60 / DBX57/58'),
        ('04', '配方核对', 'DBX53 → DBX54/55'),
        ('05', '泡棉检测', 'DBX64/65 → DBX66'),
        ('06', 'MES 上传', 'DBX67 → DBX68/69'),
    ]
    return [
        {'number': number, 'name': name, 'description': description, 'status': status}
        for (number, name, description), status in zip(content, states)
    ]


class DashboardService:
    """首页总览数据。聚合产品、流程、报警、设备等信息。"""

    def get_summary(self):
        from apps.alarms.models import Alarm
        from apps.devices.models import Device
        from apps.mes.models import MesRecord
        from apps.production.models import Product
        from apps.workflow.models import StationCycle, StationPhase, WorkflowInstance

        station_cycle = (
            StationCycle.objects
            .exclude(phase=StationPhase.COMPLETED)
            .select_related('rack__current_recipe', 'workflow__product__rack__current_recipe')
            .order_by('-created_at').first()
        )

        # 当前活动流程：取最近更新且未结束的流程实例。
        active = (
            WorkflowInstance.objects
            .exclude(current_state__in=list(TERMINAL_STATES))
            .select_related('product', 'product__rack', 'product__rack__current_recipe')
            .order_by('-updated_at')
            .first()
        ) if station_cycle is None else station_cycle.workflow

        current_product = None
        current_rack = None
        current_recipe = None
        workflow_state_label = '未启动'
        is_locked = False
        current_state = WorkflowState.CREATED
        if active:
            current_product = active.product.product_code
            if active.product.rack_id:
                current_rack = active.product.rack.rack_code
                if active.product.rack.current_recipe_id:
                    current_recipe = active.product.rack.current_recipe.recipe_code
            workflow_state_label = WorkflowState(active.current_state).label
            is_locked = active.is_locked
            current_state = active.current_state

        if station_cycle is not None:
            workflow_state_label = station_cycle.get_phase_display()
            is_locked = station_cycle.is_locked
            if station_cycle.rack_id:
                current_rack = station_cycle.rack.rack_code
                if station_cycle.rack.current_recipe_id:
                    current_recipe = station_cycle.rack.current_recipe.recipe_code

        # 演示库中的 P-DEMO 流程用于展示整改后的运行界面；接入现场数据后自动使用真实值。
        demo_mode = station_cycle is None and (not active or (current_product or '').startswith('P-DEMO'))
        if demo_mode:
            current_product = current_product or 'P-20260814-0008'
            current_rack = current_rack or 'RACK-A-20260814-01'
            current_recipe = current_recipe or 'BUMPER-A-04'
            workflow_state_label = '视觉装箱中'

        loaded_quantity = 0
        planned_quantity = 24
        if active and active.product.rack_id:
            loaded_quantity = Product.objects.filter(rack=active.product.rack).count()
            if active.product.rack.current_recipe_id:
                planned_quantity = active.product.rack.current_recipe.total_quantity or 24
        if station_cycle is not None:
            loaded_quantity = station_cycle.loaded_quantity
            planned_quantity = station_cycle.planned_quantity or planned_quantity
        if demo_mode:
            loaded_quantity = 12

        quantity_per_layer = 6
        layer_count = 4
        if active and active.product.rack_id and active.product.rack.current_recipe_id:
            quantity_per_layer = active.product.rack.current_recipe.quantity_per_layer or quantity_per_layer
            layer_count = active.product.rack.current_recipe.layer_count or layer_count

        # 首页只展示操作员需要理解的工位占位，不在这里复制业务状态机。
        display_capacity = min(max(planned_quantity, 1), 48)
        rack_slots = []
        for slot_number in range(1, display_capacity + 1):
            rack_slots.append({
                'number': slot_number,
                'layer': (slot_number - 1) // max(1, quantity_per_layer) + 1,
                'position': (slot_number - 1) % max(1, quantity_per_layer) + 1,
                'status': (
                    'loaded' if slot_number <= loaded_quantity
                    else 'current' if slot_number == loaded_quantity + 1
                    else 'pending'
                ),
            })

        phase_signal_map = {
            StationPhase.WAIT_PRODUCT: ('DBX24.0', '等待打标完成触发', '读取 DBB2 产品条码'),
            StationPhase.WAIT_MARK_RESET: ('DBX24.0', '等待 PLC 清除打标触发', 'DBX25.0 保持确认'),
            StationPhase.WAIT_RACK: ('DBX50.0', '等待料框到位触发', '读取 DBB28 料框码'),
            StationPhase.WAIT_RACK_RESET: ('DBX50.0', '等待 PLC 清除料框触发', 'DBX51/52 保持确认'),
            StationPhase.WAIT_POSITION: ('DBX56.0', '等待 3D 定位触发', 'ΔZ 写入 DBD60'),
            StationPhase.WAIT_POSITION_RESET: ('DBX56.0', '等待 PLC 清除定位触发', 'DBX57/58 保持确认'),
            StationPhase.WAIT_RECIPE_VERIFY: ('DBX53.0', '等待配方校验触发', '结果写入 DBX54/55'),
            StationPhase.WAIT_RECIPE_RESET: ('DBX53.0', '等待 PLC 清除校验触发', 'DBX54 保持确认'),
            StationPhase.WAIT_FOAM: ('DBX64.0', '等待泡棉结果记录触发', '读取 DBX65，确认写入 DBX66'),
            StationPhase.WAIT_FOAM_RESET: ('DBX64.0', '等待 PLC 清除泡棉触发', 'DBX66 保持确认'),
            StationPhase.WAIT_BOXING: ('DBX67.0', '等待装箱完成触发', '结果写入 DBX68/69'),
            StationPhase.WAIT_BOXING_RESET: ('DBX67.0', '等待 PLC 清除上传触发', 'DBX68 保持确认'),
            StationPhase.COMPLETED: ('DBX67.0', '料框装箱已完成', '等待下一料框'),
            StationPhase.LOCKED: ('DBX70.0', '工位已锁定', '处理报警后人工解锁'),
        }
        if station_cycle is not None:
            signal_code, wait_label, signal_hint = phase_signal_map.get(
                StationPhase(station_cycle.phase), ('—', workflow_state_label, '等待状态更新')
            )
        elif demo_mode:
            signal_code, wait_label, signal_hint = (
                'DBX64.0', '等待泡棉结果记录触发', '读取 DBX65，确认写入 DBX66'
            )
        else:
            signal_code, wait_label, signal_hint = ('DBX50.0', '等待料框到位触发', '读取 DBB28 料框码')

        if planned_quantity and loaded_quantity >= planned_quantity:
            current_layer = layer_count
            current_position = quantity_per_layer
        else:
            current_layer = min(layer_count, loaded_quantity // max(1, quantity_per_layer) + 1)
            current_position = loaded_quantity % max(1, quantity_per_layer) + 1

        recent_events = []
        if active and not demo_mode:
            recent_events = [
                {
                    'display_time': (event.occurred_at or event.created_at).strftime('%H:%M:%S'),
                    'source': event.get_source_display(),
                    'event': event.event_type,
                    'message': event.message or '-',
                    'success': event.success,
                }
                for event in active.events.order_by('-created_at')[:6]
            ]
        if demo_mode:
            now = timezone.localtime()
            recent_events = [
                {'display_time': (now - timedelta(seconds=4)).strftime('%H:%M:%S'), 'source': '视觉', 'event': 'RACK_LOCATED', 'message': '料架定位完成，补偿数据已写入 PLC', 'success': True},
                {'display_time': (now - timedelta(seconds=18)).strftime('%H:%M:%S'), 'source': 'MES', 'event': 'RECIPE_LOADED', 'message': '装箱配方 BUMPER-A-04 获取成功', 'success': True},
                {'display_time': (now - timedelta(seconds=25)).strftime('%H:%M:%S'), 'source': 'PLC', 'event': 'RACK_SCAN', 'message': '料框码 RACK-A-20260814-01 读取完成', 'success': True},
                {'display_time': (now - timedelta(seconds=52)).strftime('%H:%M:%S'), 'source': 'PLC', 'event': 'HANDOVER', 'message': '机器人交接完成，真空确认正常', 'success': True},
                {'display_time': (now - timedelta(seconds=74)).strftime('%H:%M:%S'), 'source': 'PLC', 'event': 'BARCODE_READ', 'message': f'产品码 {current_product} 校验通过', 'success': True},
            ]

        today = timezone.localdate()
        today_products = Product.objects.filter(created_at__date=today)
        today_total = today_products.count()
        today_completed = today_products.filter(current_state=WorkflowState.COMPLETED).count()
        today_failed = today_products.filter(
            current_state__in=[WorkflowState.FAILED, WorkflowState.LOCKED]
        ).count()
        if demo_mode:
            today_total = 126
            today_completed = 125
            today_failed = 1

        open_alarms = Alarm.objects.exclude(status=AlarmStatus.CLOSED)
        recent_alarms = list(
            open_alarms.order_by('-created_at')[:5]
        )
        primary_alarm = recent_alarms[0] if recent_alarms else None

        devices = list(Device.objects.all())
        online = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
        plc = next((device for device in devices if device.device_type == DeviceType.PLC), None)
        plc_recent = bool(
            plc
            and plc.status == DeviceStatus.ONLINE
            and plc.last_seen_at
            and timezone.now() - plc.last_seen_at <= timedelta(seconds=10)
        )

        latest_mes = MesRecord.objects.order_by('-created_at').first()
        mes_status = '待机'
        mes_status_tone = 'muted'
        if demo_mode:
            mes_status = '连接正常'
            mes_status_tone = 'ok'
        elif latest_mes:
            mes_status = '最近请求成功' if latest_mes.success else '最近请求失败'
            mes_status_tone = 'ok' if latest_mes.success else 'fail'

        return {
            'demo_mode': demo_mode,
            'current_product': current_product,
            'current_rack': current_rack,
            'current_recipe': current_recipe,
            'workflow_state': workflow_state_label,
            'is_locked': is_locked,
            'stage_cards': (
                _station_stage_cards(station_cycle.phase, station_cycle.resume_phase)
                if station_cycle is not None else _stage_cards(current_state, demo_mode=demo_mode)
            ),
            'line_mode': '自动运行',
            'shift_name': '白班 08:00—20:00',
            'cycle_time': '32.5',
            'loaded_quantity': loaded_quantity,
            'planned_quantity': planned_quantity,
            'quantity_per_layer': quantity_per_layer,
            'layer_count': layer_count,
            'rack_slots': rack_slots,
            'rack_columns': min(max(quantity_per_layer, 1), 12),
            'signal_code': signal_code,
            'wait_label': wait_label,
            'signal_hint': signal_hint,
            'data_timestamp': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S'),
            'progress_percent': min(100, round(loaded_quantity / planned_quantity * 100)) if planned_quantity else 0,
            'current_layer': current_layer,
            'current_position': current_position,
            'binding_status': '已绑定' if current_rack else '等待料框码',
            'mes_upload_label': (
                '已上传' if active and active.product.mes_upload_status == MesUploadStatus.UPLOADED
                else '等待装箱完成'
            ),
            'recent_events': recent_events,
            'open_alarm_count': open_alarms.count(),
            'recent_alarms': recent_alarms,
            'primary_alarm': primary_alarm,
            'device_total': len(devices),
            'device_online': online,
            'device_status': f'{online}/{len(devices)} 在线' if devices else '无设备',
            'plc_status': '通信正常' if demo_mode or plc_recent else ('未配置' if not plc else '离线'),
            'plc_status_tone': 'ok' if demo_mode or plc_recent else ('muted' if not plc else 'fail'),
            'plc_last_seen': '刚刚' if demo_mode else (
                timezone.localtime(plc.last_seen_at).strftime('%H:%M:%S') if plc and plc.last_seen_at else '-'
            ),
            'mes_status': mes_status,
            'mes_status_tone': mes_status_tone,
            'mes_pending_count': 1 if demo_mode else 0,
            'today_total': today_total,
            'today_completed': today_completed,
            'today_failed': today_failed,
        }
