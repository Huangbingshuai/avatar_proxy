# ToB 素材系统额度控制与素材账本设计

## 1. 目标与边界

本阶段为企业客户的素材 API 增加可配置的项目额度、API Key 子额度、素材归属账本和 TOS 孤儿文件清理能力。所有现有项目和 API Key 默认不限额，管理员在控制台启用额度后才生效。

本阶段不实现月度金额预算、客户金额账单、业务 API Key IP 白名单、外部消息告警、多实例分布式限流、全桶扫描、公网 URL 安全专项改造、视频接口改造及线上部署。

## 2. 额度模型

### 2.1 项目额度

每个项目可配置：

- 查询 QPM；
- 写入 QPM；
- 最大写请求并发数；
- 每日成功创建素材数量；
- 每日成功上传文件数量；
- 每日成功上传字节数；
- 平台管理素材总数量；
- 本系统上传的 TOS 总存储量。

字段为空表示不限额。QPM 使用自然分钟窗口，每日额度按北京时间 00:00 重置。

### 2.2 API Key 子额度

API Key 默认继承项目配置，可为查询 QPM、写入 QPM、最大写并发、每日素材数、每日上传文件数和每日上传字节数设置更严格的子额度。实际生效额度取项目与 Key 中更严格的一项，Key 不能放宽项目额度。

### 2.3 计数和拦截

- QPM 统计鉴权成功后的调用尝试，包括参数错误和上游失败。
- 每日素材数仅统计方舟 `CreateAsset` 成功的请求。
- 每日上传量仅统计 TOS 上传成功的文件。
- 公网 URL 素材计入素材数量，不计入 TOS 上传量和存储量。
- 写操作达到硬上限后返回 HTTP 429。
- 查询 QPM 达到 70%、90%、100% 时记录告警，但继续放行。
- 删除不受素材总量和存储总量限制，确保客户可以释放资源。

限流响应包含 `metric`、`scope`、`limit`、`used`、`resetAt` 和 `requestId`。能够自动恢复的窗口同时返回 `Retry-After`。

## 3. 素材账本

素材账本至少记录：

```text
project_name
api_key_id
group_id
asset_id
source_type
source_url
bucket
object_key
size_bytes
status
created_at
deleted_at
```

`source_type` 分为 `tos` 和 `external_url`。状态流转如下：

```text
uploaded_pending -> registering -> active -> deleted
                               \-> registration_failed
active/deleted cleanup failure -> cleanup_pending
```

TOS 上传成功后创建 `uploaded_pending` 记录，并在原响应中新增 `uploadId`。`POST /api/asset/create` 接受可选 `uploadId`；旧客户端没有提供时，服务端按当前项目下完全相同的 URL 匹配待注册上传，无法匹配则按外部 URL 记录。

创建素材前原子预占每日及总素材额度；方舟成功后提交计数并保存 Asset ID，失败则回滚预占。未成功注册的 TOS 文件保留 48 小时供客户端重试，之后由后台维护任务删除。

删除方舟素材成功后，外部 URL 只更新账本；TOS 素材同步删除对象。TOS 删除失败时不让客户端重试已经成功的方舟删除，而是标记 `cleanup_pending` 并由后台重试。只有 TOS 确认删除后才扣减存储量。

## 4. 数据和接口

新增持久化数据：

- `project_quotas`：项目级额度；
- `api_key_quotas`：Key 子额度；
- `quota_usage_windows`：分钟、每日计数及预占；
- `asset_records`：素材和 TOS 对象账本；
- `quota_events`：阈值告警、限流拒绝和确认状态；
- `admin_audit_logs`：真实管理员 ID/用户名、操作结果、配置变更前后值、来源 IP、User-Agent 和时间；
- `admin_users`、`admin_sessions`、`admin_recovery_codes`：两级管理员账号、Argon2id 密码哈希、加密 TOTP 密钥、单次恢复码哈希和服务端会话。IP 只用于审计和会话追溯，不参与登录限制、白名单或权限判断。
- `admin_security_alerts`、`admin_backup_runs`、`admin_restore_runs`：醒目安全告警，以及 SQLite/管理员审计自动备份和数据库恢复执行记录。

新增内部管理接口：

```text
GET  /api/internal/project/quota
PUT  /api/internal/project/quota
GET  /api/internal/apikey/quota
PUT  /api/internal/apikey/quota
GET  /api/internal/quota/usage
GET  /api/internal/quota/events
POST /api/internal/quota/event/ack
```

所有 `/api/internal/*` 接口使用服务端 Session Cookie 鉴权；POST、PUT、DELETE 额外校验 `X-CSRF-Token`，不再接受 `X-Admin-Token`。系统只保留一个由服务器 CLI 初始化的 `super_admin`，强制使用 TOTP，且只能管理管理员账号、会话、告警和备份；删除、重置、启停账号和手工备份必须再次校验超管密码。控制台创建的普通 `admin` 负责项目、API Key、额度和调试功能，但不能访问安全管理。超级管理员登录、密码修改和管理员删除产生安全告警；审计记录真实操作人，来源 IP 仅供追溯。SQLite 与管理员审计 JSONL 按配置定期生成一致性备份。

数据库恢复只允许选择服务器生成的备份，不接收前端上传文件。恢复前必须通过 SQLite 完整性、所需表、唯一启用超管和 TOTP 加密主密钥兼容性校验，并再次验证超管密码、未复用的 TOTP 和确认短语。恢复期间单实例进入维护模式并排空在途操作，先创建回滚快照；失败自动回滚，成功撤销全部会话，整个过程写入审计和 Critical 告警。多实例恢复不在第一期自动化范围内。

## 5. 控制台

项目页增加“额度与用量”入口，展示配置、当前窗口用量、素材数、TOS 存储量、告警和待清理对象。API Key 页增加“子额度”入口，清楚区分继承项目、自定义和不限额状态。

控制台概览增加今日素材数、上传文件和字节、受限项目、未确认额度事件及待清理对象。额度修改立即生效并写入审计日志。

## 6. 后台维护任务

单实例服务启动后运行一次维护任务，此后每小时运行：

- 删除超过 48 小时仍未注册成功的 TOS 文件；
- 重试 `cleanup_pending` 对象；
- 记录成功、失败及重试次数；
- 服务关闭时安全取消任务。

当前架构以单实例 SQLite 为前提。未来横向扩容时，QPM、并发和额度预占需迁移到 Redis 或共享数据库。

## 7. 验收标准

- 旧数据库升级后数据不丢失，现有项目和 Key 默认不限额。
- 项目和 Key 配置立即生效，Key 不能突破项目总额度。
- 写操作超限返回结构化 429；查询超量只产生去重告警。
- 成功操作提交用量，失败操作回滚预占。
- 公网 URL 不计 TOS 存储，跨项目或跨 Key 使用 `uploadId` 被拒绝。
- 删除 TOS 素材释放存储量，删除失败进入后台重试。
- 48 小时未注册文件自动清理。
- 现有项目、Key、素材和上传接口保持兼容。
- 后端测试、控制台构建及本地端到端流程全部通过。

## 8. 发布约束

本阶段只修改和验证本地项目。完成测试与代码提交后仍不部署；只有收到独立、明确的部署指令后，才制定生产迁移和回滚步骤。
