"""DB100-driven packing station orchestration.

No PLC protocol details or vision algorithms live here. The service coordinates
existing production/MES/vision/alarm services and persists every handshake phase.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.alarms.services import AlarmService
from apps.core.constants import (
    AlarmLevel, AlarmSource, DeviceType, EventSource, MesUploadStatus,
    STATE_STAGE_MAP, Stage, WorkflowState,
)
from apps.devices.models import Device
from apps.devices.services import DeviceService, get_plc_adapter
from apps.mes.services import MesService
from apps.production.services import ProductionService
from apps.vision.services import VisionService

from .models import StationCycle, StationPhase, WorkflowEvent, WorkflowInstance


class StationStepError(RuntimeError):
    def __init__(self, message, source=AlarmSource.WORKFLOW):
        super().__init__(message)
        self.source = source


class ExistingVisionGateway:
    """Thin integration adapter around the existing vision modules."""

    def __init__(self, service=None):
        self.service = service or VisionService()
        self.simulated = getattr(settings, 'AUTOMATIC_ORDER', {}).get(
            'USE_SIMULATED_DEVICES', True,
        )

    def calculate_position_matrix(self, cycle):
        if self.simulated:
            return [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]

        from apps.vision.models import RackLocationRecipe
        from apps.vision.rack_3d.services import RackPositioningService

        conf = getattr(settings, 'AUTOMATIC_ORDER', {})
        recipe_id = conf.get('VISION_POSITION_RECIPE_ID')
        qs = RackLocationRecipe.objects.filter(enabled=True)
        rack = cycle.product.rack
        if recipe_id:
            recipe = qs.filter(pk=recipe_id).first()
        else:
            recipe = qs.filter(rack_type=rack.rack_type).order_by('layer_no').first()
            recipe = recipe or qs.order_by('position_no', 'layer_no').first()
        if recipe is None:
            raise StationStepError('未找到可用的 3D 定位配方', AlarmSource.RECIPE)
        result = RackPositioningService().execute_positioning(
            recipe.id, recipe.layer_no, save=True,
        )
        if not result.get('is_success'):
            raise StationStepError(
                result.get('error_message') or '3D 定位失败', AlarmSource.VISION,
            )
        return result['compensation_matrix']

    def measure_recipe(self, cycle):
        recipe = cycle.product.rack.current_recipe
        if self.simulated:
            return float(recipe.layer_height), float(recipe.layer_spacing)
        from django.utils.module_loading import import_string

        callable_path = getattr(settings, 'AUTOMATIC_ORDER', {}).get(
            'RECIPE_MEASUREMENT_CALLABLE', '',
        )
        if not callable_path:
            raise StationStepError(
                '真实模式未配置 2D 层高层距测量适配器 '
                '(RECIPE_MEASUREMENT_CALLABLE)',
                AlarmSource.RECIPE,
            )
        try:
            measurement = import_string(callable_path)(
                product=cycle.product, rack=cycle.product.rack, recipe=recipe,
            )
        except StationStepError:
            raise
        except Exception as exc:
            raise StationStepError(f'2D 料架测量失败：{exc}', AlarmSource.VISION) from exc
        if isinstance(measurement, dict):
            height = measurement['measured_layer_height']
            spacing = measurement['measured_layer_spacing']
        else:
            height, spacing = measurement
        return float(height), float(spacing)

    def inspect_foam(self, cycle):
        result = self.service.inspect_foam(
            cycle.product,
            cycle.product.rack,
            position_index=cycle.loaded_quantity,
            use_camera=not self.simulated,
        )
        return bool(result.is_passed), result


class StationWorkflowService:
    OUTPUTS = (
        'mark_read_done', 'rack_done', 'boxing_allowed', 'recipe_verify_done',
        'position_done', 'foam_passed', 'foam_done', 'mes_upload_success',
        'mes_upload_done', 'workstation_locked',
    )

    def __init__(self, *, plc=None, mes_service=None, vision_gateway=None,
                 alarm_service=None, production_service=None, device_service=None):
        self.plc = plc or get_plc_adapter()
        self.mes = mes_service or MesService()
        self.vision = vision_gateway or ExistingVisionGateway()
        self.alarms = alarm_service or AlarmService()
        self.production = production_service or ProductionService()
        self.devices = device_service or DeviceService(adapter=self.plc)
        plc_device = Device.objects.filter(
            device_type=DeviceType.PLC, enabled=True,
        ).order_by('code').first()
        self.plc_device_code = plc_device.code if plc_device else 'PLC-01'

    def active_cycle(self):
        return (
            StationCycle.objects
            .exclude(phase=StationPhase.COMPLETED)
            .select_related(
                'workflow__product__rack__current_recipe',
            )
            .order_by('-created_at')
            .first()
        )

    def _ensure_cycle(self):
        cycle = self.active_cycle()
        if cycle is not None:
            return cycle
        for output in self.OUTPUTS:
            self.plc.write_point(output, False)
        return StationCycle.objects.create(
            phase=StationPhase.WAIT_PRODUCT,
            started_at=timezone.now(),
        )

    def poll_once(self):
        """Process at most one phase transition from the current DB100 snapshot."""
        heartbeat = self.plc.tick_heartbeat()
        snapshot = self.plc.read_snapshot()
        cycle = self._ensure_cycle()
        self.devices.record_signal(
            self.plc_device_code, 'heartbeat', heartbeat, direction='OUT',
            raw_payload={'db': 100, 'offset': 0},
        )
        if cycle.phase == StationPhase.LOCKED:
            if not snapshot.get('workstation_locked', True):
                self.plc.write_point('workstation_locked', True)
            return cycle, False

        cycle.loaded_quantity = max(0, int(snapshot.get('loaded_quantity', 0)))
        cycle.save(update_fields=['loaded_quantity', 'updated_at'])
        try:
            changed = self._dispatch(cycle, snapshot)
        except StationStepError as exc:
            self._lock(cycle, str(exc), exc.source)
            changed = True
        except Exception as exc:  # keep unexpected integration failures visible
            self._lock(cycle, f'工位流程异常：{exc}', AlarmSource.WORKFLOW)
            changed = True
        return cycle, changed

    def _dispatch(self, cycle, snapshot):
        handlers = {
            StationPhase.WAIT_PRODUCT: self._product_trigger,
            StationPhase.WAIT_MARK_RESET: self._mark_reset,
            StationPhase.WAIT_RACK: self._rack_trigger,
            StationPhase.WAIT_RACK_RESET: self._rack_reset,
            StationPhase.WAIT_POSITION: self._position_trigger,
            StationPhase.WAIT_POSITION_RESET: self._position_reset,
            StationPhase.WAIT_RECIPE_VERIFY: self._recipe_trigger,
            StationPhase.WAIT_RECIPE_RESET: self._recipe_reset,
            StationPhase.WAIT_FOAM: self._foam_trigger,
            StationPhase.WAIT_FOAM_RESET: self._foam_reset,
            StationPhase.WAIT_BOXING: self._boxing_trigger,
            StationPhase.WAIT_BOXING_RESET: self._boxing_reset,
        }
        handler = handlers.get(cycle.phase)
        return bool(handler and handler(cycle, snapshot))

    def _set_phase(self, cycle, phase, *, event_type='', source=EventSource.SYSTEM,
                   message='', payload=None, workflow_state=None):
        old = cycle.phase
        cycle.phase = phase
        cycle.save(update_fields=['phase', 'updated_at'])
        if workflow_state and cycle.workflow_id:
            workflow = cycle.workflow
            workflow.current_state = workflow_state
            workflow.current_stage = STATE_STAGE_MAP.get(
                workflow_state, workflow.current_stage,
            )
            workflow.is_locked = workflow_state == WorkflowState.LOCKED
            if workflow_state == WorkflowState.COMPLETED:
                workflow.finished_at = timezone.now()
            workflow.save(update_fields=[
                'current_state', 'current_stage', 'is_locked', 'finished_at', 'updated_at',
            ])
            workflow.product.current_state = workflow_state
            workflow.product.save(update_fields=['current_state', 'updated_at'])
        if cycle.workflow_id and event_type:
            WorkflowEvent.objects.create(
                workflow=cycle.workflow, event_type=event_type,
                from_state=old, to_state=phase, source=source,
                payload=payload or {}, occurred_at=timezone.now(),
                success=True, message=message,
            )

    def _record_input(self, name, value, offset):
        self.devices.record_signal(
            self.plc_device_code, name, value, raw_payload={'db': 100, 'offset': offset},
        )

    def _write(self, name, value, offset):
        self.plc.write_point(name, value)
        self.devices.record_signal(
            self.plc_device_code, name, int(bool(value)), direction='OUT',
            raw_payload={'db': 100, 'offset': offset},
        )

    def _product_trigger(self, cycle, snapshot):
        if not snapshot.get('mark_trigger'):
            return False
        from apps.devices.plc_db100 import validate_barcode

        code = validate_barcode(snapshot.get('product_barcode'), '产品条码')
        product = self.production.create_product(code)
        workflow, created = WorkflowInstance.objects.get_or_create(
            product=product,
            defaults={
                'current_state': WorkflowState.BARCODE_READ,
                'current_stage': Stage.STAGE_ONE,
                'started_at': timezone.now(),
            },
        )
        if not created and workflow.current_state != WorkflowState.CREATED:
            raise StationStepError(f'产品条码 {code} 已存在进行中或已完成流程', AlarmSource.SCANNER)
        cycle.workflow = workflow
        cycle.save(update_fields=['workflow', 'updated_at'])
        self._record_input('product_barcode', code, 2)
        self._write('mark_read_done', True, 25)
        self._set_phase(
            cycle, StationPhase.WAIT_MARK_RESET, event_type='PRODUCT_BARCODE_READ',
            source=EventSource.PLC, message=f'产品条码 {code} 校验并落库',
            payload={'product_code': code}, workflow_state=WorkflowState.BARCODE_READ,
        )
        return True

    def _mark_reset(self, cycle, snapshot):
        if snapshot.get('mark_trigger'):
            return False
        self._write('mark_read_done', False, 25)
        self._set_phase(cycle, StationPhase.WAIT_RACK)
        return True

    def _rack_trigger(self, cycle, snapshot):
        if not snapshot.get('rack_trigger'):
            return False
        from apps.devices.plc_db100 import validate_barcode

        rack_code = validate_barcode(snapshot.get('rack_barcode'), '料框码')
        rack = self.production.get_or_create_rack(rack_code)
        recipe_response = self.mes.get_rack_recipe(rack_code, rack=rack)
        if not recipe_response.get('success'):
            raise StationStepError('MES 装箱配方查询失败', AlarmSource.MES)
        data = recipe_response.get('recipe') or {}
        required = {
            'recipe_code', 'name', 'rack_type', 'layer_count',
            'quantity_per_layer', 'total_quantity', 'layer_height', 'layer_spacing',
        }
        missing = sorted(required - data.keys())
        if missing:
            raise StationStepError(f'MES 配方缺少字段: {missing}', AlarmSource.MES)
        recipe = self.production.upsert_recipe(
            data['recipe_code'],
            name=data['name'], rack_type=data['rack_type'],
            layer_count=data['layer_count'],
            quantity_per_layer=data['quantity_per_layer'],
            total_quantity=data['total_quantity'],
            layer_height=data['layer_height'], layer_spacing=data['layer_spacing'],
            tolerance_x=data.get('tolerance_x', 0),
            tolerance_y=data.get('tolerance_y', 0),
            tolerance_z=data.get('tolerance_z', 0),
        )
        self.production.assign_recipe_to_rack(rack, recipe)
        self.production.bind_product_to_rack(cycle.product, rack)
        upload = self.mes.upload_product_barcode(
            cycle.product.product_code, rack_code,
            product=cycle.product, rack=rack,
        )
        if not upload.get('success'):
            raise StationStepError('MES 产品码与料框码绑定上传失败', AlarmSource.MES)
        cycle.product.mes_upload_status = MesUploadStatus.UPLOADED
        cycle.product.save(update_fields=['mes_upload_status', 'updated_at'])
        cycle.planned_quantity = int(recipe.total_quantity)
        cycle.save(update_fields=['planned_quantity', 'updated_at'])
        self._record_input('rack_barcode', rack_code, 26)
        self._write('rack_done', True, 49)
        self._set_phase(
            cycle, StationPhase.WAIT_RACK_RESET, event_type='RACK_RECIPE_BOUND',
            source=EventSource.MES, message='料框配方已落库，产品与料框已绑定上传',
            payload={'rack_code': rack_code, 'recipe_code': recipe.recipe_code},
            workflow_state=WorkflowState.RECIPE_LOADED,
        )
        return True

    def _rack_reset(self, cycle, snapshot):
        if snapshot.get('rack_trigger'):
            return False
        self._write('rack_done', False, 49)
        self._set_phase(cycle, StationPhase.WAIT_POSITION)
        return True

    def _position_trigger(self, cycle, snapshot):
        if not snapshot.get('position_trigger'):
            return False
        matrix = self.vision.calculate_position_matrix(cycle)
        self.plc.write_matrix(matrix)
        cycle.positioning_matrix = matrix
        cycle.save(update_fields=['positioning_matrix', 'updated_at'])
        self._write('position_done', True, 119)
        self._set_phase(
            cycle, StationPhase.WAIT_POSITION_RESET, event_type='POSITIONED',
            source=EventSource.VISION, message='4x4 定位矩阵已写入 DB100[54:118]',
            payload={'matrix': matrix}, workflow_state=WorkflowState.RACK_LOCATED,
        )
        return True

    def _position_reset(self, cycle, snapshot):
        if snapshot.get('position_trigger'):
            return False
        self._write('position_done', False, 119)
        self._set_phase(cycle, StationPhase.WAIT_RECIPE_VERIFY)
        return True

    def _recipe_trigger(self, cycle, snapshot):
        if not snapshot.get('recipe_verify_trigger'):
            return False
        height, spacing = self.vision.measure_recipe(cycle)
        recipe = cycle.product.rack.current_recipe
        tolerance = Decimal(str(recipe.tolerance_z))
        height_ok = abs(Decimal(str(height)) - recipe.layer_height) <= tolerance
        spacing_ok = abs(Decimal(str(spacing)) - recipe.layer_spacing) <= tolerance
        passed = bool(height_ok and spacing_ok)
        cycle.measured_layer_height = Decimal(str(height))
        cycle.measured_layer_spacing = Decimal(str(spacing))
        cycle.recipe_verified = passed
        cycle.save(update_fields=[
            'measured_layer_height', 'measured_layer_spacing',
            'recipe_verified', 'updated_at',
        ])
        self._write('boxing_allowed', passed, 51)
        self._write('recipe_verify_done', True, 52)
        if not passed:
            raise StationStepError(
                f'配方校验不通过：层高 {height:.3f}/{recipe.layer_height}，'
                f'层距 {spacing:.3f}/{recipe.layer_spacing}，容差 ±{tolerance}',
                AlarmSource.RECIPE,
            )
        self._set_phase(
            cycle, StationPhase.WAIT_RECIPE_RESET, event_type='RECIPE_VERIFIED',
            source=EventSource.VISION, message='实测层高层距在 MES 配方容差内',
            payload={'layer_height': height, 'layer_spacing': spacing},
            workflow_state=WorkflowState.RECIPE_VERIFIED,
        )
        return True

    def _recipe_reset(self, cycle, snapshot):
        if snapshot.get('recipe_verify_trigger'):
            return False
        self._write('boxing_allowed', False, 51)
        self._write('recipe_verify_done', False, 52)
        if cycle.recipe_verified is False:
            cycle.recipe_verified = None
            cycle.save(update_fields=['recipe_verified', 'updated_at'])
            self._set_phase(cycle, StationPhase.WAIT_RECIPE_VERIFY)
        else:
            self._set_phase(cycle, StationPhase.WAIT_FOAM)
        return True

    def _foam_trigger(self, cycle, snapshot):
        if not snapshot.get('foam_trigger'):
            return False
        passed, result = self.vision.inspect_foam(cycle)
        cycle.foam_passed = passed
        cycle.save(update_fields=['foam_passed', 'updated_at'])
        self._write('foam_passed', passed, 121)
        self._write('foam_done', True, 122)
        if not passed:
            raise StationStepError('泡棉检测不合格，工位已锁定', AlarmSource.VISION)
        self._set_phase(
            cycle, StationPhase.WAIT_FOAM_RESET, event_type='FOAM_INSPECTED',
            source=EventSource.VISION, message='泡棉检测合格',
            payload={'position_index': cycle.loaded_quantity, 'result_id': getattr(result, 'pk', None)},
            workflow_state=WorkflowState.BOXING,
        )
        return True

    def _foam_reset(self, cycle, snapshot):
        if snapshot.get('foam_trigger'):
            return False
        self._write('foam_passed', False, 121)
        self._write('foam_done', False, 122)
        if cycle.foam_passed is False:
            cycle.foam_passed = None
            cycle.save(update_fields=['foam_passed', 'updated_at'])
            self._set_phase(cycle, StationPhase.WAIT_FOAM)
        else:
            self._set_phase(cycle, StationPhase.WAIT_BOXING)
        return True

    def _boxing_trigger(self, cycle, snapshot):
        if not snapshot.get('boxing_trigger'):
            return False
        payload = {
            'product_code': cycle.product.product_code,
            'rack_code': cycle.product.rack.rack_code,
            'loaded_quantity': cycle.loaded_quantity,
            'planned_quantity': cycle.planned_quantity,
            'completed_at': timezone.now().isoformat(),
        }
        response = self.mes.upload_boxing_result(
            payload, product=cycle.product, rack=cycle.product.rack,
        )
        succeeded = bool(response.get('success'))
        cycle.mes_upload_success = succeeded
        cycle.save(update_fields=['mes_upload_success', 'updated_at'])
        self._write('mes_upload_success', succeeded, 124)
        self._write('mes_upload_done', True, 125)
        if not succeeded:
            raise StationStepError('MES 装箱结果上传失败', AlarmSource.MES)
        self._set_phase(
            cycle, StationPhase.WAIT_BOXING_RESET, event_type='BOXING_UPLOADED',
            source=EventSource.MES, message='单件装箱结果已上传 MES', payload=payload,
            workflow_state=WorkflowState.BOXING,
        )
        return True

    def _boxing_reset(self, cycle, snapshot):
        if snapshot.get('boxing_trigger'):
            return False
        self._write('mes_upload_success', False, 124)
        self._write('mes_upload_done', False, 125)
        if cycle.mes_upload_success is False:
            cycle.mes_upload_success = None
            cycle.save(update_fields=['mes_upload_success', 'updated_at'])
            self._set_phase(cycle, StationPhase.WAIT_BOXING)
            return True
        loaded = max(0, int(snapshot.get('loaded_quantity', 0)))
        cycle.loaded_quantity = loaded
        if cycle.planned_quantity and loaded > cycle.planned_quantity:
            cycle.save(update_fields=['loaded_quantity', 'updated_at'])
            raise StationStepError(
                f'PLC 已装数量 {loaded} 超过 MES 配方总数 {cycle.planned_quantity}',
                AlarmSource.WORKFLOW,
            )
        if cycle.planned_quantity and loaded == cycle.planned_quantity:
            cycle.finished_at = timezone.now()
            cycle.save(update_fields=['loaded_quantity', 'finished_at', 'updated_at'])
            self._set_phase(
                cycle, StationPhase.COMPLETED, event_type='RACK_FULL',
                source=EventSource.PLC,
                message=f'装箱已满 {loaded}/{cycle.planned_quantity}',
                payload={'loaded_quantity': loaded},
                workflow_state=WorkflowState.COMPLETED,
            )
        else:
            cycle.save(update_fields=['loaded_quantity', 'updated_at'])
            self._set_phase(cycle, StationPhase.WAIT_FOAM)
        return True

    def _lock(self, cycle, message, source):
        workflow = cycle.workflow if cycle.workflow_id else None
        product = cycle.product
        rack = product.rack if product else None
        self.alarms.create(
            source=source, message=message, level=AlarmLevel.ERROR,
            product=product, rack=rack, workflow=workflow,
            lock_workstation=True,
        )
        cycle.resume_phase = cycle.phase
        cycle.is_locked = True
        cycle.last_error = message
        cycle.phase = StationPhase.LOCKED
        cycle.save(update_fields=[
            'resume_phase', 'is_locked', 'last_error', 'phase', 'updated_at',
        ])
        if workflow:
            previous_state = workflow.current_state
            workflow.last_error = message
            workflow.current_state = WorkflowState.LOCKED
            workflow.is_locked = True
            workflow.save(update_fields=[
                'last_error', 'current_state', 'is_locked', 'updated_at',
            ])
            workflow.product.current_state = WorkflowState.LOCKED
            workflow.product.save(update_fields=['current_state', 'updated_at'])
            WorkflowEvent.objects.create(
                workflow=workflow, event_type='STATION_LOCKED',
                from_state=previous_state, to_state=WorkflowState.LOCKED,
                source=EventSource.SYSTEM, occurred_at=timezone.now(),
                message=message, success=False,
            )
        try:
            self._write('workstation_locked', True, 126)
        except Exception:
            pass

    def unlock(self, cycle, operator_note=''):
        if cycle.phase != StationPhase.LOCKED:
            return cycle
        # Resume from the phase that failed. Result/done outputs must first wait
        # for the PLC trigger to reset before allowing a retry.
        if cycle.recipe_verified is False:
            resume = StationPhase.WAIT_RECIPE_RESET
        elif cycle.foam_passed is False:
            resume = StationPhase.WAIT_FOAM_RESET
        elif cycle.mes_upload_success is False:
            resume = StationPhase.WAIT_BOXING_RESET
        else:
            resume = cycle.resume_phase or StationPhase.WAIT_PRODUCT
        # PLC unlock is part of the operation: do it before committing database
        # state so a communication failure cannot show a false unlocked status.
        self._write('workstation_locked', False, 126)
        cycle.is_locked = False
        cycle.last_error = ''
        cycle.phase = resume
        cycle.resume_phase = ''
        cycle.save(update_fields=[
            'is_locked', 'last_error', 'phase', 'resume_phase', 'recipe_verified', 'foam_passed',
            'mes_upload_success', 'updated_at',
        ])
        if cycle.workflow_id:
            workflow_state = self._workflow_state_for_phase(resume)
            cycle.workflow.is_locked = False
            cycle.workflow.last_error = ''
            cycle.workflow.current_state = workflow_state
            cycle.workflow.current_stage = STATE_STAGE_MAP.get(
                workflow_state, cycle.workflow.current_stage,
            )
            cycle.workflow.save(update_fields=[
                'is_locked', 'last_error', 'current_state', 'current_stage', 'updated_at',
            ])
            cycle.workflow.product.current_state = workflow_state
            cycle.workflow.product.save(update_fields=['current_state', 'updated_at'])
            WorkflowEvent.objects.create(
                workflow=cycle.workflow, event_type='STATION_UNLOCKED',
                from_state=StationPhase.LOCKED, to_state=resume,
                source=EventSource.OPERATOR, occurred_at=timezone.now(),
                message=operator_note or '人工解除工位锁定', success=True,
            )
        return cycle

    @staticmethod
    def _workflow_state_for_phase(phase):
        if phase in (StationPhase.WAIT_PRODUCT, StationPhase.WAIT_MARK_RESET):
            return WorkflowState.BARCODE_READ
        if phase in (StationPhase.WAIT_RACK, StationPhase.WAIT_RACK_RESET):
            return WorkflowState.BARCODE_READ
        if phase in (StationPhase.WAIT_POSITION, StationPhase.WAIT_POSITION_RESET):
            return WorkflowState.RECIPE_LOADED
        if phase in (StationPhase.WAIT_RECIPE_VERIFY, StationPhase.WAIT_RECIPE_RESET):
            return WorkflowState.RACK_LOCATED
        if phase in (StationPhase.WAIT_FOAM, StationPhase.WAIT_FOAM_RESET):
            return WorkflowState.RECIPE_VERIFIED
        return WorkflowState.BOXING
