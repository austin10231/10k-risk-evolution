# RiskLensAI 登录同站域名配置清单

目标：让登录 session cookie 在所有主流浏览器里稳定生效，避免用户登录后仍显示 Guest。

推荐生产域名：
- 产品前端：`https://app.risklensai.org`
- 后端 API：`https://api.risklensai.org`
- 官网/landing：`https://risklensai.org`

## 1) DNS

在 DNS 服务商里新增：

```text
api.risklensai.org -> Railway 后端服务 custom domain
app.risklensai.org -> 产品前端 Cloudflare Pages custom domain
risklensai.org -> landing page Cloudflare Pages custom domain
```

Railway 会给 `api.risklensai.org` 提供需要配置的 CNAME/验证记录；以 Railway 页面显示为准。

## 2) Railway 后端变量

Railway Service -> Variables：

```bash
APP_BASE_URL=https://app.risklensai.org
PUBLIC_API_BASE_URL=https://api.risklensai.org
CORS_ALLOW_ORIGINS=https://app.risklensai.org,https://risklens-ai.pages.dev,http://localhost:5173

COGNITO_DOMAIN=https://YOUR_COGNITO_DOMAIN.auth.YOUR_REGION.amazoncognito.com
COGNITO_CLIENT_ID=YOUR_COGNITO_CLIENT_ID
COGNITO_CLIENT_SECRET=
COGNITO_SCOPE=openid email profile
COGNITO_REDIRECT_URI=https://api.risklensai.org/api/auth/callback
COGNITO_ALLOWED_CALLBACK_URLS=https://api.risklensai.org/api/auth/callback
COGNITO_LOGOUT_REDIRECT_URI=https://app.risklensai.org/agent
COGNITO_ALLOWED_SIGNOUT_URLS=https://app.risklensai.org/agent
COGNITO_PROMPT=select_account

RISKLENS_SESSION_SECRET=GENERATE_A_LONG_RANDOM_VALUE
AUTH_COOKIE_DOMAIN=.risklensai.org
AUTH_COOKIE_SAMESITE=Lax
AUTH_COOKIE_SECURE=1
AUTH_RETURN_TO_ALLOWLIST=https://app.risklensai.org,https://risklens-ai.pages.dev,https://risklensai.org
```

说明：
- `COGNITO_CLIENT_SECRET`：如果 Cognito App Client 没有 secret，就留空；如果有，只能放 Railway。
- `RISKLENS_SESSION_SECRET`：必须是长期稳定随机值，不要每次部署变化，否则旧登录态会失效。
- `AUTH_COOKIE_DOMAIN=.risklensai.org`：让 `api.risklensai.org` 设置的 session cookie 可以在同站请求中稳定发送。
- `AUTH_COOKIE_SAMESITE=Lax`：同站架构下比 `None` 更不容易被 Safari / 隐私浏览器当第三方 cookie 拦截。

## 3) Cloudflare 产品前端变量

Cloudflare Pages 项目 `frontend/` -> Environment Variables：

```bash
VITE_API_BASE_URL=https://api.risklensai.org
VITE_APP_TITLE=RiskLens Product
```

改完变量后需要重新部署产品前端。Vite 会在 build 时固化 `VITE_API_BASE_URL`。

## 4) Cloudflare landing page 变量

Landing page 本身不持有 Cognito secret。若需要配置 API 链接，可使用：

```bash
PUBLIC_API_BASE_URL=https://api.risklensai.org
PUBLIC_APP_ENV=production
```

登录入口应跳到：

```text
https://app.risklensai.org/auth?return_to=https%3A%2F%2Fapp.risklensai.org%2Fagent
```

当前代码里的 `landing-page/auth/index.html` 已经是跳转 shim，会统一进入产品侧品牌化 `/auth` 页面。

## 5) Cognito App Client 配置

Cognito User Pool -> App integration -> App client -> Hosted UI：

Allowed callback URLs：

```text
https://api.risklensai.org/api/auth/callback
```

Allowed sign-out URLs：

```text
https://app.risklensai.org/agent
```

OAuth 2.0 grant types：

```text
Authorization code grant
```

OpenID Connect scopes：

```text
openid
email
profile
```

Identity providers：

```text
Google
```

建议：
- 如果还在切换期，可以临时保留旧 callback：`https://10k-risk-evolution-production-982d.up.railway.app/api/auth/callback`。
- 切到 `api.risklensai.org` 并验证成功后，再移除旧 Railway callback，避免旧域名继续产生跨站 cookie 问题。

## 6) 部署顺序

1. Railway 添加 `api.risklensai.org` custom domain，并完成 DNS 验证。
2. Cognito 添加 `https://api.risklensai.org/api/auth/callback` 和 `https://app.risklensai.org/agent`。
3. Railway 更新所有后端变量并重新部署。
4. Cloudflare 产品前端设置 `VITE_API_BASE_URL=https://api.risklensai.org` 并重新部署。
5. Landing page 重新部署，确保登录入口进入 `https://app.risklensai.org/auth`。

## 7) 验证方法

打开产品页后，在 DevTools -> Network 过滤 `/api/me`：

成功时应该看到：

```json
{
  "ok": true,
  "authenticated": true,
  "user": {
    "email": "当前登录账号",
    "source": "cognito_session_cookie"
  },
  "storage": {
    "mode": "global_plus_user",
    "user_prefix": "users/<user_id>/"
  }
}
```

如果还是 Guest，重点检查：
- `/api/me` 请求 URL 是否是 `https://api.risklensai.org/api/me`。
- `/api/auth/callback` 响应里是否有 `Set-Cookie: risklens_session=...; Domain=.risklensai.org; Secure; SameSite=Lax`。
- Cognito callback URL 是否精确匹配 `https://api.risklensai.org/api/auth/callback`。
- Cloudflare 前端是否重新 build 过，旧 bundle 可能还在请求 Railway raw domain。
