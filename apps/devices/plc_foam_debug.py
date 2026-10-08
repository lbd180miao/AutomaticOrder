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
    if time.time() - state.get('heartbeat_at', 0) >= 1:
        plc.tick_heartbeat()
        state['heartbeat_at'] = time.time()
    trigger = plc.read_point('foam_trigger')
    state['trigger'] = trigger

    def write_verified(name, value):
        plc.write_point(name, value)
        if plc.read_point(name) is not value:
            raise ValueError(f'{name} 写后回读不一致')

    if not trigger:
        write_verified('foam_done', False)
        write_verified('foam_passed', False)
        state.update(phase='WAIT_TRIGGER', done=False, ok=False, message='等待 PLC 2D 泡棉检测触发')
        return
    if state['phase'] in ('ARMING', 'WAIT_RESET', 'CAPTURING'):
        state['message'] = '等待 PLC 将 DB2.DBX46.3 复位为 0'
        return
    state.update(phase='CAPTURING', done=False, ok=False, error='', result_id=None,
                 score=None, defect_type='', message='正在拍照并检测泡棉')
    save()
    try:
        write_verified('foam_done', False)
        write_verified('foam_passed', False)
        try:
            result = capture(state['recipe_id'])
            if type(result.get('is_passed')) is not bool:
                raise ValueError('泡棉检测未返回有效结果')
            state.update(result_id=result.get('result_id'), score=result.get('score'),
                         defect_type=result.get('defect_type', ''))
            passed = result['is_passed']
        except Exception as exc:
            passed = False
            state['error'] = str(exc)
        write_verified('foam_passed', passed)
        # DBX62.0 acknowledges completion for both OK and NG; only 62.1 is the verdict.
        write_verified('foam_done', True)
        state.update(ok=passed, done=True, message='检测完成，结果已回写；等待 PLC 复位')
    except Exception as exc:
        state.update(ok=False, done=False, error=(state.get('error', '') + '；PLC回写失败：' + str(exc)).lstrip('；'),
                     message='结果未完整回写，请检查PLC通信')
        raise
    finally:
        state.update(phase='WAIT_RESET', count=state.get('count', 0) + 1,
                     completed_at=time.strftime('%Y-%m-%d %H:%M:%S'))
