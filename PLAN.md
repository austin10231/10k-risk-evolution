# PLAN.md — Bedrock 模型迁移 + Streamlit 残留清理

> 本计划由 Claude 生成，交给 Codex 执行。请按顺序处理任务 A → 任务 B；每完成一个任务都要按 `feedback_changelog` 规则更新 `PROJECT_CHANGELOG_CN.md`（含 commit id）。

---

## 项目现状速览（先读，避免误改）

- **线上主栈**：
  - 后端（Railway）：`agentcore_deploy/main.py` + `agentcore_deploy/agent.py` + `agentcore_deploy/chat_agent.py`
  - 前端（Cloudflare Pages）：`frontend/src/*`（React + Vite）
- **历史遗留 Streamlit 主栈**（已不再部署）：`app.py` + `views/*` + `components/*` + `storage/store.py` + 部分 `core/*`
- **共享 core 模块**（被新后端 import）：
  - `core/extractor.py`（被 `agentcore_deploy/main.py` import；同时调 `core/bedrock.py:_invoke`）
  - `core/comparator.py`（无 streamlit）
  - `core/sec_edgar.py`（无 streamlit）
  - `core/table_extractor.py`（被 main.py import；用 `st.secrets` 取 AWS 凭证）
- **Bedrock 调用现状**（4 处真实 invoke）：
  - `agentcore_deploy/agent.py:15` `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `client.invoke_model(...)`（boto3）+ SigV4 HTTP fallback
  - `agentcore_deploy/main.py:3323/3325` `_MODEL_ID` 默认值 `"us.amazon.nova-pro-v1:0"`（当 `agent.get_model_id()` 失败时的兜底；只用于把 model_id 注入 chat_context，不直接 invoke）
  - `agentcore_deploy/chat_agent.py:424/457` `model_id = ... or "us.amazon.nova-pro-v1:0"`（仅用于回答里"我用的是什么模型"的字符串展示，不直接 invoke）
  - `core/bedrock.py:8` `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `client.invoke_model(...)`（被 `core/extractor.py` 的 AI 抽取路径调用，被 `views/*` 的 Streamlit 路径调用）
  - `core/agent.py:35` `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `client.invoke_model(...)`（仅被 `core/auto_bootstrap.py` 和 `views/*` 调用，属于旧 Streamlit 路径）
- **关键事实**：现有代码 **没有用 Converse API**，全是 `invoke_model(modelId=..., body=...)`，body 是 Nova 专用格式（`inferenceConfig` + `messages[].content[].text`）；切到 Claude 必须同时改 body 与响应解析，或一次性迁到 `client.converse()`。

---

## 任务 A — Bedrock 模型从 Nova 切到 Claude Opus 4.7

### A.0 目标

把所有真实 Bedrock invoke 点的 modelId 从 `us.amazon.nova-pro-v1:0` 切到 **`anthropic.claude-opus-4-7`**，并把请求/响应的格式改成 Claude Messages API 兼容的形态。统一改用 **Bedrock Converse API**（`client.converse(...)`）会比改两套 body 干净，推荐这条路。

> **modelId 取值约定**：用户给的字符串是 `anthropic.claude-opus-4-7`。Bedrock 的 Anthropic 模型一般要带版本号与跨区域 inference profile 前缀（例如 `us.anthropic.claude-opus-4-7-20XXXXXX-v1:0`）。本计划统一定义一个常量 `BEDROCK_CLAUDE_OPUS_47_MODEL_ID = "anthropic.claude-opus-4-7"`，**Codex 在执行前请向用户确认是否要带 `us.` 前缀和版本日期后缀**；如果要带，统一只在常量定义处改一个地方。

### A.1 涉及文件（绝对路径）

需要修改：

1. `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/agent.py`
2. `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py`
3. `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/chat_agent.py`
4. `/Users/mr.tian/Desktop/10k-risk-evolution/core/bedrock.py`
5. `/Users/mr.tian/Desktop/10k-risk-evolution/core/agent.py`（如果保留 Streamlit 旧路径不删，则需要同步切；如果按任务 B 整体删除该文件，则跳过）
6. `/Users/mr.tian/Desktop/10k-risk-evolution/PROJECT_CHANGELOG_CN.md`（追加一节）

**不要改**：
- `agentcore_deploy/chat_agent.py` 里的 `_is_model_question` 关键字列表（包含 `nova`）—— 这是用户问"你是什么模型"的检测，与 Nova 无关，保留没坏处。
- `core/extractor.py` 内部不需要改（它只调 `_invoke`，迁移在 `core/bedrock.py` 内部完成）。
- 任何 `from core.bedrock import ...` 的 import 语句（保持向后兼容）。

### A.2 具体改动

#### A.2.1 改 `agentcore_deploy/agent.py`

- 第 15 行 `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `MODEL_ID = "anthropic.claude-opus-4-7"`
- `_invoke()`（第 66–173 行）整体重写为 **Converse API** 路径：
  - 主路径（boto3 可用）改为：
    ```python
    client = boto3.client("bedrock-runtime", **kwargs)
    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
    )
    return response["output"]["message"]["content"][0]["text"].strip()
    ```
  - SigV4 HTTP fallback（第 104–169 行）：endpoint 由 `/model/{modelId}/invoke` 改为 `/model/{modelId}/converse`；请求体改成：
    ```json
    {
      "messages": [{"role": "user", "content": [{"text": "..."}]}],
      "inferenceConfig": {"maxTokens": ..., "temperature": 0.0, "topP": 1.0}
    }
    ```
    响应解析维持 `result["output"]["message"]["content"][0]["text"]`（Converse API 的响应结构和当前 Nova invoke_model 巧合一致，不需要换 key）。
- `get_model_id()` 不变（只返回常量）。

> **为什么走 Converse 而不是改 anthropic 原生 body**：Converse 是 Bedrock 跨模型统一接口，Nova / Claude / Llama 都用同一份 messages schema，将来再换模型只动 `MODEL_ID`，不用再动 body。

#### A.2.2 改 `agentcore_deploy/main.py`

- 第 3323、3325 行的兜底默认值：
  - `_MODEL_ID = str(_imported_get_model_id() or "").strip() or "us.amazon.nova-pro-v1:0"` → `... or "anthropic.claude-opus-4-7"`
  - `_MODEL_ID = "us.amazon.nova-pro-v1:0"` → `_MODEL_ID = "anthropic.claude-opus-4-7"`
- 不需要动 `_get_model_id()` 调用方（只是把 model_id 注入 chat_context 给 LLM "我是谁" 的回复用）。

#### A.2.3 改 `agentcore_deploy/chat_agent.py`

- 第 424 行 `model_id = _clean_text((context or {}).get("model_id")) or "us.amazon.nova-pro-v1:0"` → `... or "anthropic.claude-opus-4-7"`
- 第 457 行同上替换
- 第 459–467 行的 `_model_identity_answer` 函数：里面写死了"Nova Pro"两次（中文 + 英文），改成"Claude Opus 4.7"。把"Nova Lite"那个建议替换成更合适的描述（例如"如需切换到 Claude Sonnet 4.6 / Haiku 4.5 等更轻量模型，我也可以帮你改配置"），保持函数返回结构不变。

#### A.2.4 改 `core/bedrock.py`

- 第 8 行 `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `MODEL_ID = "anthropic.claude-opus-4-7"`
- `_invoke()`（第 37–54 行）重写为 Converse API：
  ```python
  def _invoke(prompt, max_tokens=1024):
      client = _get_bedrock()
      response = client.converse(
          modelId=MODEL_ID,
          messages=[{"role": "user", "content": [{"text": prompt}]}],
          inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
      )
      return response["output"]["message"]["content"][0]["text"].strip()
  ```
- 其余函数（`classify_risks` / `generate_summary` / `analyze_changes`）调用方接口不动，只依赖 `_invoke` 返回 str。

#### A.2.5 改 `core/agent.py`（**仅在任务 B 决定保留该文件时执行**）

- 第 35 行 `MODEL_ID = "us.amazon.nova-pro-v1:0"` → `MODEL_ID = "anthropic.claude-opus-4-7"`
- `_invoke()`（第 47–64 行）改为 Converse API，写法与 A.2.1 / A.2.4 一致

如果任务 B 决定删除 `core/agent.py`，则跳过本节。

#### A.2.6 更新 `PROJECT_CHANGELOG_CN.md`

新增一节：
- 标题：`Bedrock 主模型迁移：Nova Pro → Claude Opus 4.7（Converse API）`
- 列出动了哪些 invoke 点、为什么走 Converse、对外行为是否改变（应"无"）。
- 末尾写本次 commit id。

### A.3 验证步骤（Codex 执行完代码改动后跑一次）

1. 本地 import smoke test：
   - `cd agentcore_deploy && python -c "from agent import get_model_id, invoke_llm_text; print(get_model_id())"` 应输出 `anthropic.claude-opus-4-7`
   - `python -c "from core.bedrock import MODEL_ID; print(MODEL_ID)"` 同上
2. 起后端：`cd agentcore_deploy && python main.py`，访问 `GET /health` 应 200。
3. 用前端或 curl 打一次 `POST /api/agent/query`，确认 LLM 文本能正常生成（response 里 `model_id` 应是新值）。
4. **不要在本机自动跑 `pytest`**：项目无单元测试套件，跑了也没用。
5. 如果 Bedrock 拒绝该 modelId（`AccessDeniedException` / `ValidationException: model not found`）：先确认账户在 `BEDROCK_REGION` 是否开通了 Claude Opus 4.7 inference profile；再确认是否需要带 `us.` 前缀或日期版本号；这种情况要回到 PLAN A.0 与用户对齐，不要私自换其他模型。

### A.4 注意事项 / 坑

- **Converse API 与 invoke_model 的 IAM 权限不同**：Converse 至少需要 `bedrock:InvokeModel` 与（推荐）`bedrock:Converse`。如果 Railway 上的 IAM 角色只授权了 `bedrock:InvokeModel`，要让用户检查权限。
- **Claude 不支持 `topP=1.0` + `temperature=0.0` 同时极端化**：会被服务端忽略 topP，但不会报错。可以不动这俩参数。
- **Claude 没有 Nova 的 `additionalModelRequestFields`**：当前代码也没用到这部分，无需迁移。
- **token 计费**：Opus 4.7 比 Nova Pro 贵很多（约 10×）。把这条结论也写进 changelog 里提醒。
- **chat_widget.py（旧 Streamlit 浮动聊天）**：第 10 行 `from core.bedrock import MODEL_ID, _invoke` —— 如果任务 B 删掉了 `chat_widget.py` 就不用管；否则它会自动跟着 `core/bedrock.py` 的 MODEL_ID 走。
- **不要再在 PROJECT_CHANGELOG_CN.md 之外另开 changelog 文件**。

---

## 任务 B — 清理 Streamlit 残留代码

### B.0 目标

线上前端已迁移到 React + Cloudflare Pages（`frontend/`），后端独立部署在 Railway（`agentcore_deploy/`）。Streamlit 主栈已无人使用。本任务**列出所有可删除的 Streamlit 残留**，并给出清理方案；最终是否真删由用户拍板。

### B.1 现状判定（哪些是 Streamlit 专用、哪些不是）

#### B.1.1 纯 Streamlit、新栈 100% 不依赖 → 可删

- `/Users/mr.tian/Desktop/10k-risk-evolution/app.py` — Streamlit 入口
- `/Users/mr.tian/Desktop/10k-risk-evolution/views/` — 整个目录（agent/analyze/compare/dashboard/home/library/news/stock/tables/upload + `__init__.py`）
- `/Users/mr.tian/Desktop/10k-risk-evolution/components/` — 整个目录（display/filters/table_viewer + `__init__.py`）
- `/Users/mr.tian/Desktop/10k-risk-evolution/storage/` — 整个目录（store.py 用 `st.secrets`；新后端 `agentcore_deploy/main.py` 已实现自己的 S3 读写函数 `_add_record / _load_index / _load_result / _save_table_result / _load_agent_reports / ...`）
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/chat_widget.py` — Streamlit 浮动聊天 widget；React 端有自己的 `frontend/src/components/FloatingChatWidget.jsx`
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/i18n.py` — Streamlit DOM 注入式翻译
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/global_context.py` — Streamlit `st.session_state` 包装
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/comprehend.py` — Streamlit-only（`grep` 出来仅 views/* 引用，新后端 main.py 不引用）
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/agent.py` — 旧 Streamlit Agent；只被 `core/auto_bootstrap.py`（Streamlit 链）和 `views/*` 引用；新后端 Agent 是 `agentcore_deploy/agent.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/auto_bootstrap.py` — 只被 `views/agent.py` 引用，依赖 `core/agent.py` + `storage/store.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/classifier.py` — 整个文件主体被 docstring 包起来（已实质废弃），无 import 引用（grep 确认）
- `/Users/mr.tian/Desktop/10k-risk-evolution/.streamlit/` — 整个目录（config.toml + secrets.toml）。**注意 `.gitignore` 已忽略 secrets.toml；本地的 secrets.toml 删除前请用户确认是否已经把里面的密钥都迁到 Railway 环境变量并轮换过。**
- `/Users/mr.tian/Desktop/10k-risk-evolution/risklens_agent.zip` — 旧的部署包（强烈建议确认后删）

#### B.1.2 Streamlit 引用但**新后端也在用** → 不能整体删，需要剥离 `import streamlit as st`

这些文件被 `agentcore_deploy/main.py` 实际 import，但内部用了 `st.secrets` 拿 AWS 凭证。要保留文件但把 streamlit 解耦：

- `/Users/mr.tian/Desktop/10k-risk-evolution/core/extractor.py`
  - 现状：第 26 行 `import streamlit as st`；第 47–54 行 `_secret()` 函数会先试 `st.secrets`，失败再回退 `os.getenv`
  - 处理：把 `import streamlit as st` 删掉；`_secret()` 函数体改成只读 `os.getenv(name, default)`（新后端在 Railway 上全是环境变量，根本没有 `st.secrets`，try 块每次都进 except）
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/table_extractor.py`
  - 现状：第 17 行 `import streamlit as st`；第 140 行 `_secret()` 同样的写法
  - 处理：同 `core/extractor.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/bedrock.py`
  - 现状：第 5 行 `import streamlit as st`；第 17–24 行 `_secret()` 同样写法
  - 处理：同 `core/extractor.py`。该文件的 `_invoke` 仍被 `core/extractor.py` 调用，所以**保留文件**，只去 streamlit 化；其余函数 (`classify_risks` / `generate_summary` / `analyze_changes`) 是否保留见下一条。
  - **额外**：如果删了所有 views/*，那 `classify_risks` / `generate_summary` / `analyze_changes` 三个函数就再无调用方（`grep -r` 已确认它们只在 views/ 和 core/auto_bootstrap.py 用）。可以一并删掉这三个函数，只保留 `MODEL_ID / RISK_CATEGORIES / _secret / _get_bedrock / _invoke`。`RISK_CATEGORIES` 也仅 `views/dashboard.py` 用，可一并删除。

> 落地建议：先执行 B.1.1 的删除，再回过头处理 B.1.2 的剥离 + B.1.2 提到的 `core/bedrock.py` 内部死函数清理。

#### B.1.3 文档与配置 → 改文案不删文件

- `/Users/mr.tian/Desktop/10k-risk-evolution/.devcontainer/devcontainer.json`
  - 第 9 行 `"app.py"` → 删除该条
  - 第 20 行 `pip3 install --user streamlit;` → 去掉这一段
  - 第 22 行 `"server": "streamlit run app.py ..."` → 改为 React + agentcore 的启动命令，或直接删 `tasks.server`
- `/Users/mr.tian/Desktop/10k-risk-evolution/requirements.txt`
  - 现状：`streamlit>=1.30.0` / `strands-agents>=1.0.0`
  - 处理：删除 `streamlit>=1.30.0` 与 `strands-agents>=1.0.0`（后者只被 `core/agent.py` 用，A.2.5 删了就没人用了）；剩下的 `boto3 / beautifulsoup4 / lxml / PyPDF2 / plotly / yfinance / certifi` 是不是都还有用，要做一次扫一遍：
    - `plotly` —— 只在 views/dashboard.py 这种地方用，删了 views 之后**可删**
    - `yfinance` —— 全仓 `grep yfinance` 确认是否还有人用；新后端是直接 HTTP 调 Yahoo，**大概率可删**（Codex 执行时再 grep 确认）
    - `PyPDF2` —— `core/table_extractor.py` 用了，**保留**
    - `certifi` —— `core/sec_edgar.py` 用了，**保留**
    - `beautifulsoup4` / `lxml` —— `core/extractor.py` 用了，**保留**
    - `boto3` —— **保留**
- `/Users/mr.tian/Desktop/10k-risk-evolution/.gitignore`
  - 第 2 行 `.streamlit/secrets.toml` —— 如果整个 `.streamlit/` 删了可以一并删这条；不影响功能也可以保留。
- `/Users/mr.tian/Desktop/10k-risk-evolution/deploy/SPLIT_DEPLOY_RUNBOOK_ZH.md`
  - 第 6 行"保持现有 Streamlit 主分支可回滚"、第 20 行"`.streamlit/secrets.toml`"、第 121–127 行"回滚方案"提到 Streamlit
  - 处理：把"保留 Streamlit 作为回滚"那段改成"已下线，回滚走 git tag `pre-split-streamlit`"；不要直接删这份 runbook
- `/Users/mr.tian/Desktop/10k-risk-evolution/agent.md`
  - 第 26 行、第 115 行提到"旧的 Streamlit 路径"
  - 处理：改成"`views/*` / `app.py` 已删除，仅保留在 git history 里"
- `/Users/mr.tian/Desktop/10k-risk-evolution/AGENTS.md` —— 不需要改
- `/Users/mr.tian/Desktop/10k-risk-evolution/PROJECT_CHANGELOG_CN.md` —— 追加"清理 Streamlit 残留代码"一节
- `/Users/mr.tian/Desktop/10k-risk-evolution/UPLOAD_OPTIMIZATION_PLAN.md` —— 文中第 19、62、149 行提"Streamlit"。该 plan 还在执行中，**不要删**；只把里面写"Streamlit + AWS Bedrock 这套部署链路"那段加一行说明"已迁移到 React + Railway"
- `/Users/mr.tian/Desktop/10k-risk-evolution/README.md` —— 现在只有 129 字节，看一眼内容，如有 streamlit 引用一并改
- `/Users/mr.tian/Desktop/10k-risk-evolution/.env.local` —— 76 字节，看一眼是不是 Streamlit 相关的本地变量

### B.2 推荐执行顺序

1. **先备份**：`git tag pre-streamlit-removal && git push origin pre-streamlit-removal`（这步要用户授权）
2. 删 B.1.1 列出的全部文件 / 目录
3. 处理 B.1.2 的 streamlit 解耦（`core/extractor.py` / `core/table_extractor.py` / `core/bedrock.py`）
4. 在 `core/bedrock.py` 删掉 B.1.2 末段提到的死函数（如果 B.1.1 已删除 views/ 与 core/auto_bootstrap.py）
5. 改 B.1.3 列出的配置 / 文档
6. 本地起一次后端 `cd agentcore_deploy && python main.py`，跑 `/health` 与 `/api/agent/query` 确认无 import error
7. `pip install -r agentcore_deploy/requirements.txt && python -c "import core.extractor, core.bedrock, core.table_extractor, core.sec_edgar, core.comparator"` 检查没有残留 streamlit import
8. 更新 `PROJECT_CHANGELOG_CN.md` 并把 commit id 写进去

### B.3 验证清单

- [ ] `grep -rn "import streamlit\|from streamlit\|st\.secrets\|st\.session_state" agentcore_deploy/ core/` 应为空
- [ ] `python -c "import core.extractor; import core.table_extractor; import core.bedrock; import core.sec_edgar; import core.comparator"` 在没有 streamlit 包的虚拟环境里能跑
- [ ] `cd agentcore_deploy && python main.py` 起后端，`curl localhost:<port>/health` 返回 200
- [ ] Cloudflare Pages 上的前端能正常调到 Railway 后端的 `/api/*`（这一步要等部署后用户验证）

### B.4 注意事项 / 坑

- `.streamlit/secrets.toml` 里有真实密钥（AWS / Cognito / Marketaux），**删除前必须确认密钥已迁到 Railway 并完成轮换**。强烈建议先 `mv .streamlit/secrets.toml ~/risklens_secrets_backup_2026-05-02.toml` 再 push 删除。
- 删 `views/*` 后，git history 里仍能看到旧实现，不影响以后参考。
- `risklens_agent.zip` 在仓库根目录，约 7.6 KB，看上去是旧的 AgentCore zip 部署包；如果当前 Railway 部署不依赖它就删，**删除前用户确认一次**。
- `core/classifier.py` 主体被三引号字符串包成了一个超长 docstring（`"""\n#Split Item 1A text into risk blocks...\n...\n"""`），没有任何 `def` 暴露给外部，已实质死代码，可以放心删。
- `core/auto_bootstrap.py` 只被 `views/agent.py` 引用，跟 views 一起删；它也间接依赖 `core/agent.py`、`storage/store.py` —— 全部一起删。
- `frontend/node_modules/` 与 `frontend/dist/` 不要碰，那是 React 构建产物。
- 删除前请确认 `.env.local`、`.gitignore` 没有遗漏的 streamlit-only 变量。

---

## 交付物清单

执行完后需要交付：

1. 一个 commit（或两个，A 任务和 B 任务分开）
2. `PROJECT_CHANGELOG_CN.md` 追加两节（每节带 commit id）
3. 后端 `python main.py` 本地能起、`/health` 200
4. 把"Bedrock IAM 是否需要 `bedrock:Converse` 权限"和"`anthropic.claude-opus-4-7` 这个 modelId 是否需要带 `us.` 前缀 / 日期后缀"两个开放问题列回给用户

---

计划已写好，可以交给 Codex 执行。
