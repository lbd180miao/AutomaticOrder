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
    """将细粒度状态压缩为操作员能快速识别的四个生产阶段。"""
    if demo_mode:
        states = ['done', 'done', 'active', 'pending']
    else:
        current_index = WORKFLOW_ORDER.index(current_state) if current_state in WORKFLOW_ORDER else 0
        boundaries = [
            WORKFLOW_ORDER.index(WorkflowState.MES_UPLOADED),
            WORKFLOW_ORDER.index(WorkflowState.INJECTION_RELEASED),
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
            states = ['done', 'done', 'done', 'done']

    content = [
        ('01', '产品打标', '产品码读取与校验'),
        ('02', '机器人交接', '双机器人安全交接'),
        ('03', '视觉装箱', '定位、装箱与泡棉检测'),
        ('04', 'MES上传', '绑定关系与装箱结果'),
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
        from apps.workflow.models import WorkflowInstance

        # 当前活动流程：取最近更新且未结束的流程实例。
        active = (
            WorkflowInstance.objects
            .exclude(current_state__in=list(TERMINAL_STATES))
            .select_related('product', 'product__rack', 'product__rack__current_recipe')
            .order_by('-updated_at')
            .first()
        )

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

        # 演示库中的 P-DEMO 流程用于展示整改后的运行界面；接入现场数据后自动使用真实值。
        demo_mode = not active or (current_product or '').startswith('P-DEMO')
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
        if demo_mode:
            loaded_quantity = 12

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
            'stage_cards': _stage_cards(current_state, demo_mode=demo_mode),
            'line_mode': '自动运行',
            'shift_name': '白班 08:00—20:00',
            'cycle_time': '32.5',
            'loaded_quantity': loaded_quantity,
            'planned_quantity': planned_quantity,
            'progress_percent': min(100, round(loaded_quantity / planned_quantity * 100)) if planned_quantity else 0,
            'current_layer': 2 if demo_mode else '-',
            'current_position': 6 if demo_mode else '-',
            'binding_status': '已绑定' if current_rack else '等待料框码',
            'mes_upload_label': (
                '已上传' if active and active.product.mes_upload_status == MesUploadStatus.UPLOADED
                else '等待装箱完成'
            ),
            'recent_events': recent_events,
            'open_alarm_count': open_alarms.count(),
            'recent_alarms': recent_alarms,
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
