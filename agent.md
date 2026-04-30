# RiskLens 快速定位手册（给 Codex）

目的：减少每次改代码前的全项目扫描时间，先看对的文件。

---

## 0) 每次开始前的最短路径（强制）

1. 先看本文件 `agent.md`（当前手册）。
2. 再看 `AGENTS.md`（push 规则、分支规则）。
3. 根据任务类型，只进入对应模块（见下文“任务入口索引”）。

默认不要全仓 `find + read`。

---

## 1) 默认技术栈判断（非常重要）

当前线上主流程优先级：

- 前端主界面：`frontend/src/*`（React）
- 后端 API / Agent Runtime：`agentcore_deploy/main.py` + `agentcore_deploy/chat_agent.py`

历史遗留（默认不看）：

- `views/*`、`app.py` 这套是旧的 Streamlit 路径，除非用户明确说“改 Streamlit 版本”，否则不要优先进入。

---

## 2) 任务入口索引（按需求类型）

### A. 改 Agent 逻辑（意图识别、tool 路由、输出结构）
优先看：

1. `agentcore_deploy/chat_agent.py`（intent/router/对话决策）
2. `agentcore_deploy/main.py`（tool 实现、API 暴露、provider fallback）
3. `frontend/src/lib/workspaceChat.jsx`（前端如何消费 agent 返回）

### B. 改聊天体验（输入框、发送、IME、附件、消息样式）
优先看：

1. `frontend/src/components/FloatingChatWidget.jsx`
2. `frontend/src/lib/workspaceChat.jsx`
3. `frontend/src/lib/chatMemory.jsx`
4. `frontend/src/index.css`
5. `frontend/src/components/AppShell.jsx`（全局布局/底部 dock）

### C. 改 API 请求、超时、错误处理
优先看：

1. `frontend/src/lib/api.js`
2. `agentcore_deploy/main.py`（对应 `/api/*` 路由）

### D. 改上传/记录/仪表盘数据链路
优先看：

1. `agentcore_deploy/main.py`（`/api/upload/*`、`/api/dashboard/*`）
2. `frontend/src/pages/UploadPage.jsx`
3. `frontend/src/pages/LibraryPage.jsx`
4. `frontend/src/pages/DashboardPage.jsx`

### E. 改 Landing Page（官网）
优先看：

1. `landing-page/index.html`
2. `landing-page/docs/*`
3. `landing-page/assets/*`

---

## 3) 页面到文件映射（前端 React）

- Home：`frontend/src/pages/HomePage.jsx`
- Upload & Records：`frontend/src/pages/UploadPage.jsx`、`frontend/src/pages/LibraryPage.jsx`
- Stock：`frontend/src/pages/StockPage.jsx`
- News：`frontend/src/pages/NewsPage.jsx`
- Dashboard：`frontend/src/pages/DashboardPage.jsx`
- Compare：`frontend/src/pages/ComparePage.jsx`
- Tables：`frontend/src/pages/TablesPage.jsx`
- Agent Chat 主页：`frontend/src/pages/AgentPage.jsx`
- 全局壳与导航：`frontend/src/components/AppShell.jsx`
- 全局样式：`frontend/src/index.css`

路由入口：

- `frontend/src/App.jsx`

---

## 4) 后端 API 到文件映射（AgentCore）

统一入口：

- `agentcore_deploy/main.py`

常用 API：

- `/api/news`：新闻聚合与 fallback（Marketaux / TheNewsAPI / Currents）
- `/api/stock/quote`：股票数据（TwelveData / FMP / Yahoo / Stooq fallback）
- `/api/dashboard/summary`：Dashboard 聚合
- `/api/upload/manual`、`/api/upload/auto-fetch`
- `/api/agent/query`：聊天代理查询

意图/对话编排：

- `agentcore_deploy/chat_agent.py`

---

## 5) 默认排查顺序（避免走弯路）

1. 先确认问题发生在哪一层：前端展示 vs API 返回 vs Agent 路由。
2. 先看“页面文件 + 对应 API”这两个点，不要先扫全项目。
3. 只在以下情况进入旧 Streamlit 代码：
   - 用户明确点名 `views/*` 或 `app.py`
   - React 页面查不到对应实现
   - 需要对比历史逻辑迁移

---

## 6) 变更范围规则

- 非需求范围文件不要改。
- 能小改就不大改。
- 每次完成后更新 `PROJECT_CHANGELOG_CN.md`（简明记录改了什么）。

