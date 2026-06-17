"""MES 客户端抽象与模拟实现。

前期按抽象动作设计，不绑定具体 MES 协议。后期替换为 HTTP / WebService /
数据库中间表 / 文件接口的真实实现即可。
"""


class MesClient:
    """MES client interface. Replace methods with the plant-specific API."""

    def get_rack_recipe(self, rack_code):
        raise NotImplementedError

    def upload_product_barcode(self, product_code, rack_code):
        raise NotImplementedError

    def upload_boxing_result(self, payload):
        raise NotImplementedError

    def upload_vision_result(self, payload):
        raise NotImplementedError

    def upload_alarm(self, payload):
        raise NotImplementedError


class SimulatedMesClient(MesClient):
    """模拟 MES：返回固定配方与成功响应，可通过构造参数注入失败用于测试。"""

    def __init__(self, *, fail_actions=None, recipe_overrides=None):
        # fail_actions：需要模拟失败的动作集合（MesAction 值）。
        self.fail_actions = set(fail_actions or [])
        self.recipe_overrides = recipe_overrides or {}

    def _fail(self, action):
        return action in self.fail_actions

    def get_rack_recipe(self, rack_code):
        from apps.core.constants import MesAction

        if self._fail(MesAction.GET_RACK_RECIPE):
            return {'success': False, 'error': f'MES 未找到料框 {rack_code} 的配方'}

        recipe = {
            'recipe_code': f'RCP-{rack_code}',
            'name': f'{rack_code} 默认配方',
            'rack_type': 'STANDARD',
            'layer_count': 4,
            'quantity_per_layer': 6,
            'total_quantity': 24,
            'layer_height': 120.0,
            'layer_spacing': 150.0,
            'tolerance_x': 2.0,
            'tolerance_y': 2.0,
            'tolerance_z': 3.0,
        }
        recipe.update(self.recipe_overrides)
        return {'success': True, 'recipe': recipe}

    def upload_product_barcode(self, product_code, rack_code):
        from apps.core.constants import MesAction

        if self._fail(MesAction.UPLOAD_PRODUCT_BARCODE):
            return {'success': False, 'error': 'MES 上传条码失败'}
        return {'success': True, 'mes_id': f'MES-{product_code}'}

    def upload_boxing_result(self, payload):
        from apps.core.constants import MesAction

        if self._fail(MesAction.UPLOAD_BOXING_RESULT):
            return {'success': False, 'error': 'MES 上传装箱结果失败'}
        return {'success': True}

    def upload_vision_result(self, payload):
        from apps.core.constants import MesAction

        if self._fail(MesAction.UPLOAD_VISION_RESULT):
            return {'success': False, 'error': 'MES 上传视觉结果失败'}
        return {'success': True}

    def upload_alarm(self, payload):
        from apps.core.constants import MesAction

        if self._fail(MesAction.UPLOAD_ALARM):
            return {'success': False, 'error': 'MES 上传报警失败'}
        return {'success': True}
