# 前后端分离部署手册（Railway + Cloudflare）

适用目标：
- 后端（Agent + 数据处理 + 第三方 API）部署到 Railway
- 前端（Landing + Product Web UI）部署到 Cloudflare
- Streamlit 主栈已下线；回滚以 git tag `pre-split-streamlit` 回看历史版本为准

---

## 1) 先做这 3 件事（按顺序）

1. 备份当前版本（必须）
   - `git tag pre-split-streamlit`
   - `git push origin pre-split-streamlit`

2. 在 Railway / Cloudflare 先把变量填好（先不切流量）
   - Railway 变量模板：`deploy/railway.env.example`
   - Cloudflare 变量模板：`deploy/cloudflare-pages.env.example`

3. 把 `secrets.toml` 里所有真实密钥迁移到平台变量后，立即轮换密钥
   - 当前密钥来源：`.streamlit/secrets.toml`
   - 建议轮换：`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `COGNITO_CLIENT_SECRET` / `MARKETAUX_API_TOKEN`

---

## 2) 变量放置规则（最重要）

放到 Railway（后端私密）：
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`（如果有）
- `AWS_REGION`
- `BEDROCK_REGION`
- `S3_BUCKET`
- `AGENTCORE_RUNTIME_ARN`
- `AGENTCORE_QUALIFIER`
- `AGENTCORE_REGION`
- `MARKETAUX_API_TOKEN`
- `COMPREHEND_REGION`（可选）
- `APP_BASE_URL`
- `PUBLIC_API_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `COGNITO_DOMAIN`
- `COGNITO_CLIENT_ID`
- `COGNITO_CLIENT_SECRET`（如果 Cognito App Client 有 secret）
- `COGNITO_SCOPE`
- `COGNITO_REDIRECT_URI`
- `COGNITO_ALLOWED_CALLBACK_URLS`
- `COGNITO_LOGOUT_REDIRECT_URI`
- `COGNITO_ALLOWED_SIGNOUT_URLS`
- `RISKLENS_SESSION_SECRET`
- `AUTH_COOKIE_DOMAIN`
- `AUTH_COOKIE_SAMESITE`
- `AUTH_COOKIE_SECURE`
- `AUTH_RETURN_TO_ALLOWLIST`

放到 Cloudflare（前端公开可见）：
- `VITE_API_BASE_URL`（产品前端 `frontend/`）
- `PUBLIC_API_BASE_URL`（landing page 若需要展示/链接 API）

绝对不要放到前端：
- `COGNITO_CLIENT_SECRET`
- 任何 `AWS_*` 私钥
- `MARKETAUX_API_TOKEN`
- `AGENTCORE_*` 私密配置

---

## 3) CORS_ALLOW_ORIGINS 应该填什么

这是“允许访问后端 API 的前端域名白名单”，示例：

`https://app.risklensai.org,https://risklens-ai.pages.dev,http://localhost:5173`

说明：
- 生产环境填你的真实 Cloudflare 域名
- 本地联调可加 `http://localhost:5173`（或你本地端口）
- 多个域名用英文逗号分隔
- 使用 cookie 登录时不要依赖 `*`，浏览器会拒绝 wildcard + credentials 的组合

---

## 4) Railway 部署步骤（后端）

1. Railway 创建新项目 -> 连接本仓库
2. 配置 Build/Start（当前项目可直接用 `agentcore_deploy`）
   - Root Directory: `agentcore_deploy`
   - Install Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
3. 在 `Variables` 粘贴 `deploy/railway.env.example` 对应值
4. 设置 Health Check 路径：`/health`
5. 发布后绑定自定义域名 `https://api.risklensai.org`（后续填到前端 `VITE_API_BASE_URL`）

接口约定（当前后端）：
- `GET /health`：健康检查
- `POST /invocations`：主推理入口

---

## 5) Cloudflare 部署步骤（前端）

1. Cloudflare Pages 创建项目 -> 连接前端仓库目录
2. 配置构建命令与输出目录（按前端框架）
3. 产品前端在 Environment Variables 填 `deploy/cloudflare-product-frontend.env.example`
4. 部署后拿到前端域名
5. 回填后端 CORS：把前端域名加入 `CORS_ALLOW_ORIGINS`

---

## 6) Cognito 迁移要点

1. Hosted UI 仍然由 Cognito 承担，产品内的 `/auth` 只是品牌化入口页
2. 回调地址（Callback URL）指向后端 API：
   - `https://api.risklensai.org/api/auth/callback`
3. Sign-out URL 指向产品页：
   - `https://app.risklensai.org/agent`
4. 前端只配置 `VITE_API_BASE_URL=https://api.risklensai.org`
5. `COGNITO_CLIENT_SECRET` 仅放 Railway；如果 App Client 没有 secret 可以留空
6. 为避免 Safari / 隐私浏览器阻止第三方 cookie，生产环境必须让 API 使用同站域名：
   - `app.risklensai.org`
   - `api.risklensai.org`
   - `AUTH_COOKIE_DOMAIN=.risklensai.org`
   - `AUTH_COOKIE_SAMESITE=Lax`

---

## 7) 切流量前检查清单

- 前端能正常打开并发起登录
- 登录后能拿到有效身份并调用后端 API
- Agent 提问可正常返回
- 新闻/股票功能可用（`MARKETAUX_API_TOKEN` 已生效）
- 上传 / 报告查询可用（S3 / AWS 权限正常）
- 后端日志无鉴权错误、无 CORS 错误

---

## 8) 回滚方案（建议保留）

Streamlit 主栈已从当前代码树移除，出现问题时：
1. DNS 不改或回退到上一个稳定 Cloudflare / Railway 部署
2. 使用 `pre-split-streamlit` 标签回看旧 Streamlit 稳定版本
3. 如需恢复旧实现，从 git history 中 cherry-pick 对应文件
