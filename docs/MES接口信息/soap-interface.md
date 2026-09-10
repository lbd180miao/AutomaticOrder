# YFPO SOAP MES接口集成文档

### 1. `header_config` 示例

```json
{
  "content_type": "text/xml; charset=utf-8",
  "soap_action": "http://tempuri.org/IWebService/GetData",
  "authorization": "Basic dXNlcjpwYXNz",
  "custom_headers": {
    "X-Factory": "F01"
  }
}
```

- `content_type` 默认为 `text/xml; charset=utf-8`。
- `soap_action` 非空时会附加 `SOAPAction` HTTP 头。
- `authorization` 非空时会附加 `Authorization` 头。
- `custom_headers` 中的键值对会原样加入请求头。

YFPO 项目通过 `MES_CONTENT_TYPE`、代码内置的 `SOAPAction`、`MES_AUTHORIZATION` 和
`MES_CUSTOM_HEADERS` 环境变量提供上述配置；其中 `MES_CUSTOM_HEADERS` 为 JSON 对象。
甲方已确认的 SOAPAction 已写入代码：`http://tempuri.org/IBaseService/InvokeMethod`，无需配置环境变量。

## 2. 多语言调用示例

以下示例演示如何以普通 HTTP 客户端向同一 SOAP 服务端发送请求，与 Plug Client 行为等价。

### 2.1 Python

```python
import requests
import uuid
from datetime import datetime

url = "http://mes.example.com/api/WorkOrderService.asmx"
headers = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "http://tempuri.org/IWorkOrderService/GetWorkOrderInfo"
}

work_order = "SO2024001"
material_code = "MAT-888"

xml = f"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetWorkOrderInfo xmlns="http://tempuri.org/">
      <WorkOrder>"{work_order}"</WorkOrder>
      <MaterialCode>"{material_code}"</MaterialCode>
      <RequestTime>"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"</RequestTime>
      <RequestId>"{uuid.uuid4()}"</RequestId>
    </GetWorkOrderInfo>
  </soap:Body>
</soap:Envelope>"""

resp = requests.post(url, data=xml.encode("utf-8"), headers=headers)
print(resp.status_code)
print(resp.text)
```

### 8.2 C#（HttpClient）

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;

var client = new HttpClient();
var url = "http://mes.example.com/api/WorkOrderService.asmx";

var xml = $@"<soap:Envelope xmlns:soap=""http://schemas.xmlsoap.org/soap/envelope/"">
  <soap:Body>
    <GetWorkOrderInfo xmlns=""http://tempuri.org/"">
      <WorkOrder>""SO2024001""</WorkOrder>
      <MaterialCode>""MAT-888""</MaterialCode>
      <RequestTime>""{DateTime.Now:yyyy-MM-ddTHH:mm:ss}""</RequestTime>
      <RequestId>""{Guid.NewGuid()}""</RequestId>
    </GetWorkOrderInfo>
  </soap:Body>
</soap:Envelope>";

var content = new StringContent(xml, Encoding.UTF8, "text/xml");
content.Headers.Add("SOAPAction", "http://tempuri.org/IWorkOrderService/GetWorkOrderInfo");

var resp = await client.PostAsync(url, content);
Console.WriteLine(await resp.Content.ReadAsStringAsync());
```

### 8.3 Java（OkHttp）

```java
import okhttp3.*;
import java.util.UUID;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class SoapExample {
    public static void main(String[] args) throws Exception {
        String url = "http://mes.example.com/api/WorkOrderService.asmx";
        String xml = "<soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\">" +
            "<soap:Body>" +
            "<GetWorkOrderInfo xmlns=\"http://tempuri.org/\">" +
            "<WorkOrder>\"SO2024001\"</WorkOrder>" +
            "<MaterialCode>\"MAT-888\"</MaterialCode>" +
            "<RequestTime>\"" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")) + "\"</RequestTime>" +
            "<RequestId>\"" + UUID.randomUUID() + "\"</RequestId>" +
            "</GetWorkOrderInfo>" +
            "</soap:Body>" +
            "</soap:Envelope>";

        RequestBody body = RequestBody.create(xml, MediaType.parse("text/xml; charset=utf-8"));
        Request request = new Request.Builder()
            .url(url)
            .post(body)
            .header("SOAPAction", "http://tempuri.org/IWorkOrderService/GetWorkOrderInfo")
            .build();

        try (Response resp = new OkHttpClient().newCall(request).execute()) {
            System.out.println(resp.body().string());
        }
    }
}
```

### 8.4 JavaScript / Node.js

```javascript
const axios = require('axios');

const url = 'http://mes.example.com/api/WorkOrderService.asmx';
const now = new Date().toISOString().slice(0, 19).replace('T', ' ').replace(/-/g, '-');

const xml = `<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetWorkOrderInfo xmlns="http://tempuri.org/">
      <WorkOrder>"SO2024001"</WorkOrder>
      <MaterialCode>"MAT-888"</MaterialCode>
      <RequestTime>"${new Date().toISOString().slice(0, 19).replace('T', ' ')}"</RequestTime>
      <RequestId>"${crypto.randomUUID()}"</RequestId>
    </GetWorkOrderInfo>
  </soap:Body>
</soap:Envelope>`;

axios.post(url, xml, {
  headers: {
    'Content-Type': 'text/xml; charset=utf-8',
    'SOAPAction': 'http://tempuri.org/IWorkOrderService/GetWorkOrderInfo'
  }
}).then(r => console.log(r.data));
```

---

## 9. 响应格式约定

为使 Plug Client 正确解析，SOAP 服务端返回的 XML 应包含可被定位的 `<Data>` 节点，且其内容为合法 JSON。

### 9.1 推荐响应格式

```xml
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetWorkOrderInfoResponse xmlns="http://tempuri.org/">
      <GetWorkOrderInfoResult>
        <Code>200</Code>
        <Message>success</Message>
        <Data>{"WorkOrderResult":"SO2024001-OK"}</Data>
      </GetWorkOrderInfoResult>
    </GetWorkOrderInfoResponse>
  </soap:Body>
</soap:Envelope>
```

### 9.2 CDATA 兼容格式

```xml
<Data><![CDATA[{"WorkOrderResult":"SO2024001-OK"}]]></Data>
```

---

## 10. 常见问题

### Q1: 为什么 string 类型值被加了双引号？

这是 `soap_serialize_value` 的设计：将 `field_type="string"` 的值序列化为 `"值"`，以兼容 JSON-in-XML 的响应解析。若服务端不需要引号，可将 `field_type` 设为 `text` 等非 `string` 类型，或调整服务端解析逻辑。

### Q3: 响应写入失败？

- 确认响应 XML 中 `<Data>` 节点存在且内容为合法 JSON；
- 确认 `response_structure.bindings` 中的 `name` 与 JSON 字段名一致；
### Q4: 是否支持 SOAP 1.2？

当前实现不校验 SOAP 版本，主要使用 `text/xml` Content-Type 与 `SOAPAction` 头。若服务端要求 SOAP 1.2，可将 `content_type` 设为 `application/soap+xml; charset=utf-8`，并视情况在 `custom_headers` 中增加 `action`。
