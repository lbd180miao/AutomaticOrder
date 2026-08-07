"""MES 客户端：抽象基类 + HTTP 实现 + 模拟实现。

真实客户端对接 http://127.0.0.1:8082/mes/records/ (REST JSON)。
模拟客户端用于开发/测试，通过 settings.AUTOMATIC_ORDER['USE_SIMULATED_DEVICES'] 切换。
"""

import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


# ─────────────────────────── 抽象基类 ───────────────────────────

class MesClient:
    """MES 客户端接口，工厂替换具体实现即可。"""

    def get_rack_recipe(self, rack_code: str) -> dict:
        raise NotImplementedError

    def upload_product_barcode(self, product_code: str, rack_code: str) -> dict:
        raise NotImplementedError

    def upload_boxing_result(self, payload: dict) -> dict:
        raise NotImplementedError

    def upload_vision_result(self, payload: dict) -> dict:
        raise NotImplementedError

    def upload_alarm(self, payload: dict) -> dict:
        raise NotImplementedError


# ─────────────────────────── HTTP 真实客户端 ───────────────────────────

class HttpMesClient(MesClient):
    """
    通过 HTTP POST 对接工厂 MES REST 接口。

    MES 接口约定（基于 http://127.0.0.1:8082/mes/records/）：
      POST /mes/records/
      Content-Type: application/json
      Body: { "action": "<动作>", "payload": { ... } }

      成功响应 (2xx): { "success": true, ... }
      失败响应 (4xx/5xx 或 success=false): { "success": false, "error": "..." }
    """

    def __init__(self, base_url: str, timeout: int = 8, token: str = None):
        self.base_url = base_url.rstrip('/') + '/'
        self.timeout = timeout
        self.token = token
        self._session = None

    def _get_session(self):
        """懒加载 requests.Session，复用 TCP 连接。"""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({'Content-Type': 'application/json'})
            if self.token:
                self._session.headers['Authorization'] = f'Bearer {self.token}'
        return self._session

    def _post(self, action: str, payload: dict) -> dict:
        """通用 POST 到 /mes/records/ 并统一处理异常。"""
        import requests
        url = urljoin(self.base_url, 'mes/records/')
        body = {'action': action, 'payload': payload}
        try:
            resp = self._get_session().post(url, json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            # 兼容 MES 返回 success 字段或 HTTP 2xx 即视为成功
            if 'success' not in data:
                data['success'] = True
            return data
        except requests.exceptions.ConnectionError as e:
            logger.error('[MES] 连接失败 action=%s: %s', action, e)
            return {'success': False, 'error': f'MES 连接失败: {e}'}
        except requests.exceptions.Timeout:
            logger.error('[MES] 请求超时 action=%s (timeout=%ss)', action, self.timeout)
            return {'success': False, 'error': f'MES 请求超时 ({self.timeout}s)'}
        except requests.exceptions.HTTPError as e:
            logger.error('[MES] HTTP 错误 action=%s: %s', action, e)
            try:
                error_detail = e.response.json().get('error', str(e))
            except Exception:
                error_detail = str(e)
            return {'success': False, 'error': f'MES HTTP 错误: {error_detail}'}
        except Exception as e:
            logger.exception('[MES] 未知错误 action=%s', action)
            return {'success': False, 'error': f'MES 未知错误: {e}'}

    # ── 具体动作 ─────────────────────────────────────

    def get_rack_recipe(self, rack_code: str) -> dict:
        return self._post('GET_RACK_RECIPE', {'rack_code': rack_code})

    def upload_product_barcode(self, product_code: str, rack_code: str) -> dict:
        return self._post('UPLOAD_PRODUCT_BARCODE', {
            'product_code': product_code,
            'rack_code': rack_code,
        })

    def upload_boxing_result(self, payload: dict) -> dict:
        return self._post('UPLOAD_BOXING_RESULT', payload)

    def upload_vision_result(self, payload: dict) -> dict:
        return self._post('UPLOAD_VISION_RESULT', payload)

    def upload_alarm(self, payload: dict) -> dict:
        return self._post('UPLOAD_ALARM', payload)


# ─────────────────────────── 模拟客户端 ───────────────────────────

class SimulatedMesClient(MesClient):
    """模拟 MES：返回固定配方与成功响应，可注入失败用于测试。"""

    def __init__(self, *, fail_actions=None, recipe_overrides=None):
        self.fail_actions = set(fail_actions or [])
        self.recipe_overrides = recipe_overrides or {}

    def _fail(self, action: str) -> bool:
        return action in self.fail_actions

    def get_rack_recipe(self, rack_code: str) -> dict:
        if self._fail('GET_RACK_RECIPE'):
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

    def upload_product_barcode(self, product_code: str, rack_code: str) -> dict:
        if self._fail('UPLOAD_PRODUCT_BARCODE'):
            return {'success': False, 'error': 'MES 上传条码失败'}
        return {'success': True, 'mes_id': f'MES-{product_code}'}

    def upload_boxing_result(self, payload: dict) -> dict:
        if self._fail('UPLOAD_BOXING_RESULT'):
            return {'success': False, 'error': 'MES 上传装箱结果失败'}
        return {'success': True}

    def upload_vision_result(self, payload: dict) -> dict:
        if self._fail('UPLOAD_VISION_RESULT'):
            return {'success': False, 'error': 'MES 上传视觉结果失败'}
        return {'success': True}

    def upload_alarm(self, payload: dict) -> dict:
        if self._fail('UPLOAD_ALARM'):
            return {'success': False, 'error': 'MES 上传报警失败'}
        return {'success': True}
