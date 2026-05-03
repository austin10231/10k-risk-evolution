# Upload 提取功能优化计划

> **临时计划文档**：所有阶段完成并在 `PROJECT_CHANGELOG_CN.md` 中记录后，删除本文件。
>
> **执行规则**：每完成一个 Phase 的代码改动 → **必须**先在 `PROJECT_CHANGELOG_CN.md` 新增一节（含 commit id）→ 再开始下一个 Phase。

---

## 1. 优化目标

| 维度 | 当前状态 | 目标 |
|---|---|---|
| Item 1A 定位成功率 | 不稳定（TOC 误判、现代 iXBRL 格式失败、扫描件 PDF 不稳） | ≥ 99%（覆盖 1995–2026 各种格式） |
| 风险条目抽取 | 经常 0 条；bold/italic 启发式对新版 10-K 失效 | 每份至少抽出 ≥ 90% 真实风险点；输出严格 JSON |
| 分类准确度 | 关键词字典硬编码、易跑偏 | 采用受认可的分类法（SASB / FinBERT-ESG-9），由 LLM 或本地模型完成 |
| 前端展示 | 现状 OK | **保持不变**：输出 schema 仍为 `[{"category": str, "sub_risks": [str, ...]}]` |
| 失败时行为 | 直接 `Could not extract risks…` | 多级降级（4 层 fallback），保证大概率有可用结果 |

**约束**：前端展示逻辑、`storage` 写入接口、record JSON 顶层结构都不动；所有改动集中在 `core/extractor.py`、`core/classifier.py`、`core/bedrock.py`，必要时新增 `core/sec_sections.py`。

---

## 2. 当前痛点根因（基于代码 + 调研）

1. **Item 1A 定位是纯正则**（`core/extractor.py: _locate_item1a_range`）：
   - 现代 10-K 大量使用 inline XBRL + 表格化排版，`item\s*1\s*a` 经常出现在 TOC、Exhibit Index 中；`_is_toc_region` 用前 2000 字符的 "item\d" 出现次数粗判，对长 TOC 失效。
   - 2019 年后 iXBRL 没有任何 `us-gaap` / `dei` 标签语义化标记 Item 1A 这段叙述；只能靠 DOM 标题切片，业界标准做法是用专门的解析库。
2. **bold/italic 启发式**（`extract_item1a_risks`）：很多公司用 `<font weight="700">` 或 `<span class="risk-heading">` 而非 `<b>`/`<strong>`；italic 也越来越少用。
3. **Bedrock 调用是裸文本 prompt + 自己 parse JSON**（`extractor.py: _extract_json_obj_or_array`），易碎。Bedrock Converse API 的 tool-use / JSON schema 模式现在已通用，能保证结构化输出。
4. **质量门槛 `coverage 0.85–1.25, evidence ≥ 0.55`** 把不少高质量 LLM 输出回退到坏的正则结果。
5. **Classifier (`core/classifier.py`) 实际未在主管线中调用**（主管线走 `core/bedrock.classify_risks`），但里面的关键词分类法已被业界长期证伪。
6. **PDF 路径**：Textract 拿到行文本后走 `_extract_risks_from_text_fallback` 的段落启发式（开头是 "The Company / Our / We …" 才算风险句），命中率低。

---

## 3. 目标架构（4 层 fallback）

```
HTML 输入
  ├─ Layer 1 (新): edgartools section API
  │     EDGAR Filing -> TenK -> .risk_factors
  │     覆盖 ~95% 2001 年后的现代 10-K
  ├─ Layer 2 (新): sec-parser 语义树切片
  │     按 TitleElement 找 "Item 1A" → 下个 Item 之间的内容
  ├─ Layer 3 (改造): 现有 BeautifulSoup + 正则
  │     仅作兜底；强化 TOC 检测 + style-based heading 识别
  └─ Layer 4 (新): LLM long-context 兜底
        Bedrock Claude Sonnet 4，全文档塞进去定位 Item 1A 区间

PDF 输入
  ├─ Textract 提取行文本 (保留)
  └─ 文本上跑 Layer 2/3/4 同一套切片逻辑

定位到 Item 1A 文本后，进入「抽取 + 分类」管线：
  ├─ 抽取风险条目: Bedrock Converse API + tool-use JSON Schema
  │   - tokens < 40K → 一次性 prompt
  │   - tokens ≥ 40K → 按内层小标题分块抽取后合并去重
  │   - 强制返回带 source_span 的 JSON，便于校验
  └─ 分类: 优先 LLM 按 SASB-26 类目映射；保留兼容 13 类映射给前端
```

**为什么不用 FinBERT**：本地推理需要新增 `transformers + torch` 依赖（>1GB 镜像增量），对 React + Railway + AWS Bedrock 这套部署链路成本高；Bedrock Claude 在分类任务上质量已足够，且零额外依赖。FinBERT 留作可选优化（Phase 6）。
**部署状态补充**：旧 Streamlit 主栈已迁移为 React 前端 + Railway 后端，上传优化只针对当前生产链路继续推进。

---

## 4. 分阶段实施计划

> **顺序**：每个 Phase 是一次 commit。完成后立即更新 `PROJECT_CHANGELOG_CN.md` 才可进入下一个 Phase。

### Phase 1 — 引入 `edgartools` 作为 HTML 主路径
- 新增依赖：`edgartools>=5.30` 写入 `requirements.txt`
- 新建 `core/sec_sections.py`：
  - `locate_item1a_with_edgartools(html_bytes) -> (text, meta)` —— 用 `edgar.Filing.from_html(...)` 或同效 API 取出 `risk_factors` 字段，失败抛 `SectionNotFound`
  - 同样实现 `locate_item1_overview_with_edgartools(html_bytes)`
- 改 `core/extractor.py`：
  - 新封装 `locate_item1a(html_bytes) -> str`，按 Layer 1 → 2 → 3 顺序尝试
  - `extract_item1a_risks` / `_bedrock` 改为先调用 `locate_item1a` 拿文本，再做下游
- 验收：用 5 家代表性公司（Apple 2024、JPMorgan 2024、Tesla 2024、Pfizer 2024、Lockheed 2024）跑通本地，每份至少能拿到 8 条以上风险
- **changelog 文案要点**：HTML 提取改用 edgartools 主路径，Item 1A 命中率显著提升

### Phase 2 — 加 `sec-parser` 作为 Layer 2 兜底
- 新增依赖：`sec-parser>=0.55`（按官方实际版本号写）
- 在 `core/sec_sections.py` 增 `locate_item1a_with_sec_parser(html_bytes)`：
  - 走语义树，找 TitleElement 文本匹配 `Item 1A` → 截取到下一个 Item 标题
  - 跳过 TOC 锚链接节点（祖先含 TOC class 或 `<a href="#…">`）
- 接入 `locate_item1a` 的 fallback 链
- 验收：手工挑 3 份 edgartools 失败的 filing（找老格式 1999/2003 的），sec-parser 可补救
- **changelog 文案要点**：新增 sec-parser 二级兜底，覆盖 edgartools 处理不了的边缘格式

### Phase 3 — Bedrock 抽取迁移到 Converse API + Tool-use Schema
- 改 `core/bedrock.py`：
  - 新增 `invoke_with_schema(prompt, schema, max_tokens)` 走 `client.converse(toolConfig=...)`，强制返回符合 schema 的 JSON
  - 模型保持 Claude Opus 4.7；超长 token 场景可降级到 Claude Sonnet 4（Bedrock）
- 改 `core/extractor.py: extract_item1a_risks_bedrock`：
  - 用 schema `{ "blocks": [{"category": str, "sub_risks": [{"title": str, "source_span": [start, end]}]}] }`
  - 删除 `_extract_json_obj_or_array` 在该路径上的使用
  - 删除现有 `coverage 0.85–1.25` 死板质量门槛，改为 "至少 1 条且 evidence_ratio ≥ 0.4 即接受"
- 验收：JSON parse 失败率降到 0；同样 5 家公司，输出条数与人工核对偏差 ≤ 10%
- **changelog 文案要点**：Bedrock 抽取改用 Converse API + 工具调用 JSON schema，杜绝解析失败

### Phase 4 — 长文本分块 + 合并
- 新增 `core/extractor.py: _chunk_item1a_by_headings(text, max_tokens=35000)`：
  - 优先按内层 Heading（`Risks Related to …` 这种）切分；切不动再按段落
- 抽取后合并：相同 category 名归并；按 normalized title 去重
- 验收：找 1 份长 Item 1A（金融/制药行业，>40K tokens），无截断
- **changelog 文案要点**：超长 Item 1A 自动分块并智能合并，避免被截断

### Phase 5 — 分类层重构（删掉关键词字典）
- 修 `core/bedrock.py: classify_risks`：
  - 类目改为 SASB-26 子类（保留旧 13 类的映射表），避免前端展示要改
  - 用 Converse API + schema，每条 sub_risk 一次返回 `category` + `confidence`
  - 增加批处理（一次 ≤ 20 条），减少 round-trip
- 删 `core/classifier.py` 中已无人调用的关键词字典；如果其他地方还在引用就保留薄壁包装
- 验收：随机抽 50 条已知风险，人工核对分类正确率 ≥ 85%
- **changelog 文案要点**：分类改用 SASB 标准类目 + LLM 推断，去掉旧关键词硬规则

### Phase 6 — PDF 路径对齐
- `extract_item1a_risks_from_text` 改为：Textract 行文本 → 重组成"伪 HTML"（按行字号/位置生成 `<p>`/`<h2>`） → 复用 Layer 2 的 sec-parser；失败再用现有段落启发式
- 验收：1 份扫描 PDF（找 2014–2018 年扫描版 10-K）能抽出 ≥ 5 条风险
- **changelog 文案要点**：PDF 提取与 HTML 共享语义切片管线，提升扫描件命中率

### Phase 7 — 收尾
- 跑一轮回归（10 家公司 × 2 年 = 20 份），统计 Item 1A 命中率 + 抽取条数 + 分类正确率
- 把指标写入 `PROJECT_CHANGELOG_CN.md` 的"Upload 优化总览"小节
- **删除本 plan 文件**

---

## 5. 验收度量

每个 Phase 跑下面这 5 家公司的最近 2 年 10-K（共 10 份）作为基准集：
- Apple (AAPL) — 标准科技
- JPMorgan (JPM) — 长篇金融
- Tesla (TSLA) — 大量自定义排版
- Pfizer (PFE) — 制药、Item 1A 极长
- Lockheed Martin (LMT) — 国防、TOC 复杂

| 指标 | 现状（估） | Phase 1 后 | Phase 7 后 |
|---|---|---|---|
| Item 1A 定位成功 | 5/10 | 9/10 | 10/10 |
| 平均抽取条数 | 6 | 18 | 25+ |
| JSON parse 失败 | 偶发 | 偶发 | 0 |
| 分类正确率 | ~60% | ~60% | ≥ 85% |

---

## 6. 不做的事（明确划界）

- 不动前端 `views/upload.py` 的 UI 与展示（`_show_result`、`_render_manual_upload_panel`、`_render_auto_fetch_panel`）
- 不改 `storage/store.add_record` 写入结构
- 不引入本地 GPU/Torch（FinBERT 留为未来可选项）
- 不改 record JSON 顶层 key（`company_overview` / `risks` / `ai_summary` / `agent_report`）

---

## 7. 风险与回滚

- **edgartools 网络依赖**：它内置 EDGAR 抓取，但我们传的是已下载的 html_bytes，需要确认 API 支持纯字节解析；若不支持，调用其底层 `Filing._parse_html` 或类似私有路径
- **Bedrock Converse API 区域可用性**：Claude Opus 4.7 / Claude Sonnet 4 在 `us-west-2` 的实际 modelId 或 inference profile 需按账户开通情况确认；如果用户当前的 `BEDROCK_REGION` 是别的区，要在文档里提示
- **回滚策略**：每个 Phase 一个独立 commit；任何 phase 验收不过就 `git revert` 到上一个稳定点，不影响线上 record 数据
