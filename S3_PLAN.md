# S3_PLAN.md — S3 数据重组 + 批量扩展计划

> 本计划由 Claude 生成，交给 Codex 执行。Part 1 和 Part 2 复用同一套提取逻辑（`core/extractor.py:extract_item1a_risks_bedrock` + `extract_item1_overview_bedrock`），保证新旧公司 JSON 格式与质量一致。完成后按 `feedback_changelog` 规则更新 `PROJECT_CHANGELOG_CN.md`（含 commit id）。

---

## 0) S3 现状速览（先读，避免误删）

**Bucket**：`10k-risk-alert-app`（来自 Railway 环境变量 `S3_BUCKET`）

```
s3://10k-risk-alert-app/
├── 10k_html_datasets/         # 42 个 .html，文件名形如 <Company>_<Year>_10-K_<sid>.html
├── risk_analysis_results/      # 42 个 .json（旧逻辑，本次任务后整体作废）
├── agent_reports/              # Agent 执行历史（保留）
├── compare_reports/            # 历史残留，代码已无引用（独立任务再清理，本次不动）
├── stock_quote_cache_v1/       # 行情缓存（保留）
├── tables_extraction/          # 财务表格抽取产物（保留）
├── company_ticker_map.json     # 10 条映射，缺很多
├── filing_records_index.json   # 42 条 record 索引（旧 schema）
```

**当前 42 条索引按行业归属**（取自 `filing_records_index.json`，**有错误，必须在迁移时同步修正**）：

| 行业（旧）| 公司 | 备注 |
|---|---|---|
| Technology | Airbus, Alphabet, Apple, Motorola Solutions Inc, NVIDIA | 注：Airbus 是法国/欧洲公司，不在 SEC 体系，归类有问题 |
| Energy | Chevron, **ConocoPhilllips**（3 个 l，typo）, Exxon Mobil | typo 必须改成 `ConocoPhillips` |
| Consumer Staples | Kroger, Target, Walmart | 用户的目标行业表里叫 "Consumer Defensive"，需要统一 |
| Other | NVIDIA, Uber | NVIDIA 与 Technology 重复；Uber 应归 Consumer Cyclical |
| Industrials | Boeing, **lockheed** | "lockheed" 小写，且不完整，应改成 `Lockheed Martin` |

**`company_ticker_map.json` 现有内容**（仅 10 条）：
```
Alphabet→GOOG, Apple→AAPL, Motorola Solutions, Inc→MSI, Walmart→WMT,
Chevron→CVX, NVIDIA→NVDA, Uber→UBER, Boeing→BA, Airbus→AIR.PA, lockheed→LMT
```
> Alphabet 用的是 GOOG（C 类），用户的目标列表写的是 GOOGL（A 类）。**两者底层公司一样，只是股权类别不同**；本计划默认沿用 ticker map 的 GOOG（避免 SEC 检索切换 CIK 时混乱），目录名写 `Alphabet_GOOG`。如要改成 GOOGL，告知 Codex 即可。

**代码层 S3 常量**（全部在 `agentcore_deploy/main.py:69-75`）：
```python
INDEX_KEY        = "filing_records_index.json"
RESULTS_PREFIX   = "risk_analysis_results"
AGENT_PREFIX     = "agent_reports"
TICKER_MAP_KEY   = "company_ticker_map.json"
HTML_PREFIX      = "10k_html_datasets"
PDF_PREFIX       = "10k_pdf_datasets"
TABLES_PREFIX    = "tables_extraction"
```

读 / 写这些 key 的函数（也都在 `agentcore_deploy/main.py`）：
- 读：`_load_index`(L236)、`_load_result`(L256)、`_load_company_ticker_map`(L277)、`_load_agent_reports`(L788)、`_list_s3_keys`(L209)
- 写：`_save_index`(L533)、`_save_company_ticker_map`(L538)、`_add_record`(L695)、`_append_agent_report_file`(L1037)、`_write_s3_bytes`(L190)
- 删：`_delete_s3_key`(L198)、`_delete_s3_prefix`(L561)
- 缓存失效：`_invalidate_runtime_caches`(L132)

**前端不直接访问 S3**：`frontend/src/*` 通过 `/api/records`、`/api/records/{record_id}`、`/api/dashboard/summary` 读后端，本次任务前端零改动。

---

## Part 1 — 重组现有 42 条数据 + 重新提取

### 1.1 目标

把现存的 42 个 HTML 从扁平 prefix 迁到行业/公司分层结构，丢弃旧 JSON，用新提取逻辑重跑生成新 JSON，写一份新的 index.json。

**新结构**（与用户提案对齐，目录用 underscore 避免 S3 URL encode 问题）：
```
s3://10k-risk-alert-app/
└── 10k_filings/
    ├── index.json
    ├── Technology/
    │   ├── Apple_AAPL/
    │   │   ├── 2020_10K.html
    │   │   ├── 2020_10K_risks.json
    │   │   ├── 2021_10K.html
    │   │   ├── 2021_10K_risks.json
    │   │   ├── 2022_10K.html
    │   │   ├── 2022_10K_risks.json
    │   │   └── ...
    │   ├── Alphabet_GOOG/
    │   ├── NVIDIA_NVDA/
    │   └── Motorola_Solutions_MSI/
    ├── Energy/
    │   ├── Chevron_CVX/
    │   ├── ConocoPhillips_COP/      # 注意拼写已修正
    │   └── ExxonMobil_XOM/
    ├── Consumer_Defensive/          # 改名（Consumer Staples → Consumer Defensive）
    │   ├── Kroger_KR/
    │   ├── Target_TGT/
    │   └── Walmart_WMT/
    ├── Consumer_Cyclical/
    │   └── Uber_UBER/
    └── Industrials/
        ├── Boeing_BA/
        └── Lockheed_Martin_LMT/     # 注意公司名补全 + 大小写
```

> **不迁移**：`Airbus_2023_10-K_*` / `Airbus_2024_10-K_*` 两份。Airbus 是欧洲公司，不在 10-K 体系（它发的是欧盟 URD/AR），强烈建议在 Part 1 把它从新结构里剔除（保留在旧 prefix 不动）。如果用户希望保留，单独建 `International_Other/Airbus_AIRPA/`，**请 Codex 在执行前向用户确认**。

### 1.2 涉及文件（绝对路径）

需要新建：

1. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/__init__.py`（空文件，让 scripts 成包）
2. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/migrate_s3_layout.py` — Part 1 主脚本
3. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/industry_mapping.py` — 公司→行业 / ticker 硬编码映射（Part 1 + Part 2 共用）
4. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/extraction_pipeline.py` — 提取 + 写盘的复用函数（Part 1 + Part 2 共用）
5. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/README.md` — 跑这些脚本前的环境变量、依赖、命令行示例

需要修改（仅在第二阶段切流量后）：

6. `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py` — 切到读新结构（详见 §1.6）
7. `/Users/mr.tian/Desktop/10k-risk-evolution/PROJECT_CHANGELOG_CN.md` — 追加一节

不要改：
- `/Users/mr.tian/Desktop/10k-risk-evolution/core/*` — 提取与下载逻辑直接复用，不动
- `frontend/src/*` — 前端通过 API 读，零变更
- `agentcore_deploy/agent.py` / `agentcore_deploy/chat_agent.py` — 与 S3 路径无关

### 1.3 `scripts/industry_mapping.py` 的内容

定义两份硬编码 dict（Part 1 + Part 2 都用）：

```python
# 行业 → 该行业下的公司列表（顺序无关），key 是 S3 子目录名（下划线，不含空格）
INDUSTRIES = {
    "Technology":            [...10 家],
    "Energy":                [...8 家],
    "Consumer_Cyclical":     [...8 家],
    "Consumer_Defensive":    [...8 家],
    "Communication_Services":[...8 家],
    "Industrials":           [...9 家],
    "Financial_Services":    [...8 家],
    "Utilities":             [...6 家],
    "Basic_Materials":       [...6 家],
    "Real_Estate":           [...6 家],
    "Healthcare":            [...8 家],
}

# 公司元数据：display_name + ticker + cik（可选）+ S3 子目录名 + sec_company_name（用于 EDGAR 检索）
COMPANIES = {
    "AAPL":  {"name": "Apple",            "industry": "Technology",            "dir": "Apple_AAPL",            "sec_name": "Apple Inc"},
    "MSFT":  {"name": "Microsoft",        "industry": "Technology",            "dir": "Microsoft_MSFT",        "sec_name": "Microsoft Corp"},
    "GOOG":  {"name": "Alphabet",         "industry": "Technology",            "dir": "Alphabet_GOOG",         "sec_name": "Alphabet Inc"},
    "META":  {"name": "Meta",             "industry": "Communication_Services","dir": "Meta_META",             "sec_name": "Meta Platforms Inc"},
    # ... 完整 ~100 行
}
```

> **行业归属裁决**：
> - Alphabet 和 Meta 用户在两个行业里都列了。SEC GICS 体系下 **Alphabet 归 Communication Services（不是 Technology）**，Meta 归 Communication Services。Codex 默认按 GICS 把它们归 Communication_Services；如用户希望沿用 Yahoo Finance 风格（Alphabet 在 Communication Services，Meta 在 Communication Services），保持一致即可。
> - Amazon、Tesla、Home Depot 等归 Consumer_Cyclical（Yahoo / GICS 一致）。
> - 用户列表里 Berkshire Hathaway 给了 Financial_Services；BRK 是 conglomerate，但 SEC GICS 也归 Financial Services，没问题。
> - **冲突处理建议**：在 `industry_mapping.py` 顶部加注释说明本表参考 GICS 2024-09，并把分歧点（Alphabet/Meta）作为常量写死，便于以后改。

> **CIK 字段**：`COMPANIES[ticker]["cik"]` 不是必填。`core/sec_edgar.find_cik()` 已经能用 ticker 查到 CIK（`https://www.sec.gov/files/company_tickers.json`），所以只在 SEC 检索失败的特殊公司（典型如 Berkshire Hathaway 的双 ticker BRK.A/BRK.B）手动补 cik。

### 1.4 `scripts/extraction_pipeline.py` 内容（Part 1 + Part 2 共用）

提供四个函数：

```python
def s3_client(): ...                          # 用 boto3，认证从 env 读
def s3_bucket() -> str: ...                   # os.getenv("S3_BUCKET")
def extract_risks_for_html(
    html_bytes: bytes,
    company_display_name: str,
    industry: str,
) -> dict:
    """复用 core/extractor 的 AI 提取主路径。"""
    # 调 extract_item1_overview_bedrock 取 overview
    # 调 extract_item1a_risks_bedrock 取 risks
    # 返回与 _manual_extract_result 相同 schema：
    #   {"company_overview": {...}, "risks": [{"category":..., "sub_risks":[...]}]}
def write_filing_to_new_layout(
    *,
    industry_dir: str,        # e.g. "Technology"
    company_dir: str,         # e.g. "Apple_AAPL"
    year: int,
    html_bytes: bytes,
    risks_json: dict,
) -> tuple[str, str]:
    """写两个 key，返回 (html_key, json_key)。键格式：
       10k_filings/<industry>/<company_dir>/<year>_10K.html
       10k_filings/<industry>/<company_dir>/<year>_10K_risks.json
    """
def read_filing_from_new_layout(
    industry_dir: str, company_dir: str, year: int
) -> tuple[Optional[bytes], Optional[dict]]:
    """读 (html, json)，任一不存在返回 None。"""
```

> **注意**：`extract_item1a_risks_bedrock` 内部会调 Bedrock（前一个 PLAN.md 已规划切到 Claude Opus 4.7）。**Part 1 的迁移如果在 PLAN.md 模型迁移之前跑，会用旧 Nova Pro 提取一次；如果在之后跑，会用 Claude Opus 4.7 跑一次**——结果可能不一致。建议两个计划串行：先做模型迁移（PLAN.md），稳定后再做本计划，避免重复跑 42 次 Bedrock。**Codex 执行前请向用户确认顺序。**

### 1.5 `scripts/migrate_s3_layout.py` 主流程（Part 1）

伪代码：

```
1. 解析 CLI 参数：
   --dry-run            只打印计划，不写 S3
   --skip-airbus        默认 True
   --reextract          默认 True；False 时跳过提取，只迁 HTML
   --concurrency 4      Bedrock 并发上限
   --resume             支持中断后接着跑

2. 列出 s3://<bucket>/10k_html_datasets/*.html，得到 42 条 key

3. 对每个 key：
   a. 解析文件名 <safe_company>_<year>_10-K_<sid>.html
      - 用 regex `^(.+)_(\d{4})_10-K_[0-9a-f]+\.html$` 抓 (safe_company, year)
      - safe_company 反归一化：替换下划线为空格，再查 industry_mapping
        额外 hardcoded 修正：
          "ConocoPhilllips" -> "ConocoPhillips" -> ticker COP
          "lockheed"        -> "Lockheed Martin" -> ticker LMT
          "Motorola_Solutions_Inc" -> "Motorola Solutions" -> ticker MSI
          "Exxon_Mobil"     -> "ExxonMobil" -> ticker XOM
          "Airbus"          -> 跳过 (skip_airbus=True 时)
   b. 从 industry_mapping 取 industry_dir + company_dir
   c. 下载 HTML 字节
   d. 计算新 key html_key, json_key（见 1.4）
   e. 如果 --resume 且 html_key 已存在，跳过 HTML 上传；否则 put_object 到 html_key
   f. 如果 --reextract：
      - 调 extract_risks_for_html(html_bytes, display_name, industry_label)
      - 校验 risks 非空且 sub_risks 数 ≥ 5（覆盖率 sanity check）
      - 调 _generate_agent_priority_report 走 run_agent，把 priority_matrix 拼进 result
        （和 main.py:_auto_fetch_and_extract 同口径，否则 dashboard RPI 会全是 0）
      - put_object risks_json 到 json_key
   g. 把 (industry, company, ticker, year, html_key, json_key, sub_risk_count) 加进
      内存累加表 NEW_INDEX_ENTRIES

4. 全部跑完后构建 index.json：
   {
     "version": 1,
     "generated_at": "<ISO timestamp>",
     "schema": {
       "html_key":  "10k_filings/<industry>/<company_dir>/<year>_10K.html",
       "json_key":  "10k_filings/<industry>/<company_dir>/<year>_10K_risks.json"
     },
     "industries": {
        "Technology": {
          "Apple_AAPL": {
            "company": "Apple",
            "ticker": "AAPL",
            "industry": "Technology",
            "cik": "0000320193",
            "filings": [
              {"year": 2020, "filing_type": "10-K",
               "html_key": "10k_filings/Technology/Apple_AAPL/2020_10K.html",
               "json_key": "10k_filings/Technology/Apple_AAPL/2020_10K_risks.json",
               "sub_risk_count": 23,
               "extracted_at": "<ISO>"},
              ...
            ]
          },
          ...
        },
        ...
     }
   }
   put_object 到 10k_filings/index.json

5. 同时输出 scripts/migrate_s3_layout.report.json 到本地：成功 / 跳过 / 失败 / 每条耗时

6. 旧路径不动：10k_html_datasets/ 和 risk_analysis_results/ 都不删
   filing_records_index.json 也保留（旧 API 还在读它，§1.6 切流量后再处理）

7. 控制台明细日志（每条一行）：
   [1/42] OK   Technology/Apple_AAPL/2020 23 risks 4.2s
   [2/42] SKIP Technology/Apple_AAPL/2021 (already exists)
   [3/42] FAIL International/Airbus_AIRPA/2023 reason=skip_airbus
```

### 1.6 切流量：让后端从新结构读

Part 1 跑通且 `10k_filings/index.json` 写好后，再做后端切换。这一步**单独提一个 commit**，先 dry-run 在 Railway 上验证。

#### 在 `agentcore_deploy/main.py` 顶部新增常量（不删旧的）：
```python
NEW_FILINGS_PREFIX = "10k_filings"
NEW_INDEX_KEY      = "10k_filings/index.json"
USE_NEW_LAYOUT     = os.getenv("USE_NEW_S3_LAYOUT", "0") == "1"
```

#### 改这些函数（保持旧路径作为 fallback）：

| 函数 | 改动 |
|---|---|
| `_load_index()` (L236) | 当 `USE_NEW_LAYOUT` 真时，从 `NEW_INDEX_KEY` 读，把分层 dict **flatten** 成 record list（每个 filing 一条 record，字段对齐：`record_id = f"{company_dir}_{year}_10K"`，`company`/`ticker`/`industry`/`year` 取自 index.json，`file_ext="html"`，`created_at=extracted_at`）；为 false 时走旧逻辑 |
| `_load_result(record_id)` (L256) | 解析 `record_id` 的 `<company_dir>_<year>_10K`，查 index.json 拿 `json_key`，从 `json_key` 读；旧 record_id 走旧路径 |
| `_load_company_ticker_map()` (L277) | 优先从 `10k_filings/index.json` 反构 ticker map（company_name → ticker），fallback 到旧 `company_ticker_map.json` |
| `_add_record(...)` (L695) | 增加新分支：当 `USE_NEW_LAYOUT` 真时，把 file_bytes 与 result_json 写到 `10k_filings/<industry>/<company_dir>/<year>_10K.{html,json}`，并 mutating-update index.json；为 false 时走旧逻辑 |
| `_append_agent_report_file(...)` (L1037) | 不改路径（agent_reports/ 保留），但把 record_id 字段对齐新 schema |
| `_invalidate_runtime_caches(...)` (L132) | 加判断 `key.startswith("10k_filings/")` 时同样要清 `_INDEX_CACHE`、`_RECORDS_LIST_CACHE`、`_DASHBOARD_SUMMARY_CACHE` |
| `_delete_s3_prefix(...)` 调用点 (L626/L641 等) | 不改 |

> **降级策略**：保留 `USE_NEW_LAYOUT` 环境变量做开关；Railway 先 deploy 代码（默认旧），跑一轮回归（`/api/dashboard/summary`、`/api/records`、`/api/agent/query` 任意一份），再设 `USE_NEW_S3_LAYOUT=1` 重启切换。任何异常 → 改回 0 即可恢复。

> **不要做的事**：
> - 不要在切流量这一步删 `10k_html_datasets/` 或 `risk_analysis_results/`。这两个目录用户明确说"等确认无误后再手动删"。
> - 不要把旧 `filing_records_index.json` 和新 `10k_filings/index.json` 双写——会出现两边不一致，调试非常痛苦。**新流量只写新 index**。

#### 前端零改动验证

切完 `USE_NEW_LAYOUT=1` 后，前端这几个页面必须正常：
- `frontend/src/pages/LibraryPage.jsx` → `/api/records` 列表
- `frontend/src/pages/DashboardPage.jsx` → `/api/dashboard/summary` 热力图（RPI）
- `frontend/src/pages/UploadPage.jsx` → `/api/upload/auto-fetch` & `/api/upload/manual` 入新结构
- `frontend/src/pages/ComparePage.jsx` → `/api/compare`

### 1.7 Part 1 校验清单

- [ ] `aws s3 ls s3://10k-risk-alert-app/10k_filings/ --recursive | wc -l` ≈ `(原 42 - Airbus 2) × 2 + 1 (index.json)` = 81
- [ ] `aws s3 cp s3://10k-risk-alert-app/10k_filings/index.json -` 的 industries 下每个公司的 filings 数都 ≥ 1
- [ ] 抽 3 份新 JSON，确认 `risks[].sub_risks` 不为空且和旧 JSON 不同（说明真的重跑了）
- [ ] 旧路径 `10k_html_datasets/` 与 `risk_analysis_results/` 文件数量未减少
- [ ] 在 Railway 设 `USE_NEW_S3_LAYOUT=1` 后，`/api/records` 返回 ≥ 40 条；`/api/dashboard/summary` 的 `priority_heatmap.cells` 不为空
- [ ] `/api/records/<新 record_id>` 能正确返回 result JSON

---

## Part 2 — 批量扩展 ~100 家公司

### 2.1 目标

输入用户给的公司清单（按 ticker），自动从 SEC EDGAR 拉最近 3-5 年 10-K HTML，调同一套提取逻辑，写到 Part 1 的新结构里，增量更新 `10k_filings/index.json`。

### 2.2 涉及文件

需要新建：

1. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/bulk_ingest.py` — Part 2 主脚本
2. `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/bulk_ingest_targets.py` — 公司清单（用户给的 ~100 家），用 ticker 索引

`scripts/industry_mapping.py` / `scripts/extraction_pipeline.py` Part 1 已建，复用。

### 2.3 `scripts/bulk_ingest_targets.py` 内容

以**用户原始清单**为准（注意去重 Alphabet / Meta 同时被列在多个行业），定义：

```python
# 形如：[("AAPL", "Technology"), ("MSFT", "Technology"), ...]
TARGETS = [
    # Technology
    ("AAPL",  "Technology"),
    ("MSFT",  "Technology"),
    ("GOOG",  "Technology"),         # 注：用户列表里 Technology 也写了 Alphabet；与 Communication_Services 二选一
    ("META",  "Communication_Services"),
    ("NVDA",  "Technology"),
    ("ADBE",  "Technology"),
    ("CRM",   "Technology"),
    ("INTC",  "Technology"),
    ("CSCO",  "Technology"),
    ("ORCL",  "Technology"),
    # Energy
    ("XOM",   "Energy"),
    ("CVX",   "Energy"),
    ("COP",   "Energy"),
    ("SLB",   "Energy"),
    ("EOG",   "Energy"),
    ("PXD",   "Energy"),              # Pioneer Natural Resources（注：2024-05 已被 Exxon 收购退市，SEC 仅有 2024 前的 10-K，最新只能拉到 2023）
    ("MPC",   "Energy"),
    ("VLO",   "Energy"),
    # Consumer_Cyclical
    ("AMZN",  "Consumer_Cyclical"),
    ("TSLA",  "Consumer_Cyclical"),
    ("HD",    "Consumer_Cyclical"),
    ("MCD",   "Consumer_Cyclical"),
    ("NKE",   "Consumer_Cyclical"),
    ("SBUX",  "Consumer_Cyclical"),
    ("BKNG",  "Consumer_Cyclical"),
    ("LOW",   "Consumer_Cyclical"),
    # Consumer_Defensive
    ("PG",    "Consumer_Defensive"),
    ("KO",    "Consumer_Defensive"),
    ("PEP",   "Consumer_Defensive"),
    ("WMT",   "Consumer_Defensive"),  # Part 1 已迁，会被 skip
    ("COST",  "Consumer_Defensive"),
    ("PM",    "Consumer_Defensive"),
    ("CL",    "Consumer_Defensive"),
    ("MDLZ",  "Consumer_Defensive"),
    # Communication_Services
    ("NFLX",  "Communication_Services"),
    ("DIS",   "Communication_Services"),
    ("CMCSA", "Communication_Services"),
    ("TMUS",  "Communication_Services"),
    ("VZ",    "Communication_Services"),
    ("T",     "Communication_Services"),
    # Industrials
    ("BA",    "Industrials"),         # Part 1 已迁
    ("CAT",   "Industrials"),
    ("HON",   "Industrials"),
    ("UNP",   "Industrials"),
    ("MMM",   "Industrials"),
    ("GE",    "Industrials"),
    ("LMT",   "Industrials"),         # Part 1 已迁
    ("RTX",   "Industrials"),         # Raytheon 现叫 RTX Corporation
    ("DE",    "Industrials"),
    # Financial_Services
    ("JPM",   "Financial_Services"),
    ("GS",    "Financial_Services"),
    ("MS",    "Financial_Services"),
    ("BAC",   "Financial_Services"),
    ("V",     "Financial_Services"),
    ("MA",    "Financial_Services"),
    ("BLK",   "Financial_Services"),
    ("BRK.B", "Financial_Services"),  # 注：Berkshire Hathaway B 类，find_cik 必须手动给 CIK 0001067983
    # Utilities
    ("NEE",   "Utilities"),
    ("DUK",   "Utilities"),
    ("SO",    "Utilities"),
    ("D",     "Utilities"),
    ("AES",   "Utilities"),
    ("EXC",   "Utilities"),
    # Basic_Materials
    ("LIN",   "Basic_Materials"),
    ("APD",   "Basic_Materials"),
    ("FCX",   "Basic_Materials"),
    ("NEM",   "Basic_Materials"),
    ("DOW",   "Basic_Materials"),
    ("DD",    "Basic_Materials"),
    # Real_Estate
    ("PLD",   "Real_Estate"),
    ("AMT",   "Real_Estate"),
    ("CCI",   "Real_Estate"),
    ("EQIX",  "Real_Estate"),
    ("SPG",   "Real_Estate"),
    ("O",     "Real_Estate"),
    # Healthcare
    ("UNH",   "Healthcare"),
    ("JNJ",   "Healthcare"),
    ("PFE",   "Healthcare"),
    ("LLY",   "Healthcare"),
    ("ABBV",  "Healthcare"),
    ("MRK",   "Healthcare"),
    ("TMO",   "Healthcare"),
    ("ABT",   "Healthcare"),
]

# 用户列表里 Alphabet 在 Technology 和 Communication_Services 都出现过、Meta 同理，
# 这里**只保留一份归属**（GICS 标准：Alphabet=Communication Services 但常被当 Technology；
# 这里折中：Alphabet 入 Technology，Meta 入 Communication_Services）。
# Codex 执行前向用户确认这个二选一，不要私自改。
```

去重后大约 **86 个 ticker**（用户原始描述说"约 100 家"，原列表里有 Alphabet/Meta 跨行业重复 + Walmart/Boeing/Lockheed 已迁，去重后实际目标 ≈ 80-86 个新公司）。

### 2.4 `scripts/bulk_ingest.py` 主流程

```
1. 参数：
   --start-year 2021
   --end-year   2025
   --max-failures-per-company 2     # 一个公司连失败 N 年就标 SKIP
   --concurrency 3                  # 并发，受 SEC_REQUEST_DELAY_SEC=0.5s 限制
   --skip-existing                  # 默认 True：检查 10k_filings 路径已有的 (公司,年份) 跳过
   --dry-run

2. 加载 industry_mapping.COMPANIES 和 bulk_ingest_targets.TARGETS
   预读 10k_filings/index.json 得到已存在的 set[(company_dir, year)]

3. 对每个 (ticker, industry) in TARGETS：
   a. lookup company_meta = COMPANIES[ticker]
      - 拿 display_name / sec_name / company_dir
   b. for year in range(start_year, end_year + 1):
        - if (company_dir, year) in existing_set and skip_existing: 记 SKIPPED, continue
        - 调 core/sec_edgar.download_10k_html_for_company_year(
              company_name=sec_name, year=year, ticker=ticker)
          失败：append 到 errors，记 SEC_DOWNLOAD_FAIL
        - 调 extraction_pipeline.extract_risks_for_html(html_bytes, display_name, industry_label)
        - 调 _generate_agent_priority_report 拿 agent_report 拼进 result（同 Part 1 1.5.f）
        - 调 extraction_pipeline.write_filing_to_new_layout(...)
        - 累积新条目到 INDEX_DELTA
        - 控制台一行：[12/86] LIN 2024 OK 18 risks 5.7s
        - try/except 单条公司：失败 N 年就把整个公司加入 SKIPPED；不影响下一个公司
   c. 每完成 5 个公司，原子更新一次 10k_filings/index.json
      （读 → merge INDEX_DELTA → 写。读旧 → 合 → 写整体；index 文件不大，不需要分片）

4. 收尾：
   - 输出本地 scripts/bulk_ingest.report.json：
     {
       "ok_count":  <int>,
       "skip_count":<int>,
       "fail_count":<int>,
       "by_company": {ticker: {"ok": [...], "skipped": [...], "errors": [...]}},
       "started_at":..., "ended_at":...
     }
   - 把同样的 report 也 put_object 到 s3://<bucket>/10k_filings/_ingest_reports/<ISO>.json
```

### 2.5 关键的踩坑提醒

- **SEC EDGAR 限流**：`core/sec_edgar.SEC_REQUEST_DELAY_SEC = 0.5`（每个 SEC 请求强制 sleep 0.5s）。一个公司 5 年 ≈ 4 次 SEC API（CIK 查询 + submissions + filing index + html），约 2 秒；80 公司 × 5 年 ≈ 800 秒 SEC 时间。**不要把 concurrency 调到 4 以上**，否则会被 EDGAR 封 IP。
- **Bedrock 限流**：Claude Opus 4.7 默认 quota（如未提额）只有 ~1-2 RPS。每份 10-K 平均要 1-3 次 invoke（chunk_item1a_by_headings 可能切多个 chunk）。**bulk run 全量 ≈ 80×5×2 = 800 次 invoke**，即使顺序跑也要 10 分钟以上。建议在 Railway 上跑，本地跑会因为读密钥 / 网络抖动被中断。
- **PXD（Pioneer Natural Resources）已退市**：2024-05 被 Exxon 收购，最新 10-K 是 2023 年，2024+ 必然返回"No 10-K filing found"。Codex 在 industry_mapping 里把它的 `last_year` 字段写成 2023，bulk_ingest 跑到 PXD 时只取 2019-2023。
- **Berkshire Hathaway** 用 BRK.B 走 ticker 通常找不到 CIK（SEC ticker map 只有 BRK，不分 A/B）；要在 `industry_mapping.COMPANIES["BRK.B"]["cik"]` 写死 `"0001067983"` 让 `find_cik` 优先用它。
- **Alphabet 的两个股票代码**：GOOG（C 类，无投票权）vs GOOGL（A 类，有投票权）。**SEC 同一个 CIK 0001652044**，10-K 一份。本计划默认 ticker map 用 GOOG（与现存数据保持一致）；如果要切 GOOGL，需要把 Part 1 的 `Alphabet_GOOG/` 目录重命名为 `Alphabet_GOOGL/`，工作量小但要单独跑一次重命名脚本。
- **Communication Services 的 T-Mobile / Verizon / AT&T**：`TMUS` / `VZ` / `T`。SEC ticker map 都能直接查到。
- **去重逻辑必须放在循环内**：`skip_existing` 仅靠"启动时读 index.json 一次"不够，要在每条 put_object 前再 `head_object` 一次（防同时多个 worker 跑同一公司），否则会偶发 race 导致同一年覆盖写。
- **HTML 体积**：实测 Apple 2021 = 11.8 MB，Apple 2023 = 12.3 MB。Bedrock prompt 上限 ~200KB；提取流程已在 `core/extractor._chunk_item1a_by_headings(max_tokens=35000)` 处理分块，不会爆。但 S3 存的 HTML 会很大——80 公司 × 5 年 × 5 MB ≈ 2 GB，**注意 bucket 配额与 Railway 上传带宽**。

### 2.6 错误处理与日志

- 每条 (公司,年份) 一行结构化日志：`{"ticker":..., "year":..., "status":"ok|skip|fail", "reason":..., "duration_ms":..., "sub_risks":...}`
- Python `logging` 走 stdout（Railway 会自动收日志）
- 失败分桶：`SEC_DOWNLOAD_FAIL` / `EXTRACT_EMPTY_RISKS` / `BEDROCK_THROTTLE` / `S3_WRITE_FAIL` / `UNKNOWN`
- BEDROCK_THROTTLE 自动重试 3 次（指数退避 2s/4s/8s）后才记 fail
- 单公司连续 N 次 fail 即整公司跳过

### 2.7 增量重跑

第二次跑 `bulk_ingest.py`：
- 读 `10k_filings/index.json` 构建 existing set
- 对每个 (公司,年份)：if exists in index AND `aws s3api head-object` 也存在 → SKIP
- 其余流程不变
- 重跑成本 = 0（只列 index 与 head_object）

### 2.8 Part 2 校验清单

- [ ] `10k_filings/index.json` 的 `industries` 下行业数 = 11，公司数 ≈ 80-86
- [ ] 总 filings 数 ≥ 80×3 = 240（保守按每公司 3 年算）
- [ ] 抽 5 份新公司新年份 JSON，确认 `risks[]` 非空且 `agent_report.priority_matrix.high.count > 0`
- [ ] 在 Railway 跑 `/api/dashboard/summary`，`metrics.records ≥ 240`，`metrics.companies ≥ 80`
- [ ] 前端 Library 页能搜到 LIN、PLD、UNH 等新公司
- [ ] `/api/records?industry=Real_Estate` 能返回 ≥ 6 家

---

## 3) 串行顺序建议

1. **先做** PLAN.md（Bedrock Nova → Claude Opus 4.7）—— 否则 Part 1 重跑用的是 Nova，Part 2 用的是 Opus，新旧 JSON 质量不一致违反用户"格式和质量完全一致"的硬要求。
2. Part 1 §1.5（迁移 + 重跑 42 份）
3. Part 1 §1.6（切后端读新结构 `USE_NEW_S3_LAYOUT=1`）+ 回归
4. Part 2（批量补 80+ 公司）
5. 用户验证一切 OK 后 `aws s3 rm --recursive` 删 `10k_html_datasets/` 与 `risk_analysis_results/`，删 `filing_records_index.json`、`company_ticker_map.json`（这一步**用户手动执行**，不写进自动化脚本）

---

## 4) 交付物

- `scripts/industry_mapping.py`、`scripts/extraction_pipeline.py`、`scripts/migrate_s3_layout.py`、`scripts/bulk_ingest.py`、`scripts/bulk_ingest_targets.py`、`scripts/__init__.py`、`scripts/README.md`
- `agentcore_deploy/main.py` 增加 `USE_NEW_S3_LAYOUT` 双轨读写
- `PROJECT_CHANGELOG_CN.md` 追加两节：「Part 1 — S3 数据重组完成」、「Part 2 — 批量扩展 ≈86 家公司」，每节带 commit id
- 两份 report.json（s3 上一份，本地一份）
- 三个开放问题回到用户：
  1. Airbus 要不要保留？保留就建 `International_Other/Airbus_AIRPA/`
  2. Alphabet 走 GOOG 还是 GOOGL？是否归 Technology 还是 Communication_Services？
  3. 是否同意先跑 PLAN.md 的 Bedrock 模型迁移再做本计划？

---

计划已写好，可以交给 Codex 执行。
