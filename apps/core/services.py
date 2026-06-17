"""跨 app 共享的只读汇总服务。

注意：本模块只做读取与聚合，不承载具体业务流程，避免变成杂物模块。
"""
from django.utils import timezone

from apps.core.constants import AlarmStatus, TERMINAL_STATES, WorkflowState


class DashboardService:
    """首页总览数据。聚合产品、流程、报警、设备等信息。"""

    def get_summary(self):
        from apps.alarms.models import Alarm
        from apps.devices.models import Device
        from apps.production.models import Product
        from apps.workflow.models import WorkflowInstance
        from apps.core.constants import DeviceStatus

        # 当前活动流程：取最近更新且未结束的流程实例。
        active = (
            WorkflowInstance.objects
            .exclude(current_state__in=list(TERMINAL_STATES))
            .select_related('product', 'product__rack')
            .order_by('-updated_at')
            .first()
        )

        current_product = None
        current_rack = None
        workflow_state_label = '未启动'
        is_locked = False
        if active:
            current_product = active.product.product_code
            if active.product.rack_id:
                current_rack = active.product.rack.rack_code
            workflow_state_label = WorkflowState(active.current_state).label
            is_locked = active.is_locked

        today = timezone.localdate()
        today_products = Product.objects.filter(created_at__date=today)
        today_total = today_products.count()
        today_completed = today_products.filter(current_state=WorkflowState.COMPLETED).count()
        today_failed = today_products.filter(
            current_state__in=[WorkflowState.FAILED, WorkflowState.LOCKED]
        ).count()

        open_alarms = Alarm.objects.exclude(status=AlarmStatus.CLOSED)
        recent_alarms = list(
            open_alarms.order_by('-created_at')[:5]
        )

        devices = list(Device.objects.all())
        online = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)

        return {
            'current_product': current_product,
            'current_rack': current_rack,
            'workflow_state': workflow_state_label,
            'is_locked': is_locked,
            'open_alarm_count': open_alarms.count(),
            'recent_alarms': recent_alarms,
            'device_total': len(devices),
            'device_online': online,
            'device_status': f'{online}/{len(devices)} 在线' if devices else '无设备',
            'today_total': today_total,
            'today_completed': today_completed,
            'today_failed': today_failed,
        }
