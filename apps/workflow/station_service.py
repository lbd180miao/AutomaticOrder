"""DB2-driven packing station orchestration.

No PLC protocol details or vision algorithms live here. The service coordinates
existing production/MES/vision/alarm services and persists every handshake phase.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.alarms.services import AlarmService
from apps.core.constants import (
    AlarmLevel, AlarmSource, DeviceType, EventSource,
    STATE_STAGE_MAP, Stage, WorkflowState,
)
from apps.devices.plc_db100 import POINTS_BY_NAME, DB_NUMBER
from apps.devices.models import Device
from apps.devices.services import DeviceService, get_plc_adapter
from apps.mes.services import MesService
from apps.production.services import ProductionService
from apps.vision.services import VisionService

from .models import StationCycle, StationPhase, WorkflowEvent, WorkflowInstance
from apps.mes.remote_client import RemoteMesClient, RemotePending


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

    def calculate_position_offsets(self, cycle, *, on_captured=None):
        if self.simulated:
            if on_captured is not None:
                on_captured()
            return {axis: 0.0 for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2')}

        from apps.production.rack_recipe_service import RackPositionResolver
        from apps.vision.models import RackLocationRecipe
        from apps.devices.plc_position_debug import capture_position

        conf = getattr(settings, 'AUTOMATIC_ORDER', {})
        recipe_id = conf.get('VISION_POSITION_RECIPE_ID')
        qs = RackLocationRecipe.objects.filter(enabled=True)
        rack = cycle.rack or cycle.product.rack
        if recipe_id:
            recipe = qs.filter(pk=recipe_id).first()
            target_layer_no = recipe.layer_no if recipe else None
        elif (
            rack.current_recipe_id
            and rack.current_recipe.vision_mappings.filter(
                enabled=True,
                rack_location_recipe__isnull=False,
            ).exists()
        ):
            position_text = str(rack.position_side or '1').strip().upper()
            station_position_no = 2 if (
                '2' in position_text or position_text in {'RIGHT', 'R'}
            ) else 1
            resolved = RackPositionResolver(rack.current_recipe).resolve(
                cycle.loaded_quantity,
                station_position_no,
            )
            mapping_state = resolved.get('mapping') or {}
            if not mapping_state.get('ready'):
                detail = '、'.join(mapping_state.get('issues') or ['未建立视觉映射'])
                raise StationStepError(
                    f'{station_position_no}号位当前层3D映射未就绪：{detail}',
                    AlarmSource.RECIPE,
                )
            recipe = qs.filter(pk=resolved['rack_location_recipe_id']).first()
            target_layer_no = (
                resolved['current']['layer_no'] if resolved['current'] else None
            )
            if recipe is None:
                layer_label = target_layer_no or '当前'
                raise StationStepError(
                    f'{station_position_no}号位第{layer_label}层未配置可用的3D定位配方',
                    AlarmSource.RECIPE,
                )
        else:
            recipe = qs.filter(rack_type=rack.rack_type).order_by('layer_no').first()
            recipe = recipe or qs.order_by('position_no', 'layer_no').first()
            target_layer_no = recipe.layer_no if recipe else None
        if recipe is None:
            raise StationStepError('未找到可用的 3D 定位配方', AlarmSource.RECIPE)
        result = capture_position(recipe.id, target_layer_no, on_captured=on_captured)
        if not result.get('is_success'):
            raise StationStepError(
                result.get('error_message') or '3D 定位失败', AlarmSource.VISION,
            )
        return {axis: float(result[f'compensation_{axis}'])
                for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2')}

    def measure_recipe(self, cycle):
        rack = cycle.rack or cycle.product.rack
        recipe = rack.current_recipe
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
                product=cycle.product, rack=rack, recipe=recipe,
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
            cycle.rack,
            position_index=cycle.loaded_quantity,
            use_camera=not self.simulated,
        )
        return bool(result.is_passed), result


class StationWorkflowService:
    OUTPUTS = (
        'mark_read_done', 'product_barcode_valid', 'rack_done', 'rack_result',
        'boxing_allowed', 'recipe_verify_done', 'position_done',
        'position_success', 'layer_delta_x', 'layer_delta_y', 'layer_delta_z', 'layer_delta_x2', 'layer_delta_y2', 'layer_delta_z2', 'foam_done', 'foam_passed',
        'product_mes_upload_done', 'product_mes_upload_success',
        'mes_upload_success', 'mes_upload_done', 'workstation_locked',
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
                'rack__current_recipe', 'workflow__product__rack__current_recipe',
            )
            .order_by('-created_at')
            .first()
        )

    def _ensure_cycle(self):
        cycle = self.active_cycle()
        if cycle is not None:
            return cycle
        for output in self.OUTPUTS:
            if not output.startswith('layer_delta_'):
                self.plc.write_point(output, False)
        return StationCycle.objects.create(
            phase=StationPhase.WAIT_RACK,
            started_at=timezone.now(),
        )

    def poll_once(self):
        from apps.devices.plc_position_debug import ownership, active, DebugBusy
        try:
            with ownership(scan=True) as (state, save):
                if active(state):
                    return self.active_cycle(), False
                with self.plc.maintain_heartbeat():
                    return self._poll_once_owned()
        except DebugBusy:
            return self.active_cycle(), False

    def _poll_once_owned(self):
        """Process at most one phase transition from the current DB2 snapshot."""
        heartbeat = self.plc.tick_heartbeat()
        snapshot = self.plc.read_snapshot()
        cycle = self._ensure_cycle()
        self.devices.record_signal(
            self.plc_device_code, 'heartbeat', heartbeat, direction='OUT',
            raw_payload={'db': DB_NUMBER, 'offset': 48, 'bit': 0},
        )
        if cycle.phase == StationPhase.LOCKED:
            if not snapshot.get('workstation_locked', True):
                self.plc.write_point('workstation_locked', True)
            return cycle, False

        try:
            if isinstance(getattr(self.mes, 'client', None), RemoteMesClient):
                self.mes.client.nonblocking = True
                self.mes.client.context_cycle = cycle.pk
            changed = self._dispatch(cycle, snapshot)
        except RemotePending:
            # Durable network work runs separately; keep polling and maintaining heartbeat.
            return cycle, False
        except StationStepError as exc:
            self._write_failure_result(cycle)
            self._lock(cycle, str(exc), exc.source)
            changed = True
        except Exception as exc:  # keep unexpected integration failures visible
            self._write_failure_result(cycle)
            self._lock(cycle, f'工位流程异常：{exc}', AlarmSource.WORKFLOW)
            changed = True
        return cycle, changed

    def _save_io(self, cycle):
        cycle.save(update_fields=['io_state', 'updated_at'])

    def _accept(self, cycle, snapshot, trigger, fields=()):
        pending = cycle.io_state.get('pending')
        if pending:
            if pending['trigger'] != trigger:
                return None
        else:
            if not snapshot.get(trigger):
                return None
            feedback = {'rack_trigger': ('rack_done',), 'mark_trigger': ('product_mes_upload_done',),
                        'position_trigger': ('position_done', 'position_success'),
                        'foam_trigger': ('foam_done',), 'boxing_trigger': ('mes_upload_done',)}
            if any(self.plc.read_point(bit) for bit in feedback.get(trigger, ())):
                return None
            pending = {'trigger': trigger, 'data': {key: snapshot.get(key) for key in fields},
                       'accepted_at': timezone.now().isoformat()}
            cycle.io_state['pending'] = pending
            self._save_io(cycle)
        # A pending task resumes from its saved input, never from overwritten DB strings.
        if not pending.get('consumed'):
            self.plc.write_point(trigger, False)
            pending['consumed'] = True
            self._save_io(cycle)
        return pending

    def _acknowledged(self, cycle, *bits):
        if any(self.plc.read_point(bit) for bit in bits):
            return False
        cycle.io_state.pop('pending', None)
        self._save_io(cycle)
        return True

    def _mes_response(self, cycle, pending, action, call, *, product=None):
        from apps.mes.models import MesRecord
        if (pending.get('response') or {}).get('success'):
            return pending['response']
        # Recover an already recorded MES response after a local save/worker failure.
        record = MesRecord.objects.filter(
            action=action, rack=cycle.rack, product=product,
            created_at__gte=pending['accepted_at'],
        ).order_by('-pk').first()
        if record is not None:
            response = record.response_payload
        else:
            remote = isinstance(getattr(self.mes, 'client', None), RemoteMesClient)
            if pending.get('mes_started') and not remote:
                raise StationStepError('上次 MES 请求结果未确认，请先核对 MES，禁止自动重复提交', AlarmSource.MES)
            pending['mes_started'] = True
            self._save_io(cycle)
            response = call()
        pending['response'] = response
        self._save_io(cycle)
        return response

    def _ready_trigger(self, cycle, snapshot):
        pending = cycle.io_state.get('pending') or {}
        trigger = pending.get('trigger')
        handlers = [('position_trigger', self._position_trigger),
                    ('mark_trigger', self._product_trigger),
                    ('foam_trigger', self._foam_trigger),
                    ('boxing_trigger', self._mes_box_trigger)]
        for name, handler in handlers:
            if trigger == name or (not trigger and snapshot.get(name)):
                phase = {'position_trigger': StationPhase.WAIT_POSITION, 'mark_trigger': StationPhase.WAIT_PRODUCT,
                         'foam_trigger': StationPhase.WAIT_FOAM, 'boxing_trigger': StationPhase.WAIT_BOXING}[name]
                self._set_phase(cycle, phase)
                return handler(cycle, snapshot)
        return False

    def _dispatch(self, cycle, snapshot):
        handlers = {
            StationPhase.WAIT_PRODUCT: self._ready_trigger,
            StationPhase.WAIT_MARK_RESET: self._mark_reset,
            StationPhase.WAIT_RACK: self._rack_trigger,
            StationPhase.WAIT_RACK_RESET: self._rack_reset,
            StationPhase.WAIT_POSITION: self._position_trigger,
            StationPhase.WAIT_POSITION_RESET: self._position_reset,
            StationPhase.WAIT_RECIPE_VERIFY: self._recipe_trigger,
            StationPhase.WAIT_RECIPE_RESET: self._recipe_reset,
            StationPhase.WAIT_FOAM: self._foam_trigger,
            StationPhase.WAIT_FOAM_RESET: self._foam_reset,
            StationPhase.WAIT_BOXING: self._mes_box_trigger,
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
            self.plc_device_code, name, value, raw_payload={'db': DB_NUMBER, 'offset': POINTS_BY_NAME[name].offset, 'bit': POINTS_BY_NAME[name].bit},
        )

    def _write(self, name, value, offset):
        self.plc.write_point(name, value)
        self.devices.record_signal(
            self.plc_device_code, name,
            int(bool(value)) if isinstance(value, bool) else value,
            direction='OUT',
            raw_payload={'db': DB_NUMBER, 'offset': POINTS_BY_NAME[name].offset, 'bit': POINTS_BY_NAME[name].bit},
        )

    def _write_failure_result(self, cycle):
        """Expose a deterministic NG + done handshake before locking the station."""
        trigger = (cycle.io_state.get('pending') or {}).get('trigger')
        phase = {'position_trigger': StationPhase.WAIT_POSITION,
                 'mark_trigger': StationPhase.WAIT_PRODUCT, 'rack_trigger': StationPhase.WAIT_RACK,
                 'foam_trigger': StationPhase.WAIT_FOAM, 'boxing_trigger': StationPhase.WAIT_BOXING}.get(trigger, cycle.phase)
        if phase == StationPhase.WAIT_POSITION:
            from apps.devices.plc_db100 import POSITION_FAILURE_OFFSET
            try:
                self._write('position_success', False, 49)
                for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2'):
                    name = f'layer_delta_{axis}'
                    self._write(name, POSITION_FAILURE_OFFSET, POINTS_BY_NAME[name].offset)
                    if self.plc.read_point(name) != POSITION_FAILURE_OFFSET:
                        return
            except Exception:
                pass
            return
        failure_outputs = {
            StationPhase.WAIT_FOAM: (('foam_passed', False, 74), ('foam_done', True, 74)),
            StationPhase.WAIT_PRODUCT: (('product_mes_upload_success', False, 48), ('product_mes_upload_done', True, 48)),
            StationPhase.WAIT_RACK: (('rack_result', False, 52), ('rack_done', True, 51)),
            StationPhase.WAIT_BOXING: (('mes_upload_success', False, 74), ('mes_upload_done', True, 74)),
            StationPhase.WAIT_RECIPE_VERIFY: (('boxing_allowed', False, 55), ('recipe_verify_done', True, 54)),
        }
        for name, value, offset in failure_outputs.get(phase, ()):
            try:
                self._write(name, value, offset)
            except Exception:
                pass

    def _product_trigger(self, cycle, snapshot):
        from apps.core.barcode_validator import validate_product_barcode
        from apps.core.constants import MesAction
        from apps.production.models import Product
        pending = self._accept(cycle, snapshot, 'mark_trigger', ('product_barcode',))
        if pending is None:
            return False
        if cycle.rack_id is None or cycle.rack.current_recipe_id is None:
            raise StationStepError('料框与配方尚未准备完成', AlarmSource.RECIPE)
        self._write('product_mes_upload_success', False, 48)
        if not pending.get('product_id'):
            val = validate_product_barcode(pending['data']['product_barcode'], rack_code=cycle.rack.rack_code)
            if not val.is_valid:
                raise StationStepError(val.error_message, AlarmSource.SCANNER)
            with transaction.atomic():
                product = self.production.create_product(val.cleaned_code)
                workflow, _ = WorkflowInstance.objects.get_or_create(product=product,
                    defaults={'current_state': WorkflowState.BARCODE_READ,
                              'current_stage': Stage.STAGE_ONE, 'started_at': timezone.now()})
                cycle.workflow = workflow
                self.production.bind_product_to_rack(product, cycle.rack)
                pending['product_id'] = product.pk
                cycle.save(update_fields=['workflow', 'io_state', 'updated_at'])
        product = Product.objects.get(pk=pending['product_id'])
        upload = self._mes_response(cycle, pending, MesAction.UPLOAD_PRODUCT_BARCODE,
            lambda: self.mes.upload_product_barcode(product.product_code, cycle.rack.rack_code,
                                                   product=product, rack=cycle.rack), product=product)
        success = bool(upload.get('success'))
        if success and product.product_code not in cycle.bound_product_codes:
            cycle.bound_product_codes.append(product.product_code)
            cycle.loaded_quantity = len(cycle.bound_product_codes)
            cycle.save(update_fields=['bound_product_codes', 'loaded_quantity', 'updated_at'])
        self._write('product_mes_upload_success', success, 48)
        self._write('product_mes_upload_done', True, 48)
        self._set_phase(cycle, StationPhase.WAIT_MARK_RESET,
                        workflow_state=WorkflowState.BARCODE_READ)
        if not success:
            self._lock(cycle, upload.get('error') or '单件 MES 绑定失败', AlarmSource.MES)
        return True

    def _mark_reset(self, cycle, snapshot):
        pending = cycle.io_state.get('pending') or {}
        if self.plc.read_point('product_mes_upload_done'):
            return False
        if not (pending.get('response') or {}).get('success'):
            self._set_phase(cycle, StationPhase.WAIT_PRODUCT)
            return True  # retain the same product for deliberate retry/reconciliation
        self._acknowledged(cycle, 'product_mes_upload_done')
        self._set_phase(cycle, StationPhase.WAIT_PRODUCT)
        return True

    def _rack_trigger(self, cycle, snapshot):
        from apps.core.barcode_validator import validate_rack_barcode
        from apps.core.constants import MesAction
        from apps.production.models import Product
        pending = self._accept(cycle, snapshot, 'rack_trigger', ('rack_barcode',))
        if pending is None:
            return False
        self._write('rack_result', False, 48)
        val = validate_rack_barcode(pending['data']['rack_barcode'])
        if not val.is_valid:
            raise StationStepError(val.error_message, AlarmSource.SCANNER)
        rack = self.production.get_or_create_rack(val.cleaned_code)
        cycle.rack = rack
        cycle.save(update_fields=['rack', 'updated_at'])
        response = self._mes_response(cycle, pending, MesAction.GET_RACK_RECIPE,
            lambda: self.mes.get_rack_recipe(rack.rack_code, rack=rack))
        if not response.get('success'):
            raise StationStepError(response.get('error') or 'MES 查询失败', AlarmSource.MES)
        recipe = self.production.sync_recipe_from_mes(rack, response)
        if recipe is None:
            raise StationStepError('未匹配到本地装箱配方', AlarmSource.RECIPE)
        raw = response.get('pkg_type_code') or response.get('PkgTypeCode') or (response.get('mes_data') or {}).get('PkgTypeCode')
        number = {'2LayerRack': 1, '3LayerRack': 2, '5LaverRack': 3}.get(raw)
        if number is None:
            number = {'两层': 1, '三层': 2, '五层': 3}.get(response.get('rack_type') or rack.rack_type)
        if number is None:
            raise StationStepError('MES 料框类型无法转换为 PLC 类型数字', AlarmSource.MES)
        if not pending.get('prepared'):
            inner = response.get('mes_data') or {}
            qty = response.get('hu_qty', inner.get('HUQty', 0)) or 0
            has_binding = bool(response.get('product_codes') or response.get('bound_barcodes') or float(qty) > 0)
            with transaction.atomic():
                if has_binding:
                    cycle.io_state['cleared_bindings'] = list(Product.objects.filter(rack=rack).values('id', 'product_code', 'bound_at'))
                    for item in cycle.io_state['cleared_bindings']:
                        item['bound_at'] = item['bound_at'].isoformat() if item['bound_at'] else None
                    # Historical cycles/events keep their product list and bin number.
                    Product.objects.filter(rack=rack).update(rack=None, bound_at=None)
                pending['prepared'] = True
                cycle.bin_code = ''
                cycle.bound_product_codes = []
                cycle.planned_quantity = recipe.total_quantity
                cycle.save(update_fields=['io_state', 'bin_code', 'bound_product_codes', 'planned_quantity', 'updated_at'])
        self._write('rack_type_code', number, 76)
        self._write('rack_result', True, 48)
        self._write('rack_done', True, 48)
        self._set_phase(cycle, StationPhase.WAIT_RACK_RESET)
        return True

    def _rack_reset(self, cycle, snapshot):
        if not self._acknowledged(cycle, 'rack_done'):
            return False
        self._set_phase(cycle, StationPhase.WAIT_PRODUCT)
        return True

    def _position_trigger(self, cycle, snapshot):
        pending = self._accept(cycle, snapshot, 'position_trigger')
        if pending is None:
            return False
        if 'values' not in pending:
            if pending.get('capture_started'):
                raise StationStepError('上次 3D 任务被中断，请确认后重新触发', AlarmSource.VISION)
            pending['capture_started'] = True
            self._save_io(cycle)
            self._write('position_success', False, 49)
            values = self.vision.calculate_position_offsets(
                cycle, on_captured=lambda: self._write('position_done', True, 49),
            )
            pending['values'] = values
            self._save_io(cycle)
        values = pending['values']
        from apps.devices.plc_db100 import position_values
        values = position_values({f'compensation_{axis}': value for axis, value in values.items()})
        self._write('position_success', False, 49)
        for axis, value in values.items():
            name = f'layer_delta_{axis}'
            self._write(name, value, POINTS_BY_NAME[name].offset)
        for axis, value in values.items():
            if self.plc.read_point(f'layer_delta_{axis}') != value:
                raise StationStepError(f'{axis} 写后回读不一致', AlarmSource.DEVICE)
        delta_z = Decimal(str(values['z']))
        cycle.position_delta_z = delta_z
        cycle.positioning_matrix = [[values[a] for a in ('x', 'y', 'z')],
                                    [values[a] for a in ('x2', 'y2', 'z2')]]
        cycle.save(update_fields=['position_delta_z', 'positioning_matrix', 'updated_at'])
        self._write('position_success', True, 49)
        self._set_phase(
            cycle, StationPhase.WAIT_POSITION_RESET, event_type='POSITIONED',
            source=EventSource.VISION, message='当前层两组 XYZ 已写入 DB2.DBD50～70',
            payload=values, workflow_state=WorkflowState.RACK_LOCATED,
        )
        return True

    def _position_reset(self, cycle, snapshot):
        if not self._acknowledged(cycle, 'position_done', 'position_success'):
            return False
        self._set_phase(cycle, StationPhase.WAIT_PRODUCT)
        return True

    def _recipe_trigger(self, cycle, snapshot):
        if not snapshot.get('recipe_verify_trigger'):
            return False
        self._record_input('recipe_verify_trigger', True, 46)
        height, spacing = self.vision.measure_recipe(cycle)
        recipe = cycle.rack.current_recipe
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
        self._write('boxing_allowed', passed, 49)
        self._write('recipe_verify_done', True, 48)
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
        self._write('boxing_allowed', False, 49)
        self._write('recipe_verify_done', False, 48)
        if cycle.recipe_verified is False:
            cycle.recipe_verified = None
            cycle.save(update_fields=['recipe_verified', 'updated_at'])
            self._set_phase(cycle, StationPhase.WAIT_RECIPE_VERIFY)
        else:
            self._set_phase(cycle, StationPhase.WAIT_POSITION)
        return True

    def _foam_trigger(self, cycle, snapshot):
        pending = self._accept(cycle, snapshot, 'foam_trigger')
        if pending is None:
            return False
        self._write('foam_passed', False, 74)
        if 'passed' not in pending:
            if pending.get('capture_started'):
                raise StationStepError('上次 2D 采集被中断，请确认后重试', AlarmSource.VISION)
            pending['capture_started'] = True
            self._save_io(cycle)
            passed, _ = self.vision.inspect_foam(cycle)
            pending['passed'] = bool(passed)
            self._save_io(cycle)
        cycle.foam_passed = pending['passed']
        cycle.save(update_fields=['foam_passed', 'updated_at'])
        self._write('foam_passed', cycle.foam_passed, 74)
        self._write('foam_done', True, 74)
        self._set_phase(cycle, StationPhase.WAIT_FOAM_RESET)
        if not cycle.foam_passed:
            self._lock(cycle, '泡棉检测不合格', AlarmSource.VISION)
        return True

    def _foam_reset(self, cycle, snapshot):
        if not self._acknowledged(cycle, 'foam_done'):
            return False
        cycle.foam_passed = None
        cycle.save(update_fields=['foam_passed', 'updated_at'])
        self._set_phase(cycle, StationPhase.WAIT_PRODUCT)
        return True

    def _mes_box_trigger(self, cycle, snapshot):
        from apps.core.constants import MesAction
        from apps.production.models import Product
        pending = self._accept(cycle, snapshot, 'boxing_trigger')
        if pending is None:
            return False
        self._write('mes_upload_success', False, 74)
        bound = set(Product.objects.filter(rack=cycle.rack, bound_at__gte=cycle.started_at)
                    .values_list('product_code', flat=True))
        if not cycle.bound_product_codes or bound != set(cycle.bound_product_codes):
            raise StationStepError('本框存在未成功上传的产品绑定或没有产品，不能封箱', AlarmSource.MES)
        if 'payload' not in pending:
            pending['payload'] = {'rack_code': cycle.rack.rack_code,
                'product_codes': list(cycle.bound_product_codes),
                'loaded_quantity': cycle.loaded_quantity, 'planned_quantity': cycle.planned_quantity,
                'completed_at': timezone.now().isoformat()}
            self._save_io(cycle)
        response = self._mes_response(cycle, pending, MesAction.UPLOAD_BOXING_RESULT,
            lambda: self.mes.upload_boxing_result(pending['payload'], product=cycle.product, rack=cycle.rack),
            product=cycle.product)
        if not response.get('success'):
            raise StationStepError(response.get('error') or 'MES 封箱失败', AlarmSource.MES)
        bin_code = response.get('bin_code') or (response.get('mes_data') or {}).get('BinCode')
        if not bin_code:
            raise StationStepError('MES 封箱已返回但缺少区位号，请查询确认，不重复封箱', AlarmSource.MES)
        cycle.bin_code = str(bin_code)
        cycle.mes_upload_success = True
        cycle.save(update_fields=['bin_code', 'mes_upload_success', 'updated_at'])
        self._write('mes_upload_success', True, 74)
        self._write('mes_upload_done', True, 74)
        self._set_phase(cycle, StationPhase.WAIT_BOXING_RESET, event_type='BOXING_UPLOADED',
            source=EventSource.MES, message=f'封箱成功，区位号 {bin_code}',
            payload={**pending['payload'], 'bin_code': cycle.bin_code})
        return True

    def _boxing_reset(self, cycle, snapshot):
        if self.plc.read_point('mes_upload_done'):
            return False
        if not cycle.mes_upload_success:
            self._set_phase(cycle, StationPhase.WAIT_BOXING)
            return True
        self._acknowledged(cycle, 'mes_upload_done')
        cycle.finished_at = timezone.now()
        cycle.save(update_fields=['finished_at', 'updated_at'])
        self._set_phase(cycle, StationPhase.COMPLETED, event_type='RACK_FULL',
            source=EventSource.PLC, message='MES 封箱及本地保存成功，PLC 已确认',
            workflow_state=WorkflowState.COMPLETED)
        return True

    def _lock(self, cycle, message, source):
        workflow = cycle.workflow if cycle.workflow_id else None
        product = cycle.product
        rack = cycle.rack or (product.rack if product else None)
        scene_by_phase = {
            StationPhase.WAIT_RACK: '场景一：料框到位',
            StationPhase.WAIT_RACK_RESET: '场景一：料框到位',
            StationPhase.WAIT_POSITION: '场景二：料架定位补偿',
            StationPhase.WAIT_POSITION_RESET: '场景二：料架定位补偿',
            StationPhase.WAIT_PRODUCT: '产品条码暂存',
            StationPhase.WAIT_MARK_RESET: '产品条码暂存',
            StationPhase.WAIT_RECIPE_VERIFY: '产品条码暂存',
            StationPhase.WAIT_RECIPE_RESET: '产品条码暂存',
            StationPhase.WAIT_FOAM: '场景三：泡棉检测',
            StationPhase.WAIT_FOAM_RESET: '场景三：泡棉检测',
            StationPhase.WAIT_BOXING: '场景四：装箱完成与上传',
            StationPhase.WAIT_BOXING_RESET: '场景四：装箱完成与上传',
        }
        recipe = rack.current_recipe if rack and rack.current_recipe_id else None
        self.alarms.create(
            source=source, message=message, level=AlarmLevel.ERROR,
            product=product, rack=rack, workflow=workflow,
            lock_workstation=True,
            scene=scene_by_phase.get(cycle.phase, '工位流程'),
            phase=cycle.phase,
            context={
                'station_cycle_id': cycle.pk,
                'loaded_quantity': cycle.loaded_quantity,
                'planned_quantity': cycle.planned_quantity,
                'position_delta_z': (
                    float(cycle.position_delta_z)
                    if cycle.position_delta_z is not None else None
                ),
                'measured_layer_height': (
                    float(cycle.measured_layer_height)
                    if cycle.measured_layer_height is not None else None
                ),
                'measured_layer_spacing': (
                    float(cycle.measured_layer_spacing)
                    if cycle.measured_layer_spacing is not None else None
                ),
                'recipe_layer_height': (
                    float(recipe.layer_height) if recipe else None
                ),
                'recipe_layer_spacing': (
                    float(recipe.layer_spacing) if recipe else None
                ),
                'recipe_tolerance_z': (
                    float(recipe.tolerance_z) if recipe else None
                ),
            },
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
            self._write('workstation_locked', True, 74)
        except Exception:
            pass

    def unlock(self, cycle, operator_note=''):
        if cycle.phase != StationPhase.LOCKED:
            return cycle
        pending = cycle.io_state.get('pending') or {}
        trigger = pending.get('trigger')
        bits = {'rack_trigger': ('rack_done',), 'mark_trigger': ('product_mes_upload_done',),
                'position_trigger': ('position_done', 'position_success'),
                'foam_trigger': ('foam_done',), 'boxing_trigger': ('mes_upload_done',)}
        if any(self.plc.read_point(bit) for bit in bits.get(trigger, ())):
            raise StationStepError('请先由 PLC 读取并复位本次完成反馈，再解除锁定', AlarmSource.DEVICE)
        if trigger in ('rack_trigger', 'foam_trigger') or (
            trigger == 'position_trigger' and 'values' not in pending
        ) or (trigger == 'mark_trigger' and not pending.get('product_id')):
            cycle.io_state.pop('pending', None)
            self._save_io(cycle)
        # Preserve MES responses and valid calculated data for local recovery.
        # Resume from the phase that failed. Result/done outputs must first wait
        # for the PLC trigger to reset before allowing a retry.
        if trigger:
            resume = StationPhase.WAIT_RACK if trigger == 'rack_trigger' else StationPhase.WAIT_PRODUCT
        elif cycle.recipe_verified is False:
            resume = StationPhase.WAIT_RECIPE_RESET
        elif cycle.foam_passed is False:
            resume = StationPhase.WAIT_FOAM_RESET
        elif cycle.mes_upload_success is False:
            resume = StationPhase.WAIT_BOXING_RESET
        else:
            resume = cycle.resume_phase or StationPhase.WAIT_RACK
        # PLC unlock is part of the operation: do it before committing database
        # state so a communication failure cannot show a false unlocked status.
        self._write('workstation_locked', False, 74)
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
            return WorkflowState.RECIPE_LOADED
        if phase in (StationPhase.WAIT_POSITION, StationPhase.WAIT_POSITION_RESET):
            return WorkflowState.RECIPE_LOADED
        if phase in (StationPhase.WAIT_RECIPE_VERIFY, StationPhase.WAIT_RECIPE_RESET):
            return WorkflowState.RACK_LOCATED
        if phase in (StationPhase.WAIT_FOAM, StationPhase.WAIT_FOAM_RESET):
            return WorkflowState.RECIPE_VERIFIED
        return WorkflowState.BOXING
