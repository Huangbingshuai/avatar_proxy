# Vega 素材与活体接口

[文档首页](../../CLIENT_API.md) · [Vega视频与规格](vega.md) · [鉴权](basics.md) · [错误与重试](errors.md)

仅适用于已开通的Vega视频Pro系列（1.0 Pro/Fast/Mini、1.5 Pro），不支持Lite、Image或VL模型。所有请求使用星辰平台业务Key；JSON中必填model，示例为vega-1.0-pro，请替换为项目实际开通的同一个Pro型号。字段区分大小写，不传SubAppId、SecretId、SecretKey、站点、ExtInfo或回调地址。资源按项目、业务Key和渠道隔离，不可与火山素材混用。

## 素材流程与接口概览

在左侧“Vega（腾讯云点播）→ 素材接口”逐项查阅。展示方式与火山素材接口一致，但使用独立的Vega协议，不共用资源ID，也不虚构供应商未提供的操作。全部为POST JSON。

非真人素材：登记素材（可省略GroupId）→ 查询素材任务 → 保存Output.AssetId和GroupId → 视频中使用asset://引用。国内真人素材：发起活体认证 → 本人完成H5认证 → 查询认证结果取得GroupId → 登记真人素材 → 查询素材任务 → 引用素材。

这些接口不上传本地文件：FileInfo.Url必须是供应商可读取的地址。已有火山上传接口只在配置了对应TOS服务且具有权限时用于取得HTTP(S) URL，不会替代Vega登记步骤。素材、活体及存储可能产生供应商费用，不包含在视频按秒价格中；不要将创建操作作为免费的连通探测。

| 操作 | 路径 |
|---|---|
| [登记素材](#登记素材) | `/v1/vega/CreateAigcMaterial` |
| [查询素材任务](#查询素材任务) | `/v1/vega/DescribeTaskDetail` |
| [查询素材详情](#查询素材详情) | `/v1/vega/DescribeAigcMaterial` |
| [查询素材列表](#查询素材列表) | `/v1/vega/DescribeAigcMaterialList` |
| [修改素材名称](#修改素材名称) | `/v1/vega/ModifyAigcMaterial` |
| [删除素材或素材组](#删除素材或素材组) | `/v1/vega/DeleteAigcMaterial` |
| [查询素材组详情](#查询素材组详情) | `/v1/vega/DescribeAigcMaterialGroup` |
| [修改素材组](#修改素材组) | `/v1/vega/ModifyAigcMaterialGroup` |
| [发起真人活体认证](#发起真人活体认证) | `/v1/vega/CreateAigcLivenessValidate` |
| [查询真人活体结果](#查询真人活体结果) | `/v1/vega/DescribeAigcLivenessValidateResult` |

## 登记素材

`POST /v1/vega/CreateAigcMaterial`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| FileInfo | 是 | object | 必须为Type=Url和Url两个字段；Url为供应商可访问的HTTP(S)地址 |
| AssetType | 是 | string | Image、Video或Audio |
| AssetName | 否 | string | 素材名称，本站上限1024字符，供应商仍可能进一步校验 |
| IsRealPerson | 否 | string | 字符串True或False，默认False；不是JSON布尔值 |
| GroupId | 条件必填 | string | 真人素材必须使用本Key活体认证所得组ID；非真人省略时自动创建隔离组；显式传入须为本Key同渠道登记的组 |
| GroupName | 否 | string | 素材组名称，最多64字符；首次自动建组且未填写时使用本站生成的短名称，后续登记不覆盖已有组名 |
| GroupDescription | 否 | string | 素材组描述，本站上限1024字符，供应商仍可能进一步校验 |

请求头Idempotency-Key必填，长度1～128字符。同一Key、操作、model及请求内容使用同一个幂等键；结果未知时保留原键，不自动重试或换键重提。

### 请求示例

```bash
curl "$BASE_URL/v1/vega/CreateAigcMaterial" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: replace-with-unique-vega-material-create-order" \
  -d '{
  "model": "vega-1.0-pro",
  "FileInfo": {
    "Type": "Url",
    "Url": "https://example.com/reference.png"
  },
  "AssetType": "Image",
  "AssetName": "参考角色",
  "IsRealPerson": "False"
}'
```

### 响应与后续处理

这是异步登记，不是上传文件。将URL替换为真实可访问的媒体地址；保存顶层id，并调用[查询素材任务](vega-materials.md#查询素材任务)直到处理成功。不要把Response.TaskId当作本站任务ID。国内真人素材应先完成活体认证；国际站按供应商约定使用IsRealPerson=False。

```json
{
  "id": "tsk_material_example",
  "Response": {
    "TaskId": "supplier-task-id",
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 查询素材任务

`POST /v1/vega/DescribeTaskDetail`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| TaskId | 是 | string | 登记素材返回的本站顶层id（tsk_开头），不是Response.TaskId；使用创建时相同model和业务Key |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DescribeTaskDetail" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "TaskId": "tsk_material_example"
}'
```

### 响应与后续处理

Response.CreateAigcMaterialTask.Status=FINISH且ErrCode=0，并返回Output.AssetId才表示成功；未完成时继续查询原任务，失败时读取错误信息。提交失败且没有上游任务ID时，返回顶层id/status/error/outcomeUnknown；outcomeUnknown=true表示供应商结果尚待核对，不是确认未创建。创建错误的details.taskId可用于此处查询。重复同一幂等键不会再次创建，勿换键重提。成功后使用asset://加AssetId引用素材。此接口不查询视频任务或活体任务。

```json
{
  "id": "tsk_material_example",
  "Response": {
    "RequestId": "supplier-request-id",
    "CreateAigcMaterialTask": {
      "Status": "FINISH",
      "ErrCode": 0,
      "Output": {
        "AssetId": "asset-example",
        "GroupId": "group-example"
      }
    }
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 查询素材详情

`POST /v1/vega/DescribeAigcMaterial`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| AssetId | 是 | string | 通过本站登记并处理成功的素材ID，不加asset://前缀 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DescribeAigcMaterial" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "AssetId": "asset-example"
}'
```

### 响应与后续处理

Response保留供应商素材详情对象及RequestId，字段以真实返回为准。素材必须属于本项目、业务Key及渠道；未登记、已删除或越权资源返回404。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 查询素材列表

`POST /v1/vega/DescribeAigcMaterialList`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| GroupId | 是 | string | 本站登记返回的本Key同渠道组ID |
| AssetType | 否 | string | Image、Video或Audio；省略时不筛选类型 |
| Limit | 否 | integer | 1～300，默认10 |
| Offset | 否 | integer | 非负整数，必须为Limit的整数倍，默认0 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DescribeAigcMaterialList" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "GroupId": "group-example",
  "AssetType": "Image",
  "Limit": 10,
  "Offset": 0
}'
```

### 响应与后续处理

Response保留供应商列表对象及RequestId，字段以真实返回为准。下一页按Offset增加Limit查询，不能跨Key或渠道列出其他组。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 修改素材名称

`POST /v1/vega/ModifyAigcMaterial`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| AssetId | 是 | string | 本Key同渠道登记的素材ID |
| AssetName | 是 | string | 非空素材名称，本站上限1024字符，供应商仍可能进一步校验 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/ModifyAigcMaterial" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "AssetId": "asset-example",
  "AssetName": "新的角色名称"
}'
```

### 响应与后续处理

Response保留供应商操作结果及RequestId；修改后可查询素材详情核对。不能修改素材媒体内容或转移所有权。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 删除素材或素材组

`POST /v1/vega/DeleteAigcMaterial`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| AssetId | 二选一 | string | 删除单个本Key同渠道素材，不可与GroupId同时传入 |
| GroupId | 二选一 | string | 删除整个本Key同渠道素材组及组内全部素材；不可与AssetId同时传入 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DeleteAigcMaterial" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "AssetId": "asset-example"
}'
```

### 响应与后续处理

删除整个组时，将示例AssetId字段替换为GroupId及真实组ID。此操作使用POST并返回JSON，不是DELETE/204。供应商成功后本站移除对应资源授权，旧asset://引用将不可继续使用；请谨慎执行，不要将删除作为查询探测。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 查询素材组详情

`POST /v1/vega/DescribeAigcMaterialGroup`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| GroupId | 是 | string | 本站登记或活体认证返回的本Key同渠道素材组ID |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DescribeAigcMaterialGroup" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "GroupId": "group-example"
}'
```

### 响应与后续处理

Response保留供应商素材组详情及RequestId，字段以真实返回为准。Vega没有本站独立的创建素材组、枚举全部素材组接口：非真人组随登记素材建立，真人组来自活体认证，不要使用火山素材组接口代替。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 修改素材组

`POST /v1/vega/ModifyAigcMaterialGroup`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| GroupId | 是 | string | 本Key同渠道素材组ID |
| GroupName | 否 | string | 新的组名称，最多64字符；不能将上游历史超长默认组名原样用于修改 |
| GroupDescription | 否 | string | 新的组描述，本站上限1024字符，供应商仍可能进一步校验 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/ModifyAigcMaterialGroup" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "GroupId": "group-example",
  "GroupName": "角色素材",
  "GroupDescription": "项目角色参考素材"
}'
```

### 响应与后续处理

按需传入待修改的GroupName或GroupDescription；Response保留供应商操作结果及RequestId。不能通过此接口创建新组或转移组归属。

```json
{
  "Response": {
    "RequestId": "supplier-request-id"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 发起真人活体认证

`POST /v1/vega/CreateAigcLivenessValidate`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |

请求头Idempotency-Key必填，长度1～128字符。同一Key、操作、model及请求内容使用同一个幂等键；结果未知时保留原键，不自动重试或换键重提。

### 请求示例

```bash
curl "$BASE_URL/v1/vega/CreateAigcLivenessValidate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: replace-with-unique-vega-liveness-create-order" \
  -d '{
  "model": "vega-1.0-pro"
}'
```

### 响应与后续处理

仅国内站Pro系列支持。除model外不传其他请求字段。将真实返回的Response.H5Link交给本人完成认证，保存Response.LivenessToken用于[查询认证结果](vega-materials.md#查询真人活体结果)。示例链接只是结构占位，不是有效认证入口；令牌及链接不得公开分享。

```json
{
  "id": "tsk_liveness_example",
  "Response": {
    "RequestId": "supplier-request-id",
    "LivenessToken": "replace-with-returned-token",
    "H5Link": "https://example.com/replace-with-returned-h5-link"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。

## 查询真人活体结果

`POST /v1/vega/DescribeAigcLivenessValidateResult`

### 请求参数

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| model | 是 | string | 项目已开通的Vega视频Pro型号；同一素材流程保持一致 |
| LivenessToken | 是 | string | 本Key、相同model发起认证后真实返回的令牌 |

### 请求示例

```bash
curl "$BASE_URL/v1/vega/DescribeAigcLivenessValidateResult" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "model": "vega-1.0-pro",
  "LivenessToken": "replace-with-returned-token"
}'
```

### 响应与后续处理

仅国内站Pro系列支持。必须在H5页面完成认证；Response.Status=DONE时保存Response.GroupId，再登记IsRealPerson=True的素材。认证结果查询固定使用发起时的渠道和凭证版本。未完成或失败的状态以供应商实际返回为准，不视为认证成功。

```json
{
  "Response": {
    "RequestId": "supplier-request-id",
    "Status": "DONE",
    "GroupId": "group-example"
  }
}
```

上方为响应结构示例；Response中的业务字段由供应商实际返回，示例ID、URL与令牌必须替换。失败使用本站统一错误结构，非2xx时不要将响应当作成功结果。
