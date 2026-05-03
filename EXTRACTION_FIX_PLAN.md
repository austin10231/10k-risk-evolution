# EXTRACTION_FIX_PLAN.md — 提取质量修复方案

> 本计划基于对 5 份新结构 risks JSON 的真实采样得出，方案对所有公司通用。完成后按 `feedback_changelog` 规则更新 `PROJECT_CHANGELOG_CN.md`。

## 0) 数据采样（Apple/Microsoft/Chevron/Boeing/Walmart）

| file | sub_risks | blocks | 原始类别"通用"占比 | bullet 碎片占比 | General & Other 占比 | 中位 title 长度 |
|---|---|---|---|---|---|---|
| apple_2025 | 69 | 7 | 0% | **35%** | **57%** | 152 |
| microsoft_2025 | 22 | 6 | 9% | **36%** | 36% | 205 |
| chevron_2023 | 6 | 2 | 17% | 17% | 17% | 158 |
| boeing_2024 | 39 | 4 | 0% | **44%** | 18% | 126 |
| walmart_2025 | 33 | 2 | **79%** | 6% | **42%** | 199 |

绿色（≤ 健康线）：chevron 一个，但只有 6 条本身就有问题（migrate 时差点没过覆盖率门槛）。其他 4 份至少在两个维度上越线。

---

## 1) 七大共性问题（按严重度排）

### P0 — Apple_AAPL/2025 装的不是 Apple Inc，是 Apple Hospitality REIT (APLE)

**事实**：从 S3 取下 `s3://10k-risk-alert-app/10k_filings/Technology/Apple_AAPL/2025_10K.html` 检查，顶部内联 XBRL 显示 CIK `0001418121`（= Apple Hospitality REIT, NYSE 代码 APLE，CIK 0001418121）；Apple Inc 的真 CIK 是 `0000320193`。文件中找不到 "Apple Inc" / "Cupertino" / "Tim Cook"，但 "REIT"、"hotel"、"APLE" 都存在。

**根因**：原始的 legacy 文件 `s3://10k-risk-alert-app/10k_html_datasets/Apple_2025_10-K_a159.html` 是早年上传的，**当时就传错了**——上传者把 "Apple" 的品牌名和 "APLE" 的股票代码搞混。Part 1 的迁移脚本忠实地把它按文件名 token "Apple" → AAPL 映射进了 `Apple_AAPL/2025/`，但底层 HTML 一直就是错的。提取的"hotel buildings"、"REIT"、"travel patterns" 全是真实的 APLE 10-K 内容，不是提取层 bug。

**对其他公司的暗示**：所有 legacy 数据（42 份）都该过一遍 CIK 校验。光看文件名里的"Apple"不够；HTML 内的 inline XBRL CIK 才权威。

**修复方向**（不动代码、先列措施）：
- 一次性脚本：遍历 `10k_filings/<industry>/<dir>/<year>_10K.html`，从 HTML 顶部 inline XBRL 提 `<dei:EntityCentralIndexKey>` 或开头几 KB 中匹配 `^\d{10}$`、`CIK\s*\d+` 的 token，与 `industry_mapping.COMPANIES[ticker].cik`（或 SEC ticker map）比对。不一致 → 列入 `cik_mismatch_report.json`。
- 删除证实污染的 record（包括 Apple_AAPL/2025 的 html、json、index.json 条目）；让 bulk_ingest 走 SEC EDGAR 正式拉一份 Apple Inc 真实 10-K。
- 在 `scripts/migrate_s3_layout.py` 增加 `--verify-cik` 选项：迁移时直接读 HTML 头部 CIK，不匹配就 FAIL 而不是写新 layout。这样防止以后再重跑时重新污染。
- 在 `scripts/extraction_pipeline.write_filing_to_new_layout()` 加同样的 CIK 校验作为最后防线（只在 ticker 已知公司有 cik 的情况下生效）。

---

### P1 — bullet 列表被错误拆成独立 sub_risks，且 LLM 把 bullet 当作 category 名

**事实**（Apple_2025 的真实 LLM 输出）：

```
block_categories  =
  "•limited alternative uses for hotel buildings; and"          (32 个 sub_risk 挂在它下面)
  "Tax-Related Risks and Risks Related to ... REIT"             (15)
  "•changes in and/or failure to meet analysts' revenue ..."    (6)
  "•the performance of third-party managers of ..."             (5)
  "•dependence on business and leisure travel;"                 (4)
  "Risks Related to the Company's Organization and Structure"   (4)
  "Risks Related to the Company's Business and Operations"      (3)
```

7 个 block 里 4 个的"category 名"本身就是一条 bullet。Boeing_2024 也有同样模式（`"•fluctuations in international currency exchange rates;"` 当作 15 个 sub_risk 的父类别）。

碎片化定量：

| file | 35% (Apple) | 36% (MS) | 44% (Boeing) | 6% (Walmart) | 17% (Chevron) |
|---|---|---|---|---|---|

具体例子：
- Apple_2025: `"•competition from other hotels and lodging alternatives in the markets..."` 是一条独立 sub_risk
- Microsoft_2025: `"•Continuing to bring to market compelling cloud-based and AI services..."` 是独立 sub_risk
- Boeing_2024: 标题以 `"the supply chain. These factors have and may continue..."` 开头（小写 + 续句），明显是上一条切下来的尾巴

**根因**：`core/extractor.extract_item1a_risks_bedrock`（约 L865-882）的 prompt 只说"organize them into category blocks"，没说"列表项不要拆"；LLM 把 SEC 10-K 里常见的"Our results may be adversely affected by: • A • B • C"模式里每个 bullet 当成单独 risk emit 出来，子弹符号 `•` 跟着 leak 进 title（甚至 leak 进 category 名）。

**修复方向**：
- **Prompt 加显式禁令**：`core/extractor.py:865` 当前 prompt 后追加：
  > "If a risk paragraph contains a bulleted enumeration of contributing factors (lines starting with •, –, *, or '(i)/(ii)/(iii)'), keep them merged inside the parent risk's title. Do NOT emit each bullet as a separate sub_risk. Do NOT use a bullet line as a category name."
- **后处理拒收**：在 `extract_item1a_risks_bedrock` 的 `_clean_and_dedupe_ai_risk_blocks` 之后加一道清洗：
  - 任何 `category` 命中 `^[•\-\*·●]` 或 `;\s*$` 或全小写起头 → 该 block 标记为可疑，把它的所有 sub_risks 合并到上一个非可疑 block；如果没有，用 "General Risks" 作 fallback 父类。
  - 任何 sub_risk `title` 命中 `^[•\-\*·●]` → 视为前一条 sub_risk 的延续：把该 title 拼接到前一条的 title 末尾（`"; "` 连接）；如果没有前一条则丢弃。
  - 任何 `title` 以小写字母开头或以 `,` / `;` 结尾 → 视为延续，按上面规则合并。
- **二次分类 pass 触发条件加宽**：`extract_item1a_risks_bedrock` 已有的 `_looks_like_single_bucket_fallback` 只在"全部 risks 在一个桶"时触发；改为：当**最大块占比 > 60%** 或 **任一 category 名命中 bullet 模式**时也触发 re-cluster。

**统一适用性**：bullet 列表是 SEC 10-K 写作的通用范式（Apple/Microsoft/Boeing/Walmart 都在用），不针对单一公司，prompt + 后处理修复一处所有公司受益。

---

### P2 — Walmart-style 单桶退化：79% sub_risks 挤在通用 "Risk Factors" 下

**事实**：Walmart_2025 一共 33 条 sub_risks，其中 26 条 (79%) 的 `original_category = "Risk Factors"`（generic），7 条挂在 `"Legal, Tax, Regulatory, Compliance, Reputational and Other Risks"`。Chevron_2023 也类似——6 条里 5 条挂在 `"LEGAL, REGULATORY AND ESG-RELATED RISK FACTORS"`，1 条独自挂在 `"Risk Factors"`。

**根因**：现行 single-bucket 检测只看"是否只有 1 个 block + 这 1 个 block 名是 generic"。Walmart 这种 "1 个 generic 大块 + 1 个 specific 小块" 的退化形态没被检测到。

**修复方向**：
- 在 `extract_item1a_risks_bedrock` 的 `_looks_like_single_bucket_fallback` 之外，新增 `_looks_like_walmart_pattern(blocks)` 判定：**如果命中下面任意条件就触发二次分类 pass**：
  - 最大 block 的 sub_risks 数占比 ≥ 65%
  - 最大 block 的 category 名是 generic（命中 `_GENERIC_CATEGORY_NAMES = {"risk factors","general","general risks","risks","other risks","summary risk factors"}` 或纯大写"RISK FACTORS"）
  - 单个 block 包含 ≥ 20 条 sub_risks 但 category 名 ≤ 3 个词
- 二次分类 pass 已经实现（重新喂 titles 列表 + 强制 ≥ 3 个主题桶），把这条 trigger 加进去就能复用。

**统一适用性**：Walmart 是规模公司里最容易出现 "Risk Factors 单桶 + 一个 specific 子桶" 退化形态的样本。所有 retail / consumer / fin services 公司都可能这样，prompt 不变也能靠后处理 trigger 兜住。

---

### P3 — Chevron/Exxon/Kroger Item 1A 切片严重不全（上次 migrate 已暴露）

**事实**：Part 1 migrate 跑完，6 个 FAIL 全是 sub_risks < 5：

```
Chevron 2021    4 sub_risks
Chevron 2022    3 sub_risks
Exxon 2021      1 sub_risk
Kroger 2023     1 sub_risk
Kroger 2024     1 sub_risk
Kroger 2025     3 sub_risks
```

成功通过门槛的 Chevron 2023（6）/Exxon 2022（7）/Exxon 2023（7）也极度偏低；Apple 70+、NVIDIA 70+、Microsoft 22-32、Walmart 33、Boeing 39 都是合理范围，6-7 一定是切片漏了。

**根因（推断，未验证）**：`core/extractor.locate_item1a` 三层 fallback：

1. edgartools `get_sec_section("part_i_item_1a")` — 对 Chevron 这种 ALL CAPS 标题（"ITEM 1A. RISK FACTORS"）的 inline XBRL 文件可能识别失败
2. sec-parser `Edgar10QParser` — 对 10-K 的支持本来就不完整（包名就是 10Q）
3. BS4 + 正则 `_locate_item1a_range` — `_ITEM1A_END = [item 1b, item 2]`，遇到 Item 1B 立刻停。**Chevron 的 Item 1A 在 Item 1B 之前可能被 TOC 或 Item 2 误命中**，导致切到 200 字以内就停。

**修复方向**：
- 加诊断日志：`locate_item1a` 三个 provider 各返回多少字符；让运维一眼看到哪个 provider 给的不够。可以在 `core/extractor.py:locate_item1a` 失败链每一段加 `print(file=sys.stderr, ...)`，量很少不会刷屏。
- 把 BS4 fallback 的 `_locate_item1a_range` 加保护：**起点和终点之间必须至少 X 字符（比如 5000）**，否则视为切片失败、抛 `SectionTooShort` 让上层 fallback 链尝试别的 provider 或者扔回 LLM long-context。
- 长尾兜底：当三层都失败，把整份 HTML 的 `_full_text` 中关键字 `risk factors` 后第 200K 字符直接喂 LLM，让 LLM 自己定位。代价高（一次 long-context invoke），但只对 Chevron/Exxon/Kroger 这种边缘格式触发，频率低。
- 单独写诊断脚本 `scripts/diagnose_item1a_locator.py`：对失败的 6 个 record（HTML 已经在 S3 上，无需重抓）跑 `locate_item1a` 三层，把每层的字符数 + 前 500 字打印出来，从证据决定真实根因。

**统一适用性**：能源（Chevron/Exxon/COP/MPC/VLO）、零售（Kroger/Costco/Target）、银行（JPM/BAC）这些行业的 10-K 排版偏老派 / 表格密集，bulk_ingest 跑全量大概率会再撞同样问题。先解决 6 个已知失败案例，相当于建立 regression suite。

---

### P4 — dashboard_category 的关键词映射有真实误分类

**事实**（直接从样本里挑出的明显错例）：

```
Apple    title="•business interruptions, regulatory costs, financial loss and equipment loss
                 due to cyber-attacks and other technology disruptions..."
         dashboard = "Legal & Regulatory"   ← 应是 Technology & Cybersecurity
         (因为 title 里有 "regulatory" 一词)

Apple    title="Technology is used in operations, and any material failure, inadequacy,
                 interruption or security failure of that technology..."
         dashboard = "General & Other"      ← 应是 Technology & Cybersecurity
         (因为关键词表里 "Technology & Cybersecurity" 没有裸 "technology"，只有 cyber/data breach 等)

Boeing   title="Some of our and our suppliers' workforces are represented by labor unions,
                 which may lead to work stoppages."
         dashboard = "People & Governance"  ← 严格说是对的，但提到 "suppliers" 应被 supply chain bucket 抢
         (这是双标签真实情况，需要 tie-breaking 规则)

Boeing   title="Unauthorized access to our, our customers' and/or our suppliers' information
                 and systems could negatively impact our business."
         dashboard = "Technology & Cybersecurity"  ← 这条对了

Walmart  title="If the quality or safety of products we sell ... fails to meet our customers'
                 expectations or applicable regulatory requirements..."
         dashboard = "Strategy & Market"   ← 应是 Legal & Regulatory（"regulatory requirements"）
         或 Operations & Supply Chain（"product quality/safety"）

Walmart  title="Our digital platforms, which are increasingly important to our business
                 and continue to grow in complexity and scope..."
         dashboard = "General & Other"      ← 应是 Technology & Cybersecurity
         (关键词表里没有 "digital platform" 这个常见 SEC 用语)
```

**根因**（结合 `agentcore_deploy/main.py:_RISK_CATEGORY_KEYWORDS` 和 `_normalize_risk_category`）：

1. **优先级冲突没有 tie-breaking**：title 里同时含 "cyber" 和 "regulatory" 时，权重相同就是 alphabetical 命中，"Legal & Regulatory" 字典序在 "Technology & Cybersecurity" 前面 → Legal 赢。但语义上 cyber 应该胜过附带的 regulatory 描述。
2. **关键词覆盖不全**：
   - Technology & Cybersecurity 缺：`"technology"` (单字)、`"digital platform"`、`"IT systems"` 普通拼法
   - Operations & Supply Chain 缺：`"product safety"`、`"product quality"`、`"production disruption"`
   - Legal & Regulatory 缺：`"regulatory requirements"`（关键词只有 "regulation"/"regulatory" 单字，title 里出现 "regulatory requirements" 也只 +1）
3. **LLM fallback 触发条件太严**：当前 score < 3 才 fallback，多关键词命中但权重都低的情况（每个权重 1，总 5）不触发 fallback，命中错的桶。

**修复方向**：
- **加 tie-breaker 规则表**：在 `_normalize_risk_category` 排序时，对常见歧义 pair 加优先级覆盖。例如：
  - 当 Technology & Cybersecurity 与 Legal & Regulatory 得分相等时，看 title 是否包含 strong cyber phrase（"cyber-attack"/"data breach"/"information security"），是 → Tech 胜
  - 当 Operations & Supply Chain 与 People & Governance 同分，看是否有 "supplier"/"supply chain"，是 → Operations 胜
  - 当 ESG & Sustainability 与 Legal & Regulatory 同分，看是否有 "climate"/"emission"/"greenhouse"，是 → ESG 胜
- **补关键词**（写进 `_RISK_CATEGORY_KEYWORDS` 但保持权重克制 1-2 防止过度触发）：
  - Technology & Cybersecurity: `"digital platform"`, `"IT system"`, `"information system"`, `"technology disruption"`, `"data integrity"`
  - Operations & Supply Chain: `"product safety"`, `"product quality"`, `"production"`, `"merchandise availability"`
  - Legal & Regulatory: `"regulatory requirement"`, `"regulatory action"`
  - Strategy & Market: `"customer demand"`, `"consumer preference"`
- **降低 LLM fallback 触发阈值**：当前 `score < 3` 触发 fallback；改成 `score < 2` 触发，而且关键词命中虽到 3 但属于"全是低权重 (=1) 加和"的情况也触发（这通常意味着没有 strong signal）。

**统一适用性**：tie-breaker + 词表补充对所有公司同时受益。每加一条 tie-breaker 都该配实际 title 例子写在注释里。

---

### P5 — General & Other 占比过高（Apple 57% / Walmart 42% / MS 36%）

**事实**：5 份里 3 份越过 25% 健康线。Apple_2025 因为是 REIT 数据，REIT 特有的 risk（hotel 经营、租户违约等）跟我们的 9 桶设计本来就 mismatch；Walmart 主要是上面 P4 说的关键词缺失，digital platform/strategic alliance 这类常见零售 risk 词没人捡。Microsoft 36% 一部分是真•落不到桶（"challenging economic conditions also may impair the ability of our customers to pay..."），一部分是 P4 的 cyber title 被分错。

**根因**：P4 关键词映射 + P1 bullet 碎片导致很多 title 是半截句子，关键词命中率天然低。

**修复方向**：
- P1 + P4 修完，G&O 比例自然会降下来；不需要额外改 dashboard 桶。
- 如果修完后某行业（比如 Apple_AAPL/2025 因为是 REIT）依然很高，那是 9 桶分类法本身的限制，不是 bug——但这种情况会因为 P0 修复（Apple_AAPL/2025 用真 Apple Inc 数据）自动消失。

---

### P6 — original_category 有时被 dashboard_category 名"反向污染"

**事实**：5 份里 4 份的 LLM 自由分类都不重复 dashboard 桶名（apple/microsoft/chevron/boeing 的 LLM 给的都是 SOX 标题级原文），只有 walmart_2025 的 26 条挤在 generic "Risk Factors" 下，看起来是没分类。

但是再细看 Microsoft：`"Risk Factors"` 这 2 条 generic 的并存于 6 个具体 block 中。说明 LLM 混着用——大部分块用文档子标题，少数 fallback 用根标题。

**修复方向**：
- 在 `_clean_and_dedupe_ai_risk_blocks` 之后多加一步 "block 名净化"：检查每个 block 的 category name，如果是 generic（命中 `_GENERIC_CATEGORY_NAMES`），尝试合并到同份输出中第一个非 generic 的 block；只有当所有 block 都是 generic 时才保留一个总桶 "General Risks"。
- 这件事和 P2（Walmart pattern）是一体的，触发同一段后处理。

---

## 2) 修改文件清单（待执行，本计划不动代码）

需要改：

| 文件 | 改动 | 关联问题 |
|---|---|---|
| `/Users/mr.tian/Desktop/10k-risk-evolution/core/extractor.py` | (a) `extract_item1a_risks_bedrock` 的 prompt 加 bullet 禁令；(b) 后处理 `_clean_and_dedupe_ai_risk_blocks` 加 bullet/lowercase/trailing-comma 合并；(c) 二次分类 trigger 加宽（最大 block 占比 > 60% 或 category 名是 generic 也 trigger）；(d) `locate_item1a` 加 stderr 诊断 + 5K 字符下界保护 | P1 / P2 / P3 / P6 |
| `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py` | 重写 `_RISK_CATEGORY_KEYWORDS` 加补漏词条；`_normalize_risk_category` 加 tie-breaker 表；LLM fallback 阈值从 `<3` 调到 `<2` + 全 weight=1 也触发 | P4 / P5 |
| `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/extraction_pipeline.py` | `extract_risks_for_html` 上传前对 HTML 头部 inline XBRL 提 CIK，与 `industry_mapping.COMPANIES[ticker].cik` 对照（仅在该字段非空时启用） | P0 |
| `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/migrate_s3_layout.py` | 新增 `--verify-cik` 选项，与脚本扫描结果一起跑 | P0 |

需要新增：

| 文件 | 用途 | 关联问题 |
|---|---|---|
| `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/diagnose_item1a_locator.py` | 对 P3 的 6 个失败 record 跑 `locate_item1a` 三层各自字符数 + 前 500 字，找出真根因（edgartools 没识别 / sec-parser 没识别 / BS4 切短） | P3 |
| `/Users/mr.tian/Desktop/10k-risk-evolution/scripts/audit_legacy_cik.py` | 一次性扫所有 `10k_filings/<industry>/<dir>/<year>_10K.html` 的内嵌 CIK，比对 `industry_mapping.COMPANIES[ticker].cik`，输出 `cik_mismatch_report.json` | P0 |

**不要改**：
- `agentcore_deploy/agent.py` — RPI / priority 逻辑与本计划无关
- `frontend/src/*` — 前端只读字段，dashboard_category 改对了自动同步
- `core/sec_sections.py` — edgartools / sec-parser 集成本身没问题，问题在调用层

---

## 3) 修复顺序与提交策略

| commit | 内容 | 风险 |
|---|---|---|
| 1 | P0 — CIK 校验脚本 + 删 Apple_AAPL/2025 record + 让 bulk_ingest 重抓 Apple Inc 真 10-K | 中（动 S3，但只针对 1 条已确诊污染数据） |
| 2 | P1 + P2 + P6 — `core/extractor.py` 的 prompt 改 + 后处理合并（bullet 禁令、generic block 合并、二次分类 trigger 加宽） | 中（影响所有未来抽取） |
| 3 | P4 — `_RISK_CATEGORY_KEYWORDS` 补词 + tie-breaker + LLM fallback 阈值调整 | 低（纯映射改进，最坏退化到现有行为） |
| 4 | P3 — `locate_item1a` 诊断 + 5K 下界保护 + 长尾 LLM tail；先建诊断脚本拿真证据再写代码 | 中（提取层调用顺序变） |
| 5 | 跑 `migrate_s3_layout.py --write --force-reextract` 重抽全部 34 record；跑 `bulk_ingest.py` 补失败 record 与 Apple Inc 2025 真数据 | 中（再花一轮 Bedrock 钱） |

每个 commit 完成都更新 `PROJECT_CHANGELOG_CN.md`。

---

## 4) 修复后验证清单（再次抽这 5 份做对比）

- [ ] **P0**：Apple_AAPL/2025 的 HTML 头部 CIK = `0000320193`（不是 APLE 的 `0001418121`）；overview.background 提到 "Cupertino" 或 "iPhone"
- [ ] **P1**：5 份 risks JSON 里没有 title 以 `•` 开头；`block.category` 没有以 `•` 开头；fragment-like 占比 < 10%
- [ ] **P2**：单一 block 占比最大 ≤ 50%（Walmart 不再 79%）
- [ ] **P3**：Chevron/Exxon/Kroger 的 sub_risks ≥ 15 每份
- [ ] **P4**：含 "cyber" 的 sub_risk 不会被分到 Legal & Regulatory；含 "supply chain" 不会被分到 Financial & Liquidity
- [ ] **P5**：5 份 G&O 占比都 ≤ 25%
- [ ] **P6**：每份 risks JSON 的 block_categories 中 generic 名（"Risk Factors" 等）数量 ≤ 1

跑这一组检查的脚本已经在我此次审计里写好了，可以直接复用进 CI。

---

## 5) 不做的事（明确划界）

- 不改 9 桶 dashboard 分类法本身（那是产品决定，不是 bug）
- 不删除现有 Apple/Microsoft/Boeing/Walmart 的 risks JSON——P1+P2+P6 修完后 `--force-reextract` 会覆盖，旧数据自然替换
- 不动 SEC EDGAR 抓取链 (`core/sec_edgar.py`)——P0 是上传源头数据污染，不是 EDGAR 抓错
- 不引入新的 LLM fallback 模型——所有 fallback 仍走当前 Claude Opus 4.7
- 不在前端做任何分类修复，所有改动集中在后端 + 脚本

---

## 6) 待用户拍板的开放问题

1. **P0 处理力度**：是否同意把现有 `10k_filings/Technology/Apple_AAPL/2025_*` 直接删掉、由 bulk_ingest 重新拉 Apple Inc 真 10-K？或者先归档到 `10k_filings/_quarantine/APLE_2025_*`，留个证据？
2. **P3 长尾 LLM tail**：Chevron/Exxon/Kroger 这种切片失败的边缘情况，要不要花 long-context invoke 钱兜底？或者接受这些边缘 record 进不了新 layout、只在 dashboard 上看作"评分失败 record"？
3. **重抽全部 34 record 的成本**：每次 Bedrock 抽取约 6-10 秒；force-reextract 等于再花一遍 ~5 分钟 + 同等花费。是否同意？
4. **P0 audit 范围**：是否要对全部 34 个 legacy-migrated record 都做 CIK 比对？还是只针对 Apple_AAPL/2025 这一例做处理就够？

---

计划已写好，可以交给 Codex 执行。
