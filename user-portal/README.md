# Avatar Studio 用户门户

这是面向 API 用户部署的独立 React/Vite 前端，不包含项目或 API Key 管理功能。

用户使用管理员签发的 `vap_live_...` 业务 Key 连接项目后，可以：

- 创建、重命名和删除项目素材库；
- 上传、查询、重命名和删除图片素材；
- 在视频创作时选择一张状态为“可用”的素材，或仅使用提示词生成；
- 查询、取消、预览和下载 Seedance 视频任务。

图片上传会自动完成对象存储中转和火山素材入库。页面不会要求用户填写公开图片 URL、Asset ID 或 `projectName`。

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
