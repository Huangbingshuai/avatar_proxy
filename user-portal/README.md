# Avatar Studio 用户门户

这是面向 API 用户部署的独立 React/Vite 前端，不包含项目或 API Key 管理功能。

用户使用管理员签发的 `vap_live_...` 业务 Key 连接项目后，可以：

- 创建、重命名和删除项目素材库；
- 上传、查询、重命名和删除图片素材；
- 在视频创作时选择一张状态为“可用”的素材，或仅使用提示词生成；
- 通过 `/api/v3/contents/generations/tasks` 查询、取消、预览和下载 Seedance 视频任务；
- 在“模型测试”中查看当前业务 Key 所属项目已启用的模型，并发起文本、图片或视频中转测试。

图片上传会自动完成对象存储中转和火山素材入库。页面不会要求用户填写公开图片 URL、Asset ID 或 `projectName`。

模型测试直接使用当前登录的业务 Key；文本和图片调用 `/v1/*`，Seedance 视频调用火山兼容的 `/api/v3/contents/generations/tasks`。项目启用模型后，项目下所有有效业务 Key 自动可用。文本模型默认使用 SSE 流式输出并支持手动停止；视觉模型可填写图片 URL 识图；Seedream 可填写参考图进行改图；视频模型保持异步任务模式。参考图输入会按照服务端返回的模型能力显示。模型列表以服务端返回结果为准，测试请求会产生真实供应商用量；页面不会展示或额外持久化完整 Key。

视频任务列表只在当前浏览器中保存任务 ID 和创作元数据；任务状态、结果和权限仍由中转站实时校验。清空页面任务记录不会取消上游任务或删除结果文件。

素材组和图片列表使用当前标签页的浏览器缓存：缓存有效期为 10 分钟，页面会先显示缓存内容，再在后台同步最新数据。创建、修改、删除或上传素材后，对应缓存会自动失效。

## 本地启动

```powershell
cd user-portal
Copy-Item .env.example .env.local
npm install
npm run dev
```

默认地址：`http://localhost:3002`。

## 生产配置

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

执行 `npm run build` 后，将 `dist/` 部署到任意静态站点服务。API 服务器的 `CORS_ORIGINS` 必须包含用户门户域名。
