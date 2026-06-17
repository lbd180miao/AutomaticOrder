"""流程编排服务。

职责：管理单件产品主流程状态，串联 devices / vision / mes / alarms 服务。
这里不写 PLC 协议、不写 OpenCV 算法，只调用清晰的服务接口。
所有状态变化都会写入 WorkflowEvent；失败时创建报警；LOCKED 仅人工解除。
"""
from django.db import transaction
from django.utils import timezone

from apps.alarms.services import AlarmService
from apps.core.constants import (
    AlarmLevel, AlarmSource, EventSource, MarkStatus, MesUploadStatus,
    STATE_STAGE_MAP, Stage, TERMINAL_STATES, WorkflowState as W,
)
from apps.core.exceptions import (
    AutomaticOrderError, WorkflowLockedError, WorkflowTransitionError,
)
from apps.devices.services import DeviceService
from apps.mes.services import MesService
from apps.production.services import ProductionService
from apps.vision.services import VisionService
from .models import WorkflowEvent, WorkflowInstance
from .state_machine import WorkflowStateMachine


class WorkflowService:
    """Orchestrates product workflow state with device, vision, MES, and alarms."""

    def __init__(self, *, device_service=None, mes_service=None,
                 vision_service=None, alarm_service=None, production_service=None):
        self.machine = WorkflowStateMachine()
        self.devices = device_service or DeviceService()
        self.mes = mes_service or MesService()
        self.vision = vision_service or VisionService()
        self.alarms = alarm_service or AlarmService()
        self.production = production_service or ProductionService()

    # ----- 流程创建 -----
    @transaction.atomic
    def start(self, product_code, batch=None):
        """创建产品与流程实例，进入 CREATED。"""
        product = self.production.create_product(product_code, batch=batch)
        workflow, created = WorkflowInstance.objects.get_or_create(
            product=product,
            defaults={
                'current_state': W.CREATED,
                'current_stage': Stage.STAGE_ONE,
                'started_at': timezone.now(),
            },
        )
        if created:
            self._log(workflow, 'START', '', W.CREATED, EventSource.OPERATOR,
                      message='流程已创建')
        return workflow

    # ----- 通用转换 -----
    @transaction.atomic
    def _transition(self, workflow, to_state, source, *, event_type='ADVANCE',
                    payload=None, message='', success=True):
        from_state = workflow.current_state
        if not self.machine.can_transition(from_state, to_state):
            raise WorkflowTransitionError(
                f'非法状态转换：{from_state} -> {to_state}'
            )
        workflow.current_state = to_state
        workflow.current_stage = STATE_STAGE_MAP.get(to_state, workflow.current_stage)
        if to_state == W.LOCKED:
            workflow.is_locked = True
        if to_state in TERMINAL_STATES:
            workflow.finished_at = timezone.now()
        workflow.save(update_fields=[
            'current_state', 'current_stage', 'is_locked', 'finished_at', 'updated_at',
        ])
        # 同步产品当前状态。
        product = workflow.product
        product.current_state = to_state
        product.save(update_fields=['current_state', 'updated_at'])

        self._log(workflow, event_type, from_state, to_state, source,
                  payload=payload, message=message, success=success)
        return workflow

    def _log(self, workflow, event_type, from_state, to_state, source,
             *, payload=None, message='', success=True):
        WorkflowEvent.objects.create(
            workflow=workflow,
            event_type=event_type,
            from_state=from_state or '',
            to_state=to_state or '',
            source=source,
            payload=payload or {},
            occurred_at=timezone.now(),
            success=success,
            message=message,
        )

    def _fail(self, workflow, message, *, source=AlarmSource.WORKFLOW,
              level=AlarmLevel.ERROR, lock=True):
        """创建报警并把流程转入 LOCKED。"""
        self.alarms.create(
            source=source, message=message, level=level,
            product=workflow.product, rack=workflow.product.rack,
            workflow=workflow, lock_workstation=lock,
        )
        workflow.last_error = message
        workflow.save(update_fields=['last_error', 'updated_at'])
        self._transition(workflow, W.LOCKED, EventSource.SYSTEM,
                         event_type='ALARM', message=message, success=False)
        return workflow

    # ----- 主推进入口 -----
    def advance(self, workflow):
        """根据当前状态执行下一步动作并推进。供页面“模拟PLC信号”按钮调用。"""
        if workflow.is_locked or workflow.current_state == W.LOCKED:
            raise WorkflowLockedError('流程已锁定，需人工解除后继续')
        if workflow.current_state in TERMINAL_STATES:
            raise WorkflowTransitionError('流程已结束')

        handler = self._handlers().get(workflow.current_state)
        if handler is None:
            # 无特定动作的节点，直接走状态机的下一步。
            nxt = self.machine.next_state(workflow.current_state)
            if nxt is None:
                raise WorkflowTransitionError('无可推进的下一状态')
            return self._transition(workflow, nxt, EventSource.PLC)
        try:
            return handler(workflow)
        except AutomaticOrderError:
            raise
        except Exception as exc:  # noqa: BLE001 - 兜底：任何异常都报警锁定
            return self._fail(workflow, f'流程执行异常：{exc}')

    def _handlers(self):
        # 键为“当前状态”，handler 负责从该状态执行动作并推进到下一状态。
        return {
            W.MARKING_READY: self._on_marked,
            W.MARKED: self._on_barcode_read,
            W.BARCODE_READ: self._on_mes_upload,
            W.INJECTION_RELEASED: self._on_rack_scanned,
            W.RACK_SCANNED: self._on_recipe_loaded,
            W.RECIPE_LOADED: self._on_rack_located,
            W.RACK_LOCATED: self._on_recipe_verified,
            W.FOAM_ATTACHING: self._on_foam_inspecting,
        }

    # ----- 阶段一：打标 -----
    def _on_marked(self, workflow):
        """当前 MARKING_READY -> MARKED：触发打标并查询结果。"""
        product = workflow.product
        self.devices.adapter.trigger_mark(product.product_code)
        result = self.devices.adapter.get_mark_result()
        self.devices.record_signal('LASER-01', 'mark_result', result.get('result', 'NG'))
        if not result.get('success'):
            product.mark_status = MarkStatus.FAILED
            product.save(update_fields=['mark_status', 'updated_at'])
            return self._fail(workflow, '激光打标失败', source=AlarmSource.DEVICE)
        product.mark_status = MarkStatus.MARKED
        product.save(update_fields=['mark_status', 'updated_at'])
        return self._transition(workflow, W.MARKED, EventSource.PLC,
                                event_type='MARK', message='打标完成')

    def _on_barcode_read(self, workflow):
        """MARKED -> BARCODE_READ：扫码枪读取产品条码。"""
        scan = self.devices.adapter.read_product_code()
        self.devices.record_signal('SCAN-01', 'product_code', scan.get('code', ''))
        if not scan.get('success'):
            return self._fail(workflow, '产品条码读取失败', source=AlarmSource.SCANNER)
        return self._transition(workflow, W.BARCODE_READ, EventSource.PLC,
                                event_type='SCAN', payload={'code': scan.get('code')},
                                message='条码已读取')

    def _on_mes_upload(self, workflow):
        """BARCODE_READ -> MES_UPLOADED：上传条码与料框码。"""
        product = workflow.product
        rack_code = product.rack.rack_code if product.rack_id else ''
        resp = self.mes.upload_product_barcode(
            product.product_code, rack_code, product=product, rack=product.rack,
        )
        if not resp.get('success'):
            product.mes_upload_status = MesUploadStatus.FAILED
            product.save(update_fields=['mes_upload_status', 'updated_at'])
            return self._fail(workflow, 'MES 上传条码失败', source=AlarmSource.MES)
        product.mes_upload_status = MesUploadStatus.UPLOADED
        product.save(update_fields=['mes_upload_status', 'updated_at'])
        return self._transition(workflow, W.MES_UPLOADED, EventSource.MES,
                                event_type='MES', message='MES 上传成功')

    # ----- 阶段三：料框扫码与配方 -----
    def _on_rack_scanned(self, workflow):
        """INJECTION_RELEASED -> RACK_SCANNED：读料框码并绑定。"""
        scan = self.devices.adapter.read_rack_code()
        self.devices.record_signal('SCAN-01', 'rack_code', scan.get('code', ''))
        if not scan.get('success'):
            return self._fail(workflow, '料框码读取失败', source=AlarmSource.SCANNER)
        rack = self.production.get_or_create_rack(scan['code'])
        self.production.bind_product_to_rack(workflow.product, rack)
        return self._transition(workflow, W.RACK_SCANNED, EventSource.PLC,
                                event_type='RACK_SCAN', payload={'rack_code': scan['code']},
                                message='料框已扫码并绑定')

    def _on_recipe_loaded(self, workflow):
        """RACK_SCANNED -> RECIPE_LOADED：向 MES 获取配方并落库。"""
        product = workflow.product
        rack = product.rack
        resp = self.mes.get_rack_recipe(rack.rack_code, rack=rack)
        if not resp.get('success'):
            return self._fail(workflow, 'MES 配方获取失败，锁定流程',
                              source=AlarmSource.MES)
        data = resp['recipe']
        recipe = self.production.upsert_recipe(
            data['recipe_code'],
            name=data['name'], rack_type=data['rack_type'],
            layer_count=data['layer_count'], quantity_per_layer=data['quantity_per_layer'],
            total_quantity=data['total_quantity'], layer_height=data['layer_height'],
            layer_spacing=data['layer_spacing'], tolerance_x=data['tolerance_x'],
            tolerance_y=data['tolerance_y'], tolerance_z=data['tolerance_z'],
        )
        self.production.assign_recipe_to_rack(rack, recipe)
        return self._transition(workflow, W.RECIPE_LOADED, EventSource.MES,
                                event_type='RECIPE', payload={'recipe_code': recipe.recipe_code},
                                message='配方已加载')

    # ----- 阶段三：视觉定位与校验 -----
    def _on_rack_located(self, workflow):
        """RECIPE_LOADED -> RACK_LOCATING -> RACK_LOCATED：左右料架定位。"""
        product = workflow.product
        rack = product.rack
        recipe = rack.current_recipe if rack else None
        # 先进入定位中。
        self._transition(workflow, W.RACK_LOCATING, EventSource.VISION,
                         event_type='VISION', message='料架定位中')
        left, right = self.vision.locate_both_racks(product, rack, recipe)
        # 把补偿值通过 PLC 下发（模拟）。
        for res in (left, right):
            self.devices.adapter.send_offsets(
                product.product_code, res.side,
                float(res.offset_x), float(res.offset_y), float(res.offset_z),
            )
        if not (left.is_success and right.is_success):
            return self._fail(workflow, '料架视觉定位失败', source=AlarmSource.VISION)
        return self._transition(workflow, W.RACK_LOCATED, EventSource.VISION,
                                event_type='VISION', message='左右料架定位完成')

    def _on_recipe_verified(self, workflow):
        """RACK_LOCATED -> RECIPE_VERIFIED：层高/层距配方校验。"""
        product = workflow.product
        # 取最近一次定位结果判断配方匹配。
        from apps.vision.models import RackLocationResult
        last = (
            RackLocationResult.objects
            .filter(vision_task__product=product)
            .order_by('-created_at').first()
        )
        if last is not None and not last.is_recipe_matched:
            return self._fail(workflow, '料架配置校验失败（层高/层距超差）',
                              source=AlarmSource.RECIPE)
        return self._transition(workflow, W.RECIPE_VERIFIED, EventSource.VISION,
                                event_type='VERIFY', message='配方校验通过，可装箱')

    # ----- 阶段三：泡棉检测 -----
    def _on_foam_inspecting(self, workflow):
        """FOAM_ATTACHING -> FOAM_INSPECTING -> COMPLETED / LOCKED。"""
        product = workflow.product
        rack = product.rack
        self._transition(workflow, W.FOAM_INSPECTING, EventSource.VISION,
                         event_type='VISION', message='泡棉检测中')
        result = self.vision.inspect_foam(product, rack, position_index=0)
        if not result.is_passed:
            return self._fail(workflow, '泡棉贴附检测不合格，锁定工位',
                              source=AlarmSource.VISION)
        return self._transition(workflow, W.COMPLETED, EventSource.VISION,
                                event_type='COMPLETE', message='工序完成，检测合格')

    # ----- 人工解除锁定 -----
    @transaction.atomic
    def unlock(self, workflow, *, resume=True, operator_note=''):
        """人工解除 LOCKED：resume=True 回到锁定前可继续，否则判失败。"""
        if workflow.current_state != W.LOCKED:
            raise WorkflowTransitionError('当前流程未处于锁定状态')
        # 关闭该流程相关的锁定报警。
        from apps.alarms.models import Alarm
        from apps.core.constants import AlarmStatus
        for alarm in Alarm.objects.filter(workflow=workflow, locked_workstation=True).exclude(status=AlarmStatus.CLOSED):
            self.alarms.close(alarm.id, operator_note=operator_note or '人工解除')

        workflow.is_locked = False
        if resume:
            # 回退到失败前能继续的状态：用产品上一个非锁定状态较复杂，
            # 这里简单恢复到 CREATED 之后的最近正常态记录。
            prev = (
                WorkflowEvent.objects
                .filter(workflow=workflow, success=True)
                .exclude(to_state__in=[W.LOCKED, W.FAILED])
                .order_by('-created_at').first()
            )
            target = prev.to_state if prev else W.CREATED
            workflow.current_state = target
            workflow.current_stage = STATE_STAGE_MAP.get(target, Stage.STAGE_ONE)
            workflow.last_error = ''
            workflow.save(update_fields=[
                'is_locked', 'current_state', 'current_stage', 'last_error', 'updated_at',
            ])
            workflow.product.current_state = target
            workflow.product.save(update_fields=['current_state', 'updated_at'])
            self._log(workflow, 'UNLOCK', W.LOCKED, target, EventSource.OPERATOR,
                      message=operator_note or '人工解除锁定并恢复')
        else:
            workflow.save(update_fields=['is_locked', 'updated_at'])
            self._transition(workflow, W.FAILED, EventSource.OPERATOR,
                             event_type='FAIL', message=operator_note or '人工判定流程失败')
        return workflow
