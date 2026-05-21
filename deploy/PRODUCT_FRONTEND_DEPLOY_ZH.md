# 产品前端部署（Cloudflare Pages）

目标：部署 `frontend/`（React + Vite + Tailwind）作为产品主页面。

## 1. Cloudflare 创建 Pages 项目
- 选择：`Import an existing Git repository`
- Repo：`austin10231/10k-risk-evolution`

## 2. 构建配置（必须一致）
- Production branch：`test-new-function`
- Framework preset：`Vite`
- Build command：`npm run build`
- Build output directory：`dist`
- Root directory (advanced)：`frontend`

## 3. 环境变量
- 添加 `VITE_API_BASE_URL`：
  - `https://api.risklensai.org`
- 可选：`VITE_APP_TITLE=RiskLens Product`

参考模板：`deploy/cloudflare-product-frontend.env.example`

## 4. 部署后验证
- 打开 `/agent` 页面，发送问题应得到回答。
- 打开 `/dashboard` 页面，能看到 records/companies 指标。
- 打开 `/news` 页面，查询公司新闻（需后端已配置 `MARKETAUX_API_TOKEN`）。

## 5. 域名与 CORS
- 生产环境建议使用同站 API 域名：
  - 产品前端：`https://app.risklensai.org`
  - 后端 API：`https://api.risklensai.org`
- Railway 变量 `CORS_ALLOW_ORIGINS` 更新为：
  - `https://app.risklensai.org,https://risklens-ai.pages.dev,http://localhost:5173`
- 调试阶段可临时保留 `*`，上线前建议收紧白名单。
