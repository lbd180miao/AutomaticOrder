# 延锋 YFPO MES（SOAP）接入说明

对接甲方《注塑封箱测试用例.xlsx》的 3 个 WCF(SOAP) 接口，已在本项目内落地。共用端点
`http://<MES主机>:10133/BaseService.svc`（`?wsdl` 仅用于查看契约，运行时自动去掉），操作 `InvokeMethod`，
业务参数放在 `<yfpo:Data>` 的 JSON 字符串里；成功需**外层 `<a:Status>200</a:Status>` 且内层 Data `Status=true`**。

## 一、接口与本项目映射

| Code | 含义 | Data 入参 | Data 出参要点 | 项目方法 / MesAction | 触发点 |
|---|---|---|---|---|---|
| 20260801 | 料架待装箱校验 | FactoryCode,ProdLineCode,RackCode | Status、RackStatus、HUQty(已装)、HUMaxQty(容量)、IsSealed、Message | `get_rack_recipe` / GET_RACK_RECIPE | 料框扫码（workflow / station_service / 手动改料框） |
| 20260802 | 条码绑定料架 | +Barcode | PartNo、HUQty、IsFull、Message | `upload_product_barcode` / UPLOAD_PRODUCT_BARCODE | BARCODE_READ→MES_UPLOADED |
| 20260803 | 封箱生成区位号 | 同 01 | BinCode(可空)、IsNotTask、TaskGuid、Message | `upload_boxing_result` / UPLOAD_BOXING_RESULT | 整框装箱 `_boxing_trigger`（BinCode 已写入事件） |

## 二、本次改动清单

新增：
- `apps/mes/yfpo_soap_client.py`：`YfpoSoapMesClient`（MesClient 的第三种实现），负责信封拼装、回执解析、两层成功判定、失败不抛异常。
- `apps/mes/test_yfpo_soap_client.py`、`apps/production/test_recipe_sync.py`：单元/页面测试。

修改：
- `AutomaticOrder/settings.py`：`AUTOMATIC_ORDER` 新增 `MES_PROTOCOL`(默认 rest)、`MES_FACTORY_CODE`(2230)、`MES_PROD_LINE_CODE`(I308)、`MES_SOAP_ACTION`(默认空)。
- `apps/mes/services.py`：`get_mes_client()` 增加 `MES_PROTOCOL=='soap'` 分支（REST 路径不变，模拟开关仍最优先）；新增 `describe_mes_runtime()` 供前端只读展示。
- `apps/production/services.py`：新增 `resolve_local_recipe()` / `sync_recipe_from_mes()`，统一“MES 返回配方→落库”和“MES 仅校验→回退本地配方”两条路径；手动改料框时对 `IsSealed=true` 直接拦截。
- `apps/workflow/services.py`、`apps/workflow/station_service.py`：料架校验改为先过 MES 闸门（失败/已封箱即锁定），再用 `sync_recipe_from_mes` 取配方；封箱上传时记录返回的 BinCode。
- `apps/mes/views.py`、`templates/mes/record_list.html`：MES 工作台新增「接口联调」页签（运行配置只读卡片 + 三个接口手动调用），「接口记录」结果列新增已装/容量/零件号/区位号等字段小标签；顺带修正配方页一处文案以对齐既有测试。

**无数据库迁移、无新增第三方依赖**（requests 已在 requirements）。

## 三、如何启用

在环境变量（或部署配置）中设置后重启服务：

```
MES_PROTOCOL=soap
MES_BASE_URL=http://<MES主机>:10133/BaseService.svc?wsdl
MES_FACTORY_CODE=2230
MES_PROD_LINE_CODE=I308
# 仅当现场要求显式 SOAPAction 时再填（从 WSDL 的 soapAction 读取）
# MES_SOAP_ACTION=...
```

不设置时保持原行为（`MES_PROTOCOL=rest`；未配地址或 `USE_SIMULATED_DEVICES=true` 时用模拟客户端）。

联调：打开「MES → 接口联调」，选接口、填料框码（20260802 再填条码），点“发送调用”，
页面直接展示业务字段与原始 JSON，同时写入「接口记录」，失败可在该页重传。

## 四、关键设计说明：20260801 不返回配方几何

甲方 20260801 只回“能否装箱 + 已装/容量 + 是否已封箱”，**不回层数/层距/公差等配方**。
因此 SOAP 客户端不伪造 `recipe`；配方按 `sync_recipe_from_mes` 回退本地 `RackRecipe`：
料框已绑 → 同 `rack_type` 唯一启用配方 → 全局唯一启用配方；仍无法唯一确定时不臆测，
流程锁定并提示“请先在配方页维护并绑定”。如甲方另有配方/BOM 接口，可在该方法内扩展。

## 五、待甲方确认

1. `接口1：RackStatus`、接口3：`IsNotTask` 的完整枚举含义；
2. 是否要求显式 `SOAPAction`（空 action 是否被 WCF 接受）；
3. 是否另有配方/BOM 查询接口（决定配方来源）；
4. `Id/TaskId` 是否要求全局唯一或回传（当前每次新生成 GUID、Id=TaskId，与示例一致）；
5. 工厂码/产线是全厂固定还是按工位可切换（当前走全局配置）。





**第 1 点（RackStatus / IsNotTask 枚举含义）**—— 你已知道：返回参数的具体取值含义未定义。补充一句为什么它重要：`rack_status` 直接决定上层 "能不能装箱" 的分支（现在测试样例里 `RackStatus=1` 对应 "已装 26/74、未封箱" 这种状态），猜错含义流程就会误判。

**第 2 点：是否要求显式 SOAPAction？**

SOAP 1.1 协议里 `SOAPAction` 是 HTTP 头，规范上 "必须存在但允许空值"。但很多 WCF 服务部署时按 action 做严格路由 / 校验 —— 如果甲方服务配了校验，你发空值（当前代码默认发 `SOAPAction: ""`）请求会被直接拒掉。确认方法很简单：打开 `BaseService.svc?wsdl`，看每个 operation 的 `soapAction` 属性是否非空，非空就填进 `MES_SOAP_ACTION` 配置。不确认的风险：**联调时所有请求都打不进去，且表现为 HTTP 层失败，很容易误判成网络问题**。

**第 3 点：是否另有配方 / BOM 查询接口？**

20260801 只回 "能否装箱 + 数量"，**不回层高 / 层距 / 公差**。现在项目的配方来源是本地回退：料框已绑 → 同 `rack_type` 唯一启用配方 → 全局唯一启用配方，仍无法唯一确定就锁流程让人工维护。问题在于：本地配方和 MES 权威数据可能不一致；而且同类型多配方时根本无法自动确定。如果甲方有配方 / BOM 接口，就能拿到权威数据源。不确认的风险：**配方比对（2D/3D 实测 vs 配方）用了不准的基准，视觉校验形同虚设**。

**第 4 点：Id/TaskId 是否要求全局唯一或回传？**

当前实现每次调用生成一个全新 GUID（`uuid4().upper()`），且 `Id = TaskId`，这是照甲方示例做的。需要确认：MES 是否拿 Id 做**幂等 / 去重 / 日志追踪**？如果是，重复或格式不对会导致请求被拒，或排查问题时无法按 Id 关联到 MES 侧日志；"回传" 则指 MES 是否要求你保存这次调用的 Id 以便对账。不确认的风险：**联调能通，但生产环境出现重复提交时无法去重，出问题也追不到日志**。

**第 5 点：工厂码 / 产线是全局固定还是按工位切换？**

当前 `YfpoSoapMesClient` 构造时写死 `factory_code=2230`、`prod_line_code=I308`，所有请求都用这一组值。如果现场是**多工厂 / 多产线**，不同工位归属不同，全局固定值会把所有绑定、封箱记录挂到同一工厂产线下。不确认的风险：**MES 侧统计、追溯全部错账，且线上很难发现**—— 这属于最危险的一类。





## 六、验证

`python manage.py test apps.mes apps.production apps.workflow` 全部通过（含新增 SOAP、
配方回退、联调页渲染用例），`python manage.py check` 无问题。
