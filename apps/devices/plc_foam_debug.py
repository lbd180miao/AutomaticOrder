"""2D foam inspection handshake using the shared PLC debug ownership lease."""
import time

from django.conf import settings


def get_recipe(recipe_id):
    from apps.vision.models import VisionRecipe
    from apps.vision.recipe_utils import build_foam_inspection_config, get_foam_standard_template_status
    recipe = VisionRecipe.objects.get(pk=recipe_id, recipe_type='FOAM_2D', is_active=True)
    if not all((recipe.roi_config or {}).get(key) for key in ('leftFoamROI', 'rightFoamROI')):
        raise ValueError('请先完成2D配方左右泡棉ROI示教')
    build_foam_inspection_config(recipe)
    if not get_foam_standard_template_status(recipe)['ready']:
        raise ValueError('请先完成2D配方标准模板示教')
    return recipe


def capture_foam(recipe_id):
    from apps.vision.algorithms.foam_inspector import FoamInspector
    from apps.vision.services import VisionService
    recipe = get_recipe(recipe_id)
    simulated = getattr(settings, 'AUTOMATIC_ORDER', {}).get('USE_SIMULATED_DEVICES', True)
    result = VisionService(foam_inspector=FoamInspector(simulate=simulated)).inspect_foam(
        product=None, rack=None, position_index=recipe.pos,
        use_camera=True, recipe_id=recipe.pk, use_recipe=True,
    )
    return {'result_id': result.pk, 'is_passed': result.is_passed,
            'score': float(result.score), 'defect_type': result.defect_type}


def step(state, plc, capture=capture_foam, save=lambda: None):
    plc.tick_heartbeat()
    trigger = plc.read_point('foam_trigger')
    state['trigger'] = trigger
    phase = state['phase']
    if phase == 'ARMING':
        if not trigger:
            state['phase'] = 'WAIT_TRIGGER'
        return
    if phase in ('WAIT_ACK', 'WAIT_RESET'):
        if not plc.read_point('foam_done'):
            state.update(phase='WAIT_TRIGGER', message='等待下一次 2D 触发')
            save()
        return
    if phase == 'WAIT_TRIGGER' and (not trigger or plc.read_point('foam_done')):
        return
    if phase == 'CAPTURING':
        state['pending_result'] = {'is_passed': False, 'error': '上次采集被中断，请确认后重新触发'}
    elif phase != 'WRITE_PENDING':
        state.update(phase='CAPTURING', done=False, ok=False, error='', result_id=None,
                     score=None, defect_type='', message='正在拍照并检测泡棉')
        save()
        plc.write_point('foam_passed', False)
        plc.write_point('foam_trigger', False)
        state['trigger'] = False
        try:
            result = capture(state['recipe_id'])
            if type(result.get('is_passed')) is not bool:
                raise ValueError('泡棉检测未返回有效结果')
        except Exception as exc:
            result = {'is_passed': False, 'error': str(exc)}
        state['pending_result'] = result
    state['phase'] = 'WRITE_PENDING'
    save()
    result = state['pending_result']
    try:
        plc.write_point('foam_passed', result['is_passed'])
        if plc.read_point('foam_passed') != result['is_passed']:
            raise ValueError('泡棉结果写后回读不一致')
        # PLC may immediately consume/reset completion: do not require it to stay high.
        plc.write_point('foam_done', True)
    except Exception as exc:
        state.update(error=str(exc), message='保留本次检测结果，等待重试回写')
        save()
        raise
    state.update(phase='WAIT_ACK', ok=result['is_passed'], done=True,
                 result_id=result.get('result_id'), score=result.get('score'),
                 defect_type=result.get('defect_type', ''), error=result.get('error', ''),
                 count=state.get('count', 0)+1, completed_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                 message='检测完成，等待 PLC 读取并复位 74.0')
    state.pop('pending_result', None)
    save()
