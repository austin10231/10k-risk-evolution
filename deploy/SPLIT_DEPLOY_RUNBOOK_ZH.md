# 前后端分离部署手册（Railway + Cloudflare）

适用目标：
- 后端（Agent + 数据处理 + 第三方 API）部署到 Railway
- 前端（Landing + Product Web UI）部署到 Cloudflare
- 保持现有 Streamlit 主分支可回滚

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
- `CORS_ALLOW_ORIGINS`

放到 Cloudflare（前端公开可见）：
- `PUBLIC_API_BASE_URL`
- `PUBLIC_COGNITO_DOMAIN`
- `PUBLIC_COGNITO_CLIENT_ID`
- `PUBLIC_COGNITO_REDIRECT_URI`
- `PUBLIC_COGNITO_SCOPE`

绝对不要放到前端：
- `COGNITO_CLIENT_SECRET`
- 任何 `AWS_*` 私钥
- `MARKETAUX_API_TOKEN`
- `AGENTCORE_*` 私密配置

---

## 3) CORS_ALLOW_ORIGINS 应该填什么

这是“允许访问后端 API 的前端域名白名单”，示例：

`https://app.example.com,https://www.example.com,http://localhost:5173`

说明：
- 生产环境填你的真实 Cloudflare 域名
- 本地联调可加 `http://localhost:5173`（或你本地端口）
- 多个域名用英文逗号分隔

---

## 4) Railway 部署步骤（后端）

1. Railway 创建新项目 -> 连接本仓库
2. 配置 Build/Start（当前项目可直接用 `agentcore_deploy`）
   - Root Directory: `agentcore_deploy`
   - Install Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
3. 在 `Variables` 粘贴 `deploy/railway.env.example` 对应值
4. 设置 Health Check 路径：`/health`
5. 发布后拿到后端地址（后续填到前端 `PUBLIC_API_BASE_URL`）

接口约定（当前后端）：
- `GET /health`：健康检查
- `POST /invocations`：主推理入口

---

## 5) Cloudflare 部署步骤（前端）

1. Cloudflare Pages 创建项目 -> 连接前端仓库目录
2. 配置构建命令与输出目录（按前端框架）
3. 在 Environment Variables 填 `deploy/cloudflare-pages.env.example`
4. 部署后拿到前端域名
5. 回填后端 CORS：把前端域名加入 `CORS_ALLOW_ORIGINS`

---

## 6) Cognito 迁移要点

1. 建议新建一个前端公有 Client（PKCE）
2. 回调地址（Callback URL）指向 Cloudflare 前端域名
3. 前端只用：
   - Domain
   - Client ID
   - Redirect URI
   - Scope
4. `Client Secret` 仅后端使用（如使用授权码交换）

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

当日保留原 Streamlit 地址和配置不下线，出现问题时：
1. Landing 页面“进入产品”按钮临时指回旧 Streamlit 地址
2. DNS 不改或回退到旧目标
3. 使用 `pre-split-streamlit` 标签回看稳定版本
