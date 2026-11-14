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
from apps.devices.plc_db100 import POINTS_BY_NAME, DB_NUMBER, ACTIVE_OUTPUT_NAMES
from apps.devices.models import Device
from apps.devices.services import DeviceService, get_plc_adapter
from apps.mes.services import MesService
from apps.production.services import ProductionService
from apps.vision.services import FoamRecipeConfigurationError, VisionService

from apps.devices.listener_logs import record, CATEGORIES

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
        self.simulated = False

    def calculate_position_offsets(self, cycle, *, on_captured=None):
        if self.simulated:
            if on_captured is not None:
                on_captured()
            return {axis: 0.0 for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2')}

        from apps.vision.plc_defaults import get_default_recipe
        from apps.devices.plc_position_debug import capture_position

        try:
            recipe = get_default_recipe('rack')
        except ValueError as exc:
            raise StationStepError(str(exc), AlarmSource.RECIPE) from exc
        target_layer_no = recipe.layer_no
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
        from apps.vision.plc_defaults import get_default_recipe

        recipe_id = None
        if not self.simulated:
            try:
                recipe_id = get_default_recipe('foam').pk
            except ValueError as exc:
                raise StationStepError(str(exc), AlarmSource.RECIPE) from exc
        try:
            result = self.service.inspect_foam(
                cycle.product,
                cycle.rack,
                position_index=cycle.loaded_quantity,
                use_camera=not self.simulated,
                use_recipe=not self.simulated,
                recipe_id=recipe_id,
                require_ready_recipe=not self.simulated,
            )
        except FoamRecipeConfigurationError as exc:
            raise StationStepError(str(exc), AlarmSource.RECIPE) from exc
        return bool(result.is_passed), result


class StationWorkflowService:
    OUTPUTS = tuple(sorted(ACTIVE_OUTPUT_NAMES))

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
        previous = StationCycle.objects.order_by('-created_at').first()
        # Carry the observed levels across completed cycles: an unchanged rack
        # string or sustained high input must never create a second job.
        io_state = {}
        if previous is not None:
            io_state = {key: previous.io_state[key] for key in
                        ('listener_inputs', 'listener_queue') if key in previous.io_state}
        return StationCycle.objects.create(
            phase=StationPhase.WAIT_RACK, started_at=timezone.now(), io_state=io_state,
        )

    def poll_once(self):
        self.last_scan_succeeded = False
        from apps.devices.plc_position_debug import ownership, active, DebugBusy
        try:
            with ownership(scan=True) as (state, save):
                if active(state):
                    return self.active_cycle(), False
                return self._poll_once_owned()
        except DebugBusy:
            return self.active_cycle(), False

    def _poll_once_owned(self):
        """Process at most one phase transition from the current DB2 snapshot."""
        sampler = getattr(self, 'input_sampler', None)
        self._input_samples = sampler.drain() if sampler else [self.plc.read_listener_snapshot()]
        snapshot = self._input_samples[-1]
        self.last_scan_succeeded = True
        cycle = self._ensure_cycle()

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
            self._channel_failure(cycle, (cycle.io_state.get('pending') or {}).get('trigger', ''),
                                  str(exc), exc.source)
            changed = True
        except Exception as exc:  # keep unexpected integration failures visible
            self._write_failure_result(cycle)
            self._channel_failure(cycle, (cycle.io_state.get('pending') or {}).get('trigger', ''),
                                  f'执行异常：{exc}', AlarmSource.WORKFLOW)
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
            pending = {'trigger': trigger, 'data': {key: snapshot.get(key) for key in fields},
                       'accepted_at': timezone.now().isoformat()}
            record(CATEGORIES.get(trigger, 'mes'), f'收到 {trigger}：{pending["data"]}')
            cycle.io_state['pending'] = pending
            self._save_io(cycle)
        # A pending task resumes from its saved input, never from overwritten DB strings.
        if not pending.get('consumed'):
            # Input bits belong to PLC: do not manufacture a falling edge.
            pending['consumed'] = True
            self._save_io(cycle)
        return pending

    def _acknowledged(self, cycle, *bits):
        if any(self.plc.read_point(bit) for bit in bits if bit in ACTIVE_OUTPUT_NAMES):
            return False
        cycle.io_state.pop('pending', None)
        self._save_io(cycle)
        return True

    def _mes_response(self, cycle, pending, action, call, *, product=None):
        from apps.mes.models import MesRecord
        if (pending.get('response') or {}).get('success'):
            return pending['response']
        # Recover an already recorded MES response after a local save/worker failure.
        mes_record = MesRecord.objects.filter(
            action=action, rack_id=pending.get('rack_id', cycle.rack_id), product=product,
            created_at__gte=pending['accepted_at'],
        ).order_by('-pk').first()
        if mes_record is not None:
            response = mes_record.response_payload
        else:
            remote = isinstance(getattr(self.mes, 'client', None), RemoteMesClient)
            if pending.get('mes_started') and not remote:
                raise StationStepError('上次 MES 请求结果未确认，请先核对 MES，禁止自动重复提交', AlarmSource.MES)
            pending['mes_started'] = True
            self._save_io(cycle)
            if not pending.get('request_logged'):
                record('mes', f'请求 {action}，料框={cycle.rack_id}，产品={getattr(product, "pk", None)}')
                pending['request_logged'] = True
                self._save_io(cycle)
            if remote:
                self.mes.client.context_request = pending['accepted_at']
            response = call()
            record('mes', f'{action} 返回：{response}')
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
        """Persist nine-input snapshots before executing the routed actions."""
        from .plc_inputs import collect_events
        state = cycle.io_state
        observed = state.setdefault('listener_inputs', {})
        queue = state.setdefault('listener_queue', [])
        samples = getattr(self, '_input_samples', [snapshot])
        logged = dict(observed)
        for sample in samples:
            for name, value in sample.items():
                if name in POINTS_BY_NAME and logged.get(name) != value:
                    self._record_input(name, value, POINTS_BY_NAME[name].offset)
                    logged[name] = value
        events, messages = collect_events(
            observed, samples, initialize=not getattr(self, '_inputs_initialized', False))
        self._inputs_initialized = True
        queue.extend(events)
        for category, message in messages:
            record(category, message)
        # The new contract always requires real rising edges, including debug mode.
        queue[:] = [job for job in queue if not job.get('debug_repeat') or job.get('mes_started')]
        self._save_io(cycle)
        handlers = {
            'mark_trigger': (StationPhase.WAIT_PRODUCT, self._product_trigger,
                             ('product_mes_upload_done', 'product_mes_upload_success')),
            'rack_trigger': (StationPhase.WAIT_RACK, self._rack_trigger, ('rack_done',)),
            'position_trigger': (StationPhase.WAIT_POSITION, self._position_trigger,
                                 ()),
            'foam_trigger': (StationPhase.WAIT_FOAM, self._foam_trigger, ()),
            'boxing_trigger': (StationPhase.WAIT_BOXING, self._mes_box_trigger, ('mes_upload_done',)),
        }
        changed = False
        # Pending HTTP work in one channel must not stop other independent channels.
        blocked = set()
        for pending in list(queue):
            trigger = pending['trigger']
            channel = (trigger, pending.get('data', {}).get('rack_slot'))
            if channel in blocked:
                continue
            if trigger == 'boxing_trigger' and any(
                job is not pending and job['trigger'] == 'mark_trigger' and
                job.get('data', {}).get('rack_round') == pending['data'].get('rack_round')
                for job in queue[:queue.index(pending)]
            ):
                continue
            phase, execute, feedback = handlers[trigger]
            state['pending'] = pending
            cycle.phase = phase
            try:
                if not pending.get('feedback_cleared'):
                    for name in feedback:
                        if name in ACTIVE_OUTPUT_NAMES:
                            self.plc.write_point(name, False)
                    pending['feedback_cleared'] = True
                    self._save_io(cycle)
                result = execute(cycle, snapshot)
            except RemotePending:
                blocked.add(channel)
            except Exception as exc:
                # A camera/MES/recipe error belongs to this input only. Keep
                # servicing other inputs instead of locking the shared station.
                self._write_failure_result(cycle)
                self._channel_failure(cycle, trigger, str(exc),
                                      getattr(exc, 'source', AlarmSource.WORKFLOW))
                queue.remove(pending)
                changed = True
            else:
                if result:
                    queue.remove(pending)
                    changed = True
                    record(CATEGORIES[trigger], f'{trigger} 执行完成')
                    if (trigger == 'boxing_trigger' and cycle.mes_upload_success and
                            pending['data'].get('rack_round') == state.get('active_rack_round')):
                        cycle.finished_at = timezone.now()
                        cycle.save(update_fields=['finished_at', 'updated_at'])
                        # Independent input queues must survive MES completion.
                        self._set_phase(cycle, StationPhase.WAIT_RACK,
                                        workflow_state=WorkflowState.COMPLETED)
                    elif cycle.phase != StationPhase.LOCKED:
                        self._set_phase(cycle, StationPhase.WAIT_RACK)
                if cycle.phase in (StationPhase.LOCKED, StationPhase.COMPLETED):
                    if cycle.phase == StationPhase.COMPLETED:
                        state.pop('pending', None)
                    self._save_io(cycle)
                    return changed
            state.pop('pending', None)
            cycle.save(update_fields=['io_state', 'phase', 'updated_at'])
        return changed

    def _channel_failure(self, cycle, trigger, message, source):
        pending = dict(cycle.io_state.get('pending') or {})
        error_key = f"{trigger}:{pending.get('data', {}).get('rack_slot', 1)}"
        previous = (cycle.io_state.get('channel_errors', {}).get(error_key) or {}).get('pending') or {}
        if (trigger == 'boxing_trigger' and previous.get('mes_started') and
                previous.get('data', {}).get('rack_round') == pending.get('data', {}).get('rack_round')):
            pending = previous
        cycle.io_state.setdefault('channel_errors', {})[error_key] = {
            'message': message, 'at': timezone.now().isoformat(), 'pending': pending,
        }
        record(CATEGORIES.get(trigger, 'connection'), f'[报警] 本路执行失败，其他监听继续：{message}')
        self._save_io(cycle)

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
        # Only the eight outputs commissioned in the PLC participate in I/O.
        if name not in ACTIVE_OUTPUT_NAMES:
            return
        self.plc.write_point(name, value)
        self.devices.record_signal(
            self.plc_device_code, name,
            int(bool(value)) if isinstance(value, bool) else value,
            direction='OUT',
            raw_payload={'db': DB_NUMBER, 'offset': POINTS_BY_NAME[name].offset, 'bit': POINTS_BY_NAME[name].bit},
        )

    def _write_failure_result(self, cycle):
        """Overwrite failed vision results without touching handshake bits."""
        trigger = (cycle.io_state.get('pending') or {}).get('trigger')
        phase = {'position_trigger': StationPhase.WAIT_POSITION,
                 'mark_trigger': StationPhase.WAIT_PRODUCT, 'rack_trigger': StationPhase.WAIT_RACK,
                 'foam_trigger': StationPhase.WAIT_FOAM, 'boxing_trigger': StationPhase.WAIT_BOXING}.get(trigger, cycle.phase)
        if phase == StationPhase.WAIT_POSITION:
            from apps.devices.plc_db100 import POSITION_FAILURE_OFFSET
            # Attempt every result address even if one write/readback fails.
            for axis in ('x', 'y', 'z', 'x2', 'y2', 'z2'):
                name = f'layer_delta_{axis}'
                try:
                    self._write(name, POSITION_FAILURE_OFFSET, POINTS_BY_NAME[name].offset)
                except Exception as exc:
                    record('3d', f'[报警] 失败结果清零未完成：{name}：{exc}')
            return
        failure_outputs = {
            StationPhase.WAIT_FOAM: (('foam_passed', False, 74),),
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
        rack_code = pending['data'].get('rack_barcode', cycle.rack.rack_code if cycle.rack_id else '')
        if not rack_code:
            raise StationStepError('尚未读取有效料框码，无法绑定产品', AlarmSource.SCANNER)
        from apps.core.barcode_validator import validate_rack_barcode
        rack_validation = validate_rack_barcode(rack_code)
        if not rack_validation.is_valid:
            raise StationStepError(rack_validation.error_message, AlarmSource.SCANNER)
        rack = self.production.get_or_create_rack(rack_validation.cleaned_code)
        pending['rack_id'] = rack.pk
        self._write('product_mes_upload_success', False, 48)
        if not pending.get('product_id'):
            debug_product_id = None
            if pending.get('debug_repeat'):
                debug_product_id = Product.objects.filter(
                    product_code=pending['data']['product_barcode'], rack=rack
                ).values_list('pk', flat=True).first()
            val = validate_product_barcode(pending['data']['product_barcode'], rack_code=rack.rack_code,
                                           current_product_id=debug_product_id)
            if not val.is_valid:
                raise StationStepError(val.error_message, AlarmSource.SCANNER)
            with transaction.atomic():
                product = self.production.create_product(val.cleaned_code)
                workflow, _ = WorkflowInstance.objects.get_or_create(product=product,
                    defaults={'current_state': WorkflowState.BARCODE_READ,
                              'current_stage': Stage.STAGE_ONE, 'started_at': timezone.now()})
                if cycle.rack_id == rack.pk and (not pending['data'].get('rack_round') or
                        pending['data']['rack_round'] == cycle.io_state.get('active_rack_round')):
                    cycle.workflow = workflow
                self.production.bind_product_to_rack(product, rack)
                pending['product_id'] = product.pk
                cycle.save(update_fields=['workflow', 'io_state', 'updated_at'])
        product = Product.objects.get(pk=pending['product_id'])
        upload = self._mes_response(cycle, pending, MesAction.UPLOAD_PRODUCT_BARCODE,
            lambda: self.mes.upload_product_barcode(product.product_code, rack.rack_code,
                                                   product=product, rack=rack), product=product)
        success = bool(upload.get('success'))
        same_round = (not pending['data'].get('rack_round') or
                      pending['data']['rack_round'] == cycle.io_state.get('active_rack_round'))
        round_id = pending['data'].get('rack_round')
        if success and round_id:
            round_products = cycle.io_state.setdefault('round_products', {}).setdefault(round_id, [])
            if product.product_code not in round_products:
                round_products.append(product.product_code)
            self._save_io(cycle)
        if success and same_round and cycle.rack_id == rack.pk and product.product_code not in cycle.bound_product_codes:
            cycle.bound_product_codes.append(product.product_code)
            cycle.loaded_quantity = len(cycle.bound_product_codes)
            cycle.save(update_fields=['bound_product_codes', 'loaded_quantity', 'updated_at'])
        self._write('product_mes_upload_success', success, 48)
        self._write('product_mes_upload_done', True, 48)
        self._set_phase(cycle, StationPhase.WAIT_MARK_RESET,
                        workflow_state=WorkflowState.BARCODE_READ if same_round and cycle.rack_id == rack.pk else None)
        if not success:
            self._channel_failure(cycle, 'mark_trigger', upload.get('error') or '单件 MES 绑定失败', AlarmSource.MES)
        return True

    def _mark_reset(self, cycle, snapshot):
        pending = cycle.io_state.get('pending') or {}
        if 'product_mes_upload_done' in ACTIVE_OUTPUT_NAMES and self.plc.read_point('product_mes_upload_done'):
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
        pending['rack_id'] = rack.pk
        if not pending.get('round_started'):
            cycle.rack = rack
            cycle.bin_code = ''
            cycle.workflow = None
            cycle.mes_upload_success = None
            from django.utils.dateparse import parse_datetime
            cycle.started_at = parse_datetime(pending['accepted_at'])
            cycle.bound_product_codes = list(cycle.io_state.get('round_products', {}).get(pending['data'].get('rack_round', pending['accepted_at']), []))
            cycle.loaded_quantity = len(cycle.bound_product_codes)
            cycle.planned_quantity = 0
            cycle.io_state['active_rack_round'] = pending['data'].get('rack_round', pending['accepted_at'])
            pending['round_started'] = True
            cycle.save(update_fields=['rack', 'io_state', 'bin_code', 'workflow',
                                      'mes_upload_success', 'started_at', 'bound_product_codes',
                                      'loaded_quantity', 'planned_quantity', 'updated_at'])
        response = self._mes_response(cycle, pending, MesAction.GET_RACK_RECIPE,
            lambda: self.mes.get_rack_recipe(rack.rack_code, rack=rack))
        if not response.get('success'):
            raise StationStepError(response.get('error') or 'MES 查询失败', AlarmSource.MES)
        from apps.mes.services import map_pkg_type
        response = map_pkg_type(response)
        if not response.get('success'):
            raise StationStepError(response.get('error') or '料框类型映射无效', AlarmSource.MES)
        recipe = self.production.sync_recipe_from_mes(rack, response)
        from apps.mes.services import resolve_plc_rack_type
        try:
            number = resolve_plc_rack_type(response)
        except ValueError as exc:
            raise StationStepError(str(exc), AlarmSource.MES) from exc
        # Mapping the MES rack type does not require a local vision/packing recipe.
        if cycle.io_state.get('active_rack_round') == pending['data'].get('rack_round', pending['accepted_at']):
            cycle.planned_quantity = recipe.total_quantity if recipe else 0
            cycle.save(update_fields=['planned_quantity', 'updated_at'])
        type_point = 'rack_type_code_2' if pending['data'].get('rack_slot') == 2 else 'rack_type_code'
        self._write(type_point, number, POINTS_BY_NAME[type_point].offset)
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
            record('3d', '3D 触发已受理，正在检查默认配方并请求相机拍照')
            def captured():
                record('3d', '3D 相机采集完成，开始自动计算并保存视觉历史')
            values = self.vision.calculate_position_offsets(
                cycle, on_captured=captured,
            )
            pending['values'] = values
            self._save_io(cycle)
        values = pending['values']
        from apps.devices.plc_db100 import position_values
        values = position_values({f'compensation_{axis}': value for axis, value in values.items()})
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
        self._set_phase(
            cycle, StationPhase.WAIT_POSITION_RESET, event_type='POSITIONED',
            source=EventSource.VISION, message='当前层两组 XYZ 已写入 DB2.DBD76～96',
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
        if 'passed' not in pending:
            if pending.get('capture_started'):
                raise StationStepError('上次 2D 采集被中断，请确认后重试', AlarmSource.VISION)
            pending['capture_started'] = True
            self._save_io(cycle)
            record('2d', '泡棉触发已受理，正在检查默认配方、拍照、计算并保存视觉历史')
            passed, _ = self.vision.inspect_foam(cycle)
            pending['passed'] = bool(passed)
            self._save_io(cycle)
        cycle.foam_passed = pending['passed']
        cycle.save(update_fields=['foam_passed', 'updated_at'])
        self._write('foam_passed', cycle.foam_passed, 74)
        self._set_phase(cycle, StationPhase.WAIT_FOAM_RESET)
        if not cycle.foam_passed:
            self._channel_failure(cycle, 'foam_trigger', '泡棉检测不合格', AlarmSource.VISION)
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
        from apps.core.barcode_validator import validate_rack_barcode
        pending = self._accept(cycle, snapshot, 'boxing_trigger')
        if pending is None:
            return False
        rack_code = pending['data'].get('rack_barcode', cycle.rack.rack_code if cycle.rack_id else '')
        validation = validate_rack_barcode(rack_code)
        if not validation.is_valid:
            raise StationStepError(validation.error_message, AlarmSource.SCANNER)
        rack = self.production.get_or_create_rack(validation.cleaned_code)
        pending['rack_id'] = rack.pk
        round_id = pending['data'].get('rack_round') or cycle.io_state.get('active_rack_round')
        previous = (cycle.io_state.get('channel_errors', {}).get(f"boxing_trigger:{pending.get('data', {}).get('rack_slot', 1)}") or {}).get('pending') or {}
        if previous.get('mes_started') and previous.get('data', {}).get('rack_round') == round_id:
            raise StationStepError('上次封箱提交需核对 MES 结果；保留请求记录，禁止新触发重复提交', AlarmSource.MES)
        self._write('mes_upload_success', False, 74)
        if 'payload' not in pending:
            pending['payload'] = {'rack_code': rack.rack_code,
                'completed_at': timezone.now().isoformat()}
            self._save_io(cycle)
        response = self._mes_response(cycle, pending, MesAction.UPLOAD_BOXING_RESULT,
            lambda: self.mes.upload_boxing_result(pending['payload'], rack=rack))
        if not response.get('success'):
            raise StationStepError(response.get('error') or 'MES 封箱失败', AlarmSource.MES)
        bin_code = response.get('bin_code') or (response.get('mes_data') or {}).get('BinCode')
        bin_code = str(bin_code or '').strip()
        if not bin_code:
            raise StationStepError('MES 封箱已返回但缺少区位号，请查询确认，不重复封箱', AlarmSource.MES)
        returned_rack = response.get('rack_code') or (response.get('mes_data') or {}).get('RackCode')
        if returned_rack and str(returned_rack).strip() != rack.rack_code:
            raise StationStepError('MES 返回料框码与请求不一致，区位号未绑定', AlarmSource.MES)
        # Preserve the original rack/round association after the station moves on.
        cycle.io_state.setdefault('boxing_results', {})[round_id or pending['accepted_at']] = {
            'rack_id': rack.pk, 'rack_code': rack.rack_code, 'bin_code': bin_code,
            'completed_at': timezone.now().isoformat(),
        }
        if cycle.rack_id == rack.pk and round_id == cycle.io_state.get('active_rack_round'):
            cycle.bin_code = bin_code
            cycle.mes_upload_success = True
        cycle.save(update_fields=['io_state', 'bin_code', 'mes_upload_success', 'updated_at'])
        self._write('mes_upload_success', True, 74)
        self._write('mes_upload_done', True, 74)
        self._set_phase(cycle, StationPhase.WAIT_BOXING_RESET, event_type='BOXING_UPLOADED',
            source=EventSource.MES, message=f'封箱成功，区位号 {bin_code}',
            payload={**pending['payload'], 'bin_code': bin_code})
        return True

    def _boxing_reset(self, cycle, snapshot):
        if 'mes_upload_done' in ACTIVE_OUTPUT_NAMES and self.plc.read_point('mes_upload_done'):
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
        trigger = (cycle.io_state.get('pending') or {}).get('trigger')
        record(CATEGORIES.get(trigger, 'connection'), f'工位锁定：{message}')
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
        if any(self.plc.read_point(bit) for bit in bits.get(trigger, ()) if bit in ACTIVE_OUTPUT_NAMES):
            raise StationStepError('请先由 PLC 读取并复位本次完成反馈，再解除锁定', AlarmSource.DEVICE)
        if trigger in ('rack_trigger', 'foam_trigger') or (
            trigger == 'position_trigger' and 'values' not in pending
        ) or (trigger == 'mark_trigger' and not pending.get('product_id')):
            cycle.io_state.pop('pending', None)
            cycle.io_state.get('channels', {}).pop(trigger, None)
            queue = cycle.io_state.get('listener_queue', [])
            if pending in queue:
                queue.remove(pending)
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
