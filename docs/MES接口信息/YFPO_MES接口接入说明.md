# YFPO MES（SOAP）接口接入说明 —— AutomaticOrder

> 对应甲方《注塑封箱测试用例.xlsx》，共 **3 个同构接口**，共用同一个 WCF(SOAP) 端点
> `http://<MES主机>:10133/BaseService.svc`，操作名 `InvokeMethod`，仅业务代码 `Code` 与 `Data`(JSON 字符串) 不同。

---

## 一、从甲方示例里提取到的有用信息

### 1. 甲方确认结果

- `RackStatus`：`1` 可用、`0` 禁用、`2` 隔离、`9` 不可用。只有可用料架允许继续装箱。
- `IsNotTask`：是否存在拉动任务；`0` 有任务并可能返回 `BinCode`，`1` 无任务，`BinCode` 为空。
- SOAP 请求头必须支持 `Content-Type`、`SOAPAction`、`Authorization` 和自定义请求头；`SOAPAction` 使用配置值并在请求中显示发送。
- 暂无独立配方/BOM/工艺参数接口，先使用本地配方回退方案，后续新需求再扩展。
- `Id` 与 `TaskId` 每次生成同一个新 GUID，与甲方示例一致。
- `FactoryCode=2230`、`ProdLineCode=I308` 暂时固定在全局 settings 配置。

### 2. 三个接口一览（它们正好对应你现有的 3 个 MES 动作）

| 业务代码 Code | 接口名 | 含义 | Data 入参 | Data 出参关键字段 | 对应本项目方法 / MesAction | 流程触发点 |
|---|---|---|---|---|---|---|
| **20260801** | CheckIMMRackReadyToPkg | 注塑料架待装箱校验 | FactoryCode, ProdLineCode, RackCode | Status(bool)、RackStatus、HUQty(已装)、HUMaxQty(容量)、IsSealed(已封箱?)、Message | `get_rack_recipe` / GET_RACK_RECIPE | 料框扫码后（station_service / `_on_recipe_loaded`） |
| **20260802** | BindIMMBarcodeToRK | 注塑条码绑定料架 RK | 上面三个 + **Barcode** | Status、Barcode、**PartNo(零件号)**、HUQty、HUMaxQty、**IsFull(装满?)**、Message | `upload_product_barcode` / UPLOAD_PRODUCT_BARCODE | `_on_mes_upload`（BARCODE_READ→MES_UPLOADED） |
| **20260803** | SealIMMRKAndGenBin | 注塑封箱生成区位号 | FactoryCode, ProdLineCode, RackCode | Status、**BinCode(区位号,可空)**、**IsNotTask**、TaskGuid、Message | `upload_boxing_result` / UPLOAD_BOXING_RESULT | 满框封箱时（当前单件流程未挂，需补触发点，见第五节） |

### 2. SOAP/WCF 调用要点（容易踩坑的地方）

- **调用地址要去掉 `?wsdl`**：`?wsdl` 只是给人看契约的元数据；真正 POST 到 `BaseService.svc`。
- **请求**：`POST`，`Content-Type: text/xml; charset=utf-8`，Body 是固定 SOAP 信封；业务参数全部塞在 `<yfpo:Data>` 里的一段 **紧凑 JSON 字符串**（不是 XML 子节点）。
- **信封固定字段**：`Code`=业务代码、`Data`=JSON、`FactoryCode`=工厂码；`Id` 与 `TaskId` 用同一个 GUID；`RT/Sender/Status/TelId` 固定为 `1`；`SenderUrl` 固定 `?`；`TimeStamp/Timestamp` 用当天日期。
- **成功要判两层**（缺一不可）：
  1. 外层 `<a:Status>200</a:Status>` —— WCF 包装层/系统级状态；
  2. 内层 `Data` JSON 的 `"Status": true` —— 业务是否通过；失败原因看内层 `Message`（或外层 `ErrMsg`）。
- **SOAPAction 待确认**：示例只给了 XML Body，没给 HTTP 头。代码默认发空 `SOAPAction: ""`（WCF 通用分发通常接受）；若现场返回 400 / SOAP Fault，需从 WSDL 的 `wsdl:operation/@soapAction` 取真实 action 填进配置（见第六节）。

### 3. 字段示例（来自甲方原文，已用于离线自测）

- 20260801 成功：`HUQty=26.0, HUMaxQty=74.0, IsSealed=false, Message="料架校验通过，可开始装箱"`
- 20260802 成功：`PartNo="12441620", IsFull=false, Message="绑定成功"`
- 20260803 成功：`BinCode="", IsNotTask=1, TaskGuid="", Message="封箱成功，暂无可用区位号"`

---

## 二、本项目现状（为什么这样接最省事）

- `apps/mes/client.py`：抽象 `MesClient` + REST 实现 `HttpMesClient` + 模拟实现 `SimulatedMesClient`；
  统一返回契约是 **`{'success': bool, ...}`，失败 `{'success': False, 'error': ...}`，客户端不抛异常**。
- `apps/mes/services.py`：`get_mes_client()` 按 `settings.AUTOMATIC_ORDER` 选择实现；`MesService` 负责 `MesRecord` 落库、失败重传（`run_mes_retry`）、统计。
- `requests==2.33.1` 已在 `requirements.txt`，**无需新增依赖、无需数据库迁移**（三个动作复用现有 `MesAction` 选项）。

> 结论：**新增一个 `MesClient` 的 SOAP 实现 + 在工厂里加一个协议分支**即可，`MesService` 及以上的 workflow 完全不用改调用方式。

---

## 三、落地步骤

### 步骤 1：新增文件 `apps/mes/yfpo_soap_client.py`
直接用交付目录里的 `yfpo_soap_client.py`（已实现信封拼装、回执解析、两层成功判定、失败不抛异常、可注入 session 便于测试）。

### 步骤 2：在 `apps/mes/services.py` 的 `get_mes_client()` 增加协议分支

把现有函数改成（REST 路径保持不变，纯增量）：

```python
def get_mes_client():
    """按配置返回 MES 客户端实例。"""
    conf = getattr(settings, 'AUTOMATIC_ORDER', {})
    base_url = conf.get('MES_BASE_URL') or ''
    if conf.get('USE_SIMULATED_DEVICES', False) or not base_url.strip() or not base_url.startswith(('http://', 'https://')):
        return SimulatedMesClient()

    timeout = conf.get('MES_TIMEOUT', conf.get('DEVICE_TIMEOUT_SECONDS', 8))
    protocol = (conf.get('MES_PROTOCOL') or 'rest').lower()

    if protocol == 'soap':  # 延锋 YFPO WCF(SOAP)
        from .yfpo_soap_client import YfpoSoapMesClient
        return YfpoSoapMesClient(
            base_url=base_url,
            factory_code=conf.get('MES_FACTORY_CODE', ''),
            prod_line_code=conf.get('MES_PROD_LINE_CODE', ''),
            timeout=timeout,
            soap_action=conf.get('MES_SOAP_ACTION', ''),
        )

    token = conf.get('MES_TOKEN') or None
    return HttpMesClient(base_url=base_url, timeout=timeout, token=token)
```

### 步骤 3：在 `AutomaticOrder/settings.py` 的 `AUTOMATIC_ORDER` 里补 4 项

```python
'MES_PROTOCOL': os.environ.get('MES_PROTOCOL', 'rest'),        # rest=原REST; soap=延锋YFPO SOAP
'MES_FACTORY_CODE': os.environ.get('MES_FACTORY_CODE', '2230'),
'MES_PROD_LINE_CODE': os.environ.get('MES_PROD_LINE_CODE', 'I308'),
'MES_SOAP_ACTION': os.environ.get('MES_SOAP_ACTION', ''),       # 仅当现场要求显式 SOAPAction 时填
# MES_BASE_URL 切 SOAP 时改成： http://<MES主机>:10133/BaseService.svc?wsdl （代码会自动去掉 ?wsdl）
```

### 步骤 4：测试（交付目录里的 `test_yfpo_soap_client.py` 放到 `apps/mes/`）

```bash
.venv\Scripts\python.exe manage.py test apps.mes
```
> 该测试已在你项目里实跑：**8 个用例全部 OK**（含成功/业务拒绝/外层500/坏XML兜底/MesService 落库）。

**不需要 makemigrations/migrate**，也不用改 `MesAction`、`MesRecord`、admin、urls。

---

## 四、关键矛盾：20260801 不返回“配方”，两处消费点必须处理 ⚠️

你现在有 **两处** 把 `get_rack_recipe()` 的返回当成“完整配方”在用，且强制要求一堆几何字段：

- `apps/workflow/services.py::_on_recipe_loaded`（取 `resp['recipe']` 后 `upsert_recipe`）
- `apps/workflow/station_service.py` 约 356–377 行（校验 `recipe_code/name/layer_count/.../layer_spacing` 齐全，缺字段直接报错锁定）

但甲方 **20260801 只回“能不能装箱 + 已装/最大数量 + 是否已封箱”，不回层数、层距、公差等配方几何**。SOAP 客户端因此**故意不返回 `recipe` 键**，不会瞎编。你需要二选一（这是业务决策，建议先和甲方/内部确认）：

- **方案 A（推荐，改动小）**：把“校验”和“配方”解耦——20260801 只做装箱前闸门（`is_sealed` 必须为 False、`rack_status` 合法、用 `hu_qty/hu_max_qty` 显示进度）；配方继续走**本地 `RackRecipe`**（你已有视觉配方/管理页），按料架类型或产品号匹配。
  `station_service.py` 可改成类似：

  ```python
  check = self.mes.get_rack_recipe(rack_code, rack=rack)
  if not check.get('success'):
      raise StationStepError(f'MES 料架校验失败: {check.get("error")}', AlarmSource.MES)
  if check.get('is_sealed'):
      raise StationStepError('料架已封箱，禁止装箱', AlarmSource.MES)
  # 配方改为本地匹配（按 rack_type / 产品号），而不是用 MES 返回的 recipe
  recipe = self.production.find_local_recipe(rack)   # ← 需要你按现有配方来源补这个方法
  if recipe is None:
      raise StationStepError('本地未匹配到装箱配方', AlarmSource.RECIPE)
  self.production.assign_recipe_to_rack(rack, recipe)
  ```
  `_on_recipe_loaded` 同理：先过校验闸门，再从本地取配方。

- **方案 B**：向甲方确认是否**另有**“配方/BOM 查询接口”（这份 Excel 只有校验/绑定/封箱三个）。若有，用它来填 `recipe`，20260801 仍只做闸门。

---

## 五、20260803 封箱接口的触发点要补

`upload_boxing_result`（封箱生成区位号）目前**没有挂在单件产品流程里**（它是“整框”动作，不是单件动作）。建议在“料框装满/人工点封箱”处调用，并把返回的 **BinCode（区位号）落库追溯**：

```python
resp = self.mes.upload_boxing_result({'rack_code': rack.rack_code}, rack=rack)
if resp.get('success'):
    bin_code = resp.get('bin_code', '')          # 空串=暂无区位（配合 is_not_task=1）
    # TODO: 把 bin_code / task_guid 写到 Rack 或追溯表（如需持久化，给 Rack 加字段再迁移）
```

---

## 六、现场联调

1. 设环境变量后启动：
   ```
   set MES_PROTOCOL=soap
   set MES_BASE_URL=http://10.x.x.x:10133/BaseService.svc?wsdl
   set MES_FACTORY_CODE=2230
   set MES_PROD_LINE_CODE=I308
   ```
2. 不跑流程、先单测一发（`manage.py shell`）：
   ```python
   from apps.mes.services import MesService
   print(MesService().get_rack_recipe('INN0117G00'))
   ```
   能看到 `{'success': True, 'hu_qty': 26.0, ...}` 即链路通；每次调用都会在 `MesRecord` 留痕，失败可用现有 `run_mes_retry` 重传。
3. 若返回 400 / SOAP Fault：八成是 SOAPAction。浏览器打开 `MES_BASE_URL`（带 ?wsdl）搜 `soapAction`，把值填到 `MES_SOAP_ACTION`。

---

## 七、需要找甲方确认的清单

1. `RackStatus` 的枚举含义（示例=1，1 是否=可用/待装箱？还有哪些值）。
2. `IsNotTask` 的取值语义（示例=1 且 BinCode 为空，什么情况下=0 并给区位号？）。     RackStatus：RK状态 1可用 0禁用 2隔离 9不可用    IsNotTask：是否存在拉动任务 0有 1没有
3. 真实的 `SOAPAction` 要求（空 action 是否接受）。  显示 `SOAPAction`
4. 是否另有“配方/BOM/工艺参数”查询接口（决定第四节走方案 A 还是 B）。 暂定，新需求
5. `Id/TaskId` 是否要求全局唯一、是否需要回传上一次的值（当前按“每次新生成 GUID、Id=TaskId”实现，与示例一致）。与示例一致
6. 工厂码 `FactoryCode=2230`、产线 `ProdLineCode=I308` 是全厂固定还是按工位可切换（当前走 settings，多工位可改为按工位配置）。暂时固定

---

## 八、交付文件清单

| 文件 | 放到项目哪里 | 作用 |
|---|---|---|
| `yfpo_soap_client.py` | `apps/mes/yfpo_soap_client.py` | YFPO SOAP 客户端（MesClient 的第三种实现） |
| `test_yfpo_soap_client.py` | `apps/mes/test_yfpo_soap_client.py` | 8 个单测（已实跑通过） |
| `offline_verify.py` | 任意处，可不入库 | 不依赖 Django/网络的离线验证脚本 |

验证结果：离线脚本 8 项断言全过；在 AutomaticOrder 真实测试框架下 `apps.mes.test_yfpo_soap_client` **Ran 8 tests OK**。
