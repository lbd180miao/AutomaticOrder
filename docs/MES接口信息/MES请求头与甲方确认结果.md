# YFPO SOAP MES 请求头与甲方确认结果

本说明记录当前确认结果，替代旧接入说明中对应的“待甲方确认”条目。

### 1. `header_config` 示例

```json
{
  "content_type": "text/xml; charset=utf-8",
  "soap_action": "http://tempuri.org/IBaseService/InvokeMethod",
  "authorization": "<甲方提供的认证值；不需要认证时留空>",
  "custom_headers": {
    "X-Factory": "2230"
  }
}
```

认证值是占位符，不能直接用于生产；X-Factory 只是自定义头示例，不是甲方确认的必填头。
`GetData`、`GetWorkOrderInfo` 示例操作也不能替代本项目的 `InvokeMethod`。

| 配置字段 | 项目环境变量 | 请求行为 |
|---|---|---|
| content_type | MES_CONTENT_TYPE | 默认发送 text/xml; charset=utf-8 |
| soap_action | 代码固定 | 始终发送 `http://tempuri.org/IBaseService/InvokeMethod`（带双引号） |
| authorization | MES_AUTHORIZATION | 非空时原样发送 Authorization，前端仅显示是否配置 |
| custom_headers | MES_CUSTOM_HEADERS | JSON 字符串键值对对象，原样合入请求头；同名头覆盖默认值 |

修改环境变量后重启服务。MES_CUSTOM_HEADERS 格式错误会明确报错，不会静默丢弃配置。
甲方已确认 InvokeMethod 的完整 SOAPAction 为 `http://tempuri.org/IBaseService/InvokeMethod`，项目已写死并始终发送。

### 2. 甲方确认的业务字段

| 字段 | 值 | 含义 |
|---|---|---|
| RackStatus | 1 | 可用 |
| RackStatus | 0 | 禁用 |
| RackStatus | 2 | 隔离 |
| RackStatus | 9 | 不可用 |
| IsNotTask | 0 | 有拉动任务 |
| IsNotTask | 1 | 无拉动任务 |

20260801 必须业务通过、RackStatus=1 且 IsSealed=false 才允许装箱；未知或缺失状态不会放行。
20260803 的 IsNotTask 表示拉动任务是否存在，不代表封箱成功与否，也不保证有任务就一定返回非空区位号。
封箱成功以外层 Status=200 且内层 Status=true 判定；BinCode、TaskGuid 按实际返回保存至 MesRecord。
前端显示原始枚举值及中文含义。

### 3. 其余接入约定

- 工厂码 2230、产线 I308 暂时为全局固定配置。
- 每次调用生成新的 GUID，Id 与 TaskId 相同，不回传上次值。
- 配方/BOM/工艺参数查询属于后续新需求，当前继续使用本地配方匹配。
- SOAP 端点为 BaseService.svc，操作为 InvokeMethod，Data 使用 JSON 字符串。
- 本次测试使用假 HTTP session 验证请求头及业务状态，未连接甲方 MES。
