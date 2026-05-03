# CATEGORY_OPTIMIZATION_PLAN.md — 风险因子分类逻辑 + Item 1 Overview 修复

> 本计划由 Claude 生成，交给 Codex 执行。完成后按 `feedback_changelog` 规则更新 `PROJECT_CHANGELOG_CN.md`（含 commit id）。

---

## 0) 问题诊断（实地验证后修正用户原始描述）

### 0.1 用户的现象

> Apple 2024 的 34 条风险因子，33 条都被分到了 Strategy & Market

### 0.2 我对线上数据的 ground-truth 检查（取自 `s3://10k-risk-alert-app/risk_analysis_results/Apple_2024_10-K_d69b.json`）

```
overview.background = "(Could not extract Item 1 overview.)"
risks = [
    {category: "Risk Factors", sub_risks: [...34 条...]}
]
```

**真相和用户描述不完全一致**：

1. 提取阶段 LLM **并没有**被强制塞进固定分类。`core/extractor.py:865` 的 prompt 只要求"organize them into category blocks"，没给固定列表。**LLM 现在是自由分类的**。
2. Apple 2024 的实际产物里，LLM **退化成了一个超大块** `"Risk Factors"`（兜底值，见 `core/extractor.py:183` `current_cat = "Risk Factors"`），34 条全在里面。也就是说 LLM 这次根本没分类——分类工作没做。
3. 全部塞到 Strategy & Market 是**展示层**做的：`agentcore_deploy/main.py:_normalize_risk_category` 用关键词匹配把 `"Risk Factors"` 这个字符串往 9 大类里推；该函数的 `Strategy & Market` 关键词列表里恰好包含 `"risk factors"` / `"general risk"` / `"business risk"` / `"industry"` / `"market"` 这些极其宽泛的词（main.py:943-962），结果把 Apple 这种"分类未做"的兜底值 + 任何含有 industry/market/business 字样的 sub-title 全部抓到 Strategy & Market 桶。

所以**用户的两层方案是对的，但每层要修的代码点和原因稍微不一样**：

- **第一层（提取）**：prompt 已经是自由分类。需要做的不是"放开"，而是 **(a) 引导 LLM 真去分多个类**（不要退化成单桶 "Risk Factors"），**(b) 在 schema/JSON 里显式保留 `original_category` 字段**，以及 **(c) 在 LLM 退化为单桶时启用 secondary 分类 pass**。
- **第二层（展示映射）**：现有 `_normalize_risk_category` 关键词太贪心，需要 **(a) 重写关键词权重表**（"risk factors" 这种泛词不能再触发任何具体桶），**(b) 增加 LLM fallback** 处理关键词不命中的边缘场景，**(c) 把映射结果写到 sub_risk 的 `dashboard_category` 字段而不是覆盖 `category`**——保留 LLM 的 `original_category` 永久可追溯。

### 0.3 Item 1 Overview 失败的根因

Apple 2024 的 background 是 `"(Could not extract Item 1 overview.)"`。链路：

```
main.py:_manual_extract_result
  → extract_item1_overview_bedrock(html, "Apple", "Technology")        core/extractor.py:752
       fallback = extract_item1_overview(html, ...)                     L739
            → locate_item1_overview(html)        # edgartools/sec-parser  L415
                返回非空 item1_text
            → _extract_overview_from_text(
                  f"{item1_text}\n\nItem 1A. Risk Factors", ...)        L747
                   ↓
                   starts = list(_ITEM1_START.finditer(text))           L118
                   _ITEM1_START = r"item\s*1[\.\:\s—–\-]+\s*bus(?:iness)?"  L33
                   ↑
                   item1_text 是 edgartools **已经切好的 Item 1 正文**，
                   里面通常**不会再次出现** "Item 1. Business" 这个标题字符串
                   → starts == [] → raw == "" → background == "(Could not extract Item 1 overview.)"
```

**Bug**：`extract_item1_overview` 把 edgartools/sec-parser 已经切好的 section text 又喂回 `_extract_overview_from_text`，后者还在用 raw-filing-level 的正则去找 "Item 1. Business" 标题，自然找不到。LLM bedrock 路径读到 fallback 的失败字符串，然后 LLM 调用本身可能成功也可能失败 —— 但**只要 fallback 错了，就算 LLM 成功，主流程也是把 fallback 当 baseline**（看 `extract_item1_overview_bedrock:761-801` 的逻辑）。

注：`extract_item1_overview_bedrock` 自己另起 `item1_text = locate_item1_overview(html_bytes)` (L767) 直接喂给 LLM；当 LLM 返回 parseable JSON 时**本应**用 LLM 的结果。Apple 的 result JSON 里 background 是 fallback 失败串而不是 LLM 输出，说明 **LLM 调用要么抛异常进 except、要么返回不可 parse**。考虑到我们刚把模型从 Nova 切到 Claude Opus 4.7，很可能有一条 silently failed —— 这个要修但单独诊断。

---

## 1) 目标

| 编号 | 目标 | 衡量 |
|---|---|---|
| G1 | LLM 提取时真正分多个类，单桶兜底"Risk Factors" 不再出现 | Apple 2024 重跑后 risks 块数 ≥ 4 |
| G2 | sub_risk 的 JSON 里同时保留 `original_category`（LLM 给的）和 `dashboard_category`（映射到 9 大类） | result JSON 抽样可见两个字段 |
| G3 | 关键词映射不再把任何含 "industry/market/business risk/risk factors" 的条目无脑归入 Strategy & Market | Apple 2024 的 34 条不再 33 条都进 Strategy & Market |
| G4 | 关键词映射不命中（score=0）时不再硬塞 Strategy & Market，先调一次 LLM 二次裁决；LLM 也不可用时才回到 General & Other | 抽样 5 份新 result，关键词不命中的条目 dashboard_category 合理 |
| G5 | Item 1 Overview 不再返回 "(Could not extract Item 1 overview.)"，至少 90% 公司能拿到 ≥ 200 字的 background | Apple/JPMorgan/Tesla/Pfizer/Lockheed 五家公司 background 长度 ≥ 200 |
| G6 | Python 端与前端 records.js 的分类映射逻辑保持单一数据源（前端不再各跑一份关键词表） | `frontend/src/lib/records.js` 不再自己跑分类映射，直接用 API 返回的 `dashboard_category` |

---

## 2) 涉及文件（绝对路径）

需要修改：

1. `/Users/mr.tian/Desktop/10k-risk-evolution/core/extractor.py`
   - 改 `extract_item1a_risks_bedrock` 的 prompt + JSON schema：要求多类、加 `original_category`
   - 修 `extract_item1_overview` & `extract_item1_overview_bedrock`：解决"已切片文本被当 raw filing 重新搜索"的 bug
2. `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py`
   - 重写 `_normalize_risk_category` 关键词权重表（删除歧义词）
   - 新增 `_classify_with_llm_fallback`：关键词命中失败时调一次 LLM
   - 改 `_extract_sub_risks`：保留 `original_category` + 新增 `dashboard_category`
   - dashboard 聚合逻辑（`_dashboard_summary`）改成读 `dashboard_category`，不再实时调用 `_normalize_risk_category`（因为现在已经在写入时计算并落盘）
   - 在 `_manual_extract_result` / `_auto_fetch_and_extract` 写入前对 risks 跑一次 normalize，把 dashboard_category 写进每条 sub_risk
3. `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/lib/records.js`
   - 删除前端的 `RISK_CATEGORY_KEYWORDS` 与 `normalizeRiskCategory`，改成"优先读 sub_risk 自带的 `dashboard_category` 字段；缺省回退到 `category` 原值"
4. `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/pages/ComparePage.jsx`
   - 它现在通过 `normalizeRiskCategory(category)` 单参数调用做分类——改成读 `row.dashboard_category` (后端已经填好)
5. `/Users/mr.tian/Desktop/10k-risk-evolution/PROJECT_CHANGELOG_CN.md` — 追加一节
6. （可选）`/Users/mr.tian/Desktop/10k-risk-evolution/scripts/reclassify_existing_records.py` — 一次性把已存在的 ~42+ 条 record 的 result JSON 跑一遍 normalize，写回 dashboard_category（避免老数据继续显示错分类）

不要改：
- `core/sec_sections.py` — edgartools/sec-parser 集成已经写好，本计划不动它
- `agentcore_deploy/agent.py` — RPI 评分流程与本计划无关
- `core/comparator.py` — 它返回的 risks 已经带 `category` 字段，前端的 normalize 改完后自动适配

---

## 3) 第一层：提取阶段（核心改在 `core/extractor.py`）

### 3.1 改 `extract_item1a_risks_bedrock` 的 schema

`core/extractor.py:830-861` 当前 schema：每个 sub_risk 有 `title` + `source_span`。需要扩展：

```python
schema = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},        # LLM 自由命名
                    "sub_risks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "source_span": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2, "maxItems": 2,
                                },
                            },
                            "required": ["title", "source_span"],
                        },
                    },
                },
                "required": ["category", "sub_risks"],
            },
        }
    },
    "required": ["blocks"],
}
```

`category` 字段含义不变（仍由 LLM 自由命名），但 prompt 要修。

### 3.2 改 prompt 引导多类（`core/extractor.py:865-882`）

把当前 prompt 替换为：

```python
prompt = f"""You are an expert SEC 10-K parser.

Extract risk factors from Item 1A text and organize them into category blocks.
Use exact wording from source risk statements whenever possible.

Company: {company_name or "Unknown"}
Chunk: {chunk_index} of {len(item1a_chunks)}

Input text (Item 1A):
\"\"\"{item1a_chunk}\"\"\"

Categorization rules:
- 10-K Item 1A typically contains 3-8 distinct risk categories. Use the SOURCE TEXT's
  own subheadings (e.g., "Macroeconomic and Industry Risks", "Business Risks",
  "Legal and Regulatory Compliance Risks", "Financial Risks", "General Risks") as
  category names whenever the source provides them.
- If the source has no explicit subheadings, INFER 3-6 categories from the risk
  themes (e.g., "Supply Chain Concentration", "Regulatory Compliance",
  "Cybersecurity", "Talent & Workforce", "Foreign Operations & Currency").
- DO NOT return a single bucket called "Risk Factors", "General", "Risks", or
  "Other" containing all risks — that is a failure mode and will be rejected.
- Each category should ideally hold 2–10 sub-risks. Avoid categories with only one
  sub-risk unless the source clearly isolates that risk.
- Category names should be 2–6 words, capitalized as titles.

Output rules:
- Return data by calling the provided structured output tool.
- Each block must have category and sub_risks.
- Each sub_risk must have title and source_span [start, end] character offsets
  from the input text above (so we can verify grounding).
- Preserve the risk's original wording where reasonable.
- Do not include any keys outside the provided schema."""
```

### 3.3 添加单桶兜底检测 + 二次分类 pass

在 `extract_item1a_risks_bedrock` 主循环外（`core/extractor.py:898 merged = _merge_risk_blocks(all_cleaned)` 之后），加一段：

```python
def _looks_like_single_bucket_fallback(blocks: list[dict]) -> bool:
    """Detect the 'one giant Risk Factors block' degenerate case."""
    if not isinstance(blocks, list) or len(blocks) > 1:
        return False
    if not blocks:
        return False
    only = blocks[0]
    cat = str(only.get("category", "") or "").strip().lower()
    n_subs = len(only.get("sub_risks", []) or [])
    return cat in {"risk factors", "general", "risks", "other", "general risks"} and n_subs >= 5

# 在 merged = _merge_risk_blocks(all_cleaned) 之后：
if _looks_like_single_bucket_fallback(merged):
    # Secondary pass: ask LLM to re-split this single bucket into themed categories.
    titles = [str(s.get("title", "")) for blk in merged for s in blk.get("sub_risks", [])]
    resplit_schema = {
        "type": "object",
        "properties": {
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "indices": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["category", "indices"],
                },
            }
        },
        "required": ["blocks"],
    }
    titles_listing = "\n".join(f"{i}. {t[:300]}" for i, t in enumerate(titles))
    resplit_prompt = f"""The previous extraction returned all {len(titles)} risks under one bucket.
Re-cluster them into 3–6 themed categories. Each category needs 2–10 risks.

Risks (numbered):
{titles_listing}

Return blocks where each block has:
- category: the theme name
- indices: list of 0-based indices from the list above
"""
    try:
        resplit = invoke_with_schema(
            resplit_prompt, resplit_schema, max_tokens=2500,
            tool_name="recluster_risks",
            tool_description="Re-cluster a flat risk list into 3–6 themed categories.",
        )
        new_blocks = []
        for b in (resplit.get("blocks") or []):
            cat = str(b.get("category", "")).strip()
            idxs = [int(i) for i in (b.get("indices") or []) if isinstance(i, (int, float))]
            subs = [merged[0]["sub_risks"][i] for i in idxs if 0 <= i < len(titles)]
            if cat and subs:
                new_blocks.append({"category": cat, "sub_risks": subs})
        if new_blocks and len(new_blocks) >= 3:
            merged = new_blocks
    except Exception:
        pass
```

`_looks_like_single_bucket_fallback` 是私有 helper，只用一次。如果二次分类失败，保留原单桶，下游展示层（§4）的 LLM fallback 会再兜一道。

### 3.4 `_normalize_ai_risk_blocks` / `_clean_and_dedupe_ai_risk_blocks` 不需要改

它们只过滤空字段；现有逻辑兼容多类输出。

### 3.5 提取层校验

抽样 5 份重跑：Apple 2024、JPMorgan 2024、Tesla 2024、Pfizer 2024、Lockheed Martin 2024。每份的 `risks` 顶层数组长度应 ≥ 3。

---

## 4) 第二层：展示映射（`agentcore_deploy/main.py`）

### 4.1 重写 `_RISK_CATEGORY_KEYWORDS`（`main.py:827-963`）

**核心原则**：删除所有"宽到能匹配任何 10-K 风险"的词。下面是建议的新关键词表（注释里写明删了什么 / 加了什么）：

```python
_RISK_CATEGORY_KEYWORDS: Dict[str, List[tuple[str, int]]] = {
    # 每条 (phrase, weight)；weight 越大优先级越高
    # 下面那些 weight=3 是该桶的"金标"词；weight=1 的可以被竞争桶反超
    "Capital Markets": [
        ("common stock", 3), ("stockholder", 3), ("shareholder", 2),
        ("market price of our", 3), ("dividend", 3), ("dilution", 3),
        ("equity offering", 3), ("ownership of our stock", 3),
        ("public offering", 2), ("listing", 1),
    ],
    "Financial & Liquidity": [
        ("liquidity", 3), ("cash flow", 3), ("debt", 2), ("credit risk", 3),
        ("interest rate", 3), ("refinancing", 3), ("impairment", 3),
        ("foreign exchange", 3), ("currency", 2), ("solvency", 3),
        ("capital resources", 3), ("inflation", 2), ("hedging", 2),
        # 删 "financial risk" / "financial condition" / "financial statements"
        # / "profitability" / "revenue" — 每份 10-K 都有这些词，会污染
    ],
    "Legal & Regulatory": [
        ("regulation", 3), ("regulatory", 3), ("compliance", 2),
        ("litigation", 3), ("antitrust", 3), ("sanction", 3), ("bribery", 3),
        ("intellectual property", 3), ("patent", 2),
        ("data privacy law", 3), ("gdpr", 3), ("ccpa", 3),
        ("tax-related", 2), ("status as a reit", 3),
        # 删 "legal" / "laws" / "government" / "policy" / "policies" — 太泛
    ],
    "Technology & Cybersecurity": [
        ("cybersecurity", 3), ("cyber attack", 3), ("data breach", 3),
        ("information security", 3), ("ransomware", 3), ("system outage", 3),
        ("it system", 3), ("personal information", 2),
        ("artificial intelligence", 2), ("generative ai", 3),
        # 删 "technology" / "software" / "cloud" / "digital" — 太泛
    ],
    "Operations & Supply Chain": [
        ("supply chain", 3), ("supplier", 3), ("procurement", 2),
        ("manufacturing", 2), ("logistics", 2), ("distribution", 2),
        ("inventory", 2), ("business continuity", 3),
        ("single source", 3), ("contract manufacturer", 3),
        # 删 "operations" / "operational" — 太泛；保留具体术语
    ],
    "People & Governance": [
        ("workforce", 3), ("union", 3), ("human capital", 3),
        ("talent", 3), ("retention of key", 3),
        ("internal control", 3), ("succession", 2), ("board of directors", 3),
        # 删 "employment" / "labor" / "management" / "leadership" / "executive"
        # — 这些词在每份 10-K 都频繁出现且经常出现在其他桶里
    ],
    "ESG & Sustainability": [
        ("climate change", 3), ("greenhouse gas", 3), ("carbon emissions", 3),
        ("environmental regulation", 3), ("esg", 3),
        ("sustainability", 2), ("renewable", 2),
        # 删 "environment" / "social responsibility" / "emissions" 单字 — 太泛
    ],
    "Strategy & Market": [
        ("competition", 3), ("competitive landscape", 3),
        ("market share", 3), ("pricing pressure", 3),
        ("customer concentration", 3), ("new entrants", 2),
        ("brand", 2), ("reputation", 2), ("geopolitical", 3),
        ("macroeconomic", 3),
        # 大幅瘦身：删 "strategy" / "strategic" / "market" / "industry"
        # / "business risk" / "general risk" / "risk factors" / "demand"
        # / "growth" — 这些是吸尘器词，是当前 bug 的元凶
    ],
}
```

> ⚠️ **关键决策**：以上数据结构由 `List[str]` 升级为 `List[tuple[str, weight]]`。`_normalize_risk_category` 也要相应改：累加 weight 而不是计数。

### 4.2 改 `_normalize_risk_category`（`main.py:966-994`）

```python
def _normalize_risk_category(
    category: Any,
    title: Any = "",
    labels: Optional[List[Any]] = None,
) -> tuple[str, int]:
    """
    Returns (dashboard_category, score).
    score == 0  → no keyword matched (caller may invoke LLM fallback).
    score >= 1  → one or more keywords matched; best bucket selected.
    """
    cat_text = str(category or "").strip()
    title_text = str(title or "").strip()
    label_text = " ".join([str(x or "").strip() for x in (labels or []) if str(x or "").strip()])
    full_text = " ".join([cat_text, title_text, label_text]).strip().lower()
    if not full_text:
        return "General & Other", 0

    scores: Dict[str, int] = {k: 0 for k in FIXED_RISK_CATEGORIES}
    cat_lower = cat_text.lower()

    for target, weighted in _RISK_CATEGORY_KEYWORDS.items():
        for phrase, weight in weighted:
            if phrase in full_text:
                scores[target] = scores.get(target, 0) + weight
            if phrase in cat_lower:
                scores[target] = scores.get(target, 0) + weight  # extra weight when LLM category itself contains the phrase

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_cat, best_score = ranked[0]
    if best_score >= 3:                # 至少匹配一个高权重 phrase
        return best_cat, best_score
    if best_score >= 1:                # 弱匹配：可信度低，由调用方决定是否再问 LLM
        return best_cat, best_score
    return "General & Other", 0        # ← 不再硬塞 Strategy & Market！
```

> ⚠️ 返回值类型从 `str` 变成 `tuple[str, int]`。现在 4 个调用点（`main.py:1010`、`main.py:1498`、`frontend records.js`）都要更新。

### 4.3 新增 `_classify_with_llm_fallback`

在 `main.py:_normalize_risk_category` 函数下面新增：

```python
_LLM_CLASSIFY_CACHE: Dict[str, str] = {}

def _classify_with_llm_fallback(
    category: str, title: str, labels: List[str],
) -> str:
    """When keyword scoring is too weak (<3), ask LLM to pick one of 9 dashboard buckets."""
    cache_key = (str(category or "") + "||" + str(title or ""))[:300]
    if cache_key in _LLM_CLASSIFY_CACHE:
        return _LLM_CLASSIFY_CACHE[cache_key]

    bucket_list = "\n".join(f"- {c}" for c in FIXED_RISK_CATEGORIES)
    prompt = f"""You map an SEC 10-K risk factor into ONE of these 9 dashboard categories:
{bucket_list}

Risk source category (LLM-named): {category!r}
Risk title: {title!r}
Labels: {labels!r}

Return ONLY a JSON object: {{"bucket": "<exactly one of the 9 names>"}}.
"""
    try:
        invoke = _get_llm_invoke()                                  # 已存在 main.py:3308
        raw = invoke(prompt, 60)                                    # max_tokens=60
        # 复用 _extract_json_obj 之类的 helper；最简单做 json.loads + 兜底
        import json
        try:
            obj = json.loads(raw.strip().strip("`").strip())
        except Exception:
            # 最后兜底：在原始 raw 里找第一个 FIXED_RISK_CATEGORIES 命中
            obj = {}
        bucket = str((obj or {}).get("bucket", "")).strip()
        if bucket in FIXED_RISK_CATEGORIES:
            _LLM_CLASSIFY_CACHE[cache_key] = bucket
            return bucket
    except Exception:
        pass

    _LLM_CLASSIFY_CACHE[cache_key] = "General & Other"
    return "General & Other"
```

> ⚠️ **限速**：每条 sub_risk 不命中关键词都会调一次 LLM。**必须**有进程内缓存（按 `(category, title)` 去重），上面的 `_LLM_CLASSIFY_CACHE` 起到这个作用。一份 10-K 通常 30-60 条 sub_risk，在新关键词表下大约 30%-50% 不命中（即 10-30 次 LLM 调用 / 份），可以接受。

### 4.4 改 `_extract_sub_risks`（`main.py:997-1012`）— 写入 `dashboard_category`

```python
def _extract_sub_risks(result: dict) -> List[dict]:
    out: List[dict] = []
    for cat_block in result.get("risks", []) if isinstance(result, dict) else []:
        original_category = str(cat_block.get("category", "Unknown") or "Unknown")
        for sr in cat_block.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = sr.get("labels", []) if isinstance(sr.get("labels"), list) else []
                # 优先读已写好的 dashboard_category（避免重复 LLM 调用）
                pre_dashboard = str(sr.get("dashboard_category", "") or "").strip()
                pre_original = str(sr.get("original_category", "") or "").strip()
            else:
                title = str(sr or "").strip()
                labels = []
                pre_dashboard = ""
                pre_original = ""
            if not title:
                continue

            if pre_dashboard in FIXED_RISK_CATEGORIES:
                mapped = pre_dashboard
            else:
                mapped, score = _normalize_risk_category(original_category, title, labels)
                if score < 3:
                    mapped = _classify_with_llm_fallback(original_category, title, labels)

            out.append({
                "category": mapped,                                  # 兼容旧字段（dashboard 里读这个）
                "dashboard_category": mapped,                        # 显式新字段
                "original_category": pre_original or original_category,
                "title": title,
                "labels": labels,
            })
    return out
```

### 4.5 写入时落盘 `dashboard_category` 与 `original_category`

`_manual_extract_result`（`main.py:1135-1186`）当前直接把 `extract_item1a_risks_bedrock` 的输出存进 `result["risks"]`。需要在 store 之前 **就地** 把 dashboard_category / original_category 写到每条 sub_risk：

```python
def _annotate_dashboard_category(risks_blocks: list) -> list:
    """Mutate-and-return: for each sub_risk dict in each block, attach
       'original_category' (= block's own category) + 'dashboard_category' (= mapped 9-bucket)."""
    for blk in risks_blocks if isinstance(risks_blocks, list) else []:
        if not isinstance(blk, dict):
            continue
        original_category = str(blk.get("category", "") or "")
        new_subs = []
        for sr in blk.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = sr.get("labels", []) if isinstance(sr.get("labels"), list) else []
                if not title:
                    continue
                mapped, score = _normalize_risk_category(original_category, title, labels)
                if score < 3:
                    mapped = _classify_with_llm_fallback(original_category, title, labels)
                sr_out = dict(sr)
                sr_out["original_category"] = original_category
                sr_out["dashboard_category"] = mapped
                new_subs.append(sr_out)
            else:
                title = str(sr or "").strip()
                if not title:
                    continue
                mapped, score = _normalize_risk_category(original_category, title, [])
                if score < 3:
                    mapped = _classify_with_llm_fallback(original_category, title, [])
                new_subs.append({
                    "title": title,
                    "labels": [],
                    "original_category": original_category,
                    "dashboard_category": mapped,
                })
        blk["sub_risks"] = new_subs
    return risks_blocks
```

在 `_manual_extract_result` 的最后（return 前）：
```python
if isinstance(risks, list):
    risks = _annotate_dashboard_category(risks)
return {"company_overview": overview, "risks": risks}, ""
```

> 这样 `result["risks"][...]["sub_risks"][...]` 在落盘时已经带 `original_category` + `dashboard_category`，下游（前端、ComparePage、`_extract_sub_risks`）直接读字段，**不再每次实时分类**。原始 LLM 给的 `block.category` 同时保留在 block 顶层，**永远可追溯**。

### 4.6 `_dashboard_summary`（`main.py:1429-1611`）取消重新分类

`main.py:1468` 当前调 `_extract_sub_risks(result)`，`_extract_sub_risks` 又会重新分类。改完后（§4.4），如果 sub_risk 已经带 `dashboard_category`，直接用 —— 行为是单跳，不再二跳。这个改动其实在 4.4 已经实现，记一下。

### 4.7 `top_categories` / `category_counts` / `category_yearly` 输出字段不变

`main.py:1497-1505` / `:1544-1556` 仍输出 9 个 FIXED_RISK_CATEGORIES。frontend Dashboard 不需要改。

### 4.8 类型修订

`_normalize_risk_category` 返回 `tuple[str, int]`，所有调用方需同步更新（`main.py:1010`、新加的 `_annotate_dashboard_category`）。**不要忘记 `agentcore_deploy/main.py` 顶部的 `Tuple` import**：

```python
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
```

---

## 5) 第三件事：修 Item 1 Overview 提取失败

### 5.1 改 `extract_item1_overview`（`core/extractor.py:739-749`）

```python
def extract_item1_overview(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """Extract Item 1 overview from HTML."""
    item1_text = locate_item1_overview(html_bytes)
    if item1_text:
        # ① 已经是 edgartools/sec-parser 切好的 Item 1 正文 —— 不要再用 _ITEM1_START
        # 正则去找标题。直接做 cut + 长度限制就好。
        return _shape_overview_from_section_text(item1_text, company_name, industry)
    # ② 兜底：raw 文本里找 Item 1 → Item 1A
    text = _full_text(_make_soup(html_bytes))
    return _extract_overview_from_text(text, company_name, industry)


def _shape_overview_from_section_text(
    section_text: str, company_name: str, industry: str,
) -> dict:
    """When the input is already a clean Item 1 section, just trim + cut at sub-headings."""
    body = str(section_text or "").strip()
    if not body:
        return {
            "company": company_name, "industry": industry,
            "year": 0, "filing_type": "",
            "background": "(Could not extract Item 1 overview.)",
        }

    # Cut at common sub-headings (Products / Services / Segments / Human Capital / etc.)
    cut_patterns = [
        re.compile(r"\n\s*Products\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Services\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Segments?\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Human Capital\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Employees\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Competition\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Seasonality\s*\n", re.IGNORECASE),
    ]
    for cp in cut_patterns:
        m = cp.search(body)
        if m and m.start() > 200:
            body = body[:m.start()]
            break

    background = _clean_text(body)

    if len(background) > 1500:
        cut = background[:1500]
        lp = cut.rfind(".")
        if lp > 200:
            background = cut[:lp + 1]

    return {
        "company": company_name, "industry": industry,
        "year": 0, "filing_type": "",
        "background": background or "(Could not extract Item 1 overview.)",
    }
```

### 5.2 改 `extract_item1_overview_bedrock`（`core/extractor.py:752-802`）

主要修两件事：

1. **fallback 用新的 `_shape_overview_from_section_text` 路径**（已经通过 §5.1 自动获得）
2. **LLM 调用失败时，不要返回失败串**——既然 fallback 已经能给一段干净文本（§5.1 之后），失败时直接 return `fallback`（fallback 现在是真背景，不再是 "(Could not extract...)"）

具体改动：现在的 L799-801 已经是这个语义，§5.1 修完后行为正确。

3. **加一行诊断日志**：在 `except Exception:` 处加 `print(f"[overview-bedrock] LLM failed for {company_name}: {type(_e).__name__}", file=sys.stderr)`（用 try…except as _e: ）。Railway 会收 stdout/stderr 日志，方便定位 Claude Opus 4.7 是不是真的有响应格式问题。

4. **空响应检测**：当前 `parsed = _extract_json_obj_or_array(raw)` 返回 None 时静默走 fallback，看不到原因。在 None 分支也加一行 stderr 日志：
```python
if not isinstance(parsed, dict):
    print(f"[overview-bedrock] Non-dict LLM response for {company_name}: {raw[:200]!r}", file=sys.stderr)
```

### 5.3 校验

跑 5 家：Apple 2024、JPMorgan 2024、Tesla 2024、Pfizer 2024、Lockheed Martin 2024。重新调 `/api/upload/auto-fetch` 或写脚本直接调 `extract_item1_overview_bedrock(html, ...)`，确保 `background` 长度 ≥ 200，且不是 `"(Could not extract...)"`。

---

## 6) 前端同步

### 6.1 改 `frontend/src/lib/records.js`

把 `RISK_CATEGORY_KEYWORDS` 与 `normalizeRiskCategory` **整体删除**。改成：

```js
export const FIXED_RISK_CATEGORIES = [
  'Strategy & Market',
  'Operations & Supply Chain',
  'Financial & Liquidity',
  'Legal & Regulatory',
  'Technology & Cybersecurity',
  'People & Governance',
  'ESG & Sustainability',
  'Capital Markets',
  'General & Other',
]

// 优先读后端注入的 dashboard_category；缺省回退到原始 category；都没有就 General & Other
function pickCategory(blockCategory, sub) {
  if (sub && typeof sub === 'object') {
    const dashboard = String(sub.dashboard_category || '').trim()
    if (FIXED_RISK_CATEGORIES.includes(dashboard)) return dashboard
  }
  const orig = String(blockCategory || '').trim()
  if (FIXED_RISK_CATEGORIES.includes(orig)) return orig
  return 'General & Other'
}

export function flattenRisks(result) {
  if (!result || !Array.isArray(result.risks)) return []
  const out = []
  result.risks.forEach((block) => {
    const blockCat = String(block?.category || 'Unknown').trim()
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      if (typeof sub === 'string') {
        const title = sub.trim()
        if (title) out.push({ category: pickCategory(blockCat, null), title, labels: [] })
        return
      }
      const title = String(sub?.title || '').trim()
      if (!title) return
      const labels = Array.isArray(sub?.labels) ? sub.labels.filter(Boolean) : []
      out.push({
        category: pickCategory(blockCat, sub),
        original_category: String(sub?.original_category || blockCat || '').trim(),
        title,
        labels,
      })
    })
  })
  return out
}

export function groupedRiskTitles(result) {
  if (!result || !Array.isArray(result.risks)) return []
  const grouped = new Map()
  result.risks.forEach((block) => {
    const blockCat = String(block?.category || 'Unknown').trim()
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      const title = String(typeof sub === 'string' ? sub : sub?.title || '').trim()
      if (!title) return
      const dashboardCat = pickCategory(blockCat, typeof sub === 'object' ? sub : null)
      if (!grouped.has(dashboardCat)) grouped.set(dashboardCat, [])
      grouped.get(dashboardCat).push(title)
    })
  })
  return Array.from(grouped.entries()).map(([category, titles]) => ({ category, titles }))
}

export function riskItemCount(result) { return flattenRisks(result).length }
export function riskCategoryCount(result) {
  if (!result || !Array.isArray(result.risks)) return 0
  return result.risks.length
}
export function companyOverview(result) {
  if (!result || typeof result !== 'object') return {}
  return result.company_overview && typeof result.company_overview === 'object' ? result.company_overview : {}
}

// 不再 export normalizeRiskCategory —— 没有调用方了（除了 ComparePage，下面改）
```

### 6.2 改 `frontend/src/pages/ComparePage.jsx`

当前（L6-9）：
```js
import { normalizeRiskCategory } from '../lib/records'
function normalizeCategory(value) {
  return normalizeRiskCategory(value)
}
```

`normalizeRiskCategory` 已删除，改成直接从 row 读：

```js
import { FIXED_RISK_CATEGORIES } from '../lib/records'

function normalizeCategory(row) {
  // row 来自 compare API，字段是 {category, title, ...}（core/comparator.py 输出）
  // 后端在落盘时已经把 dashboard_category 注到每条 sub_risk；compare 走的是 result.risks
  // 但 comparator.py 当前输出只有 {category, title}，需要确认它是否带 dashboard_category。
  const v = String(row?.dashboard_category || row?.category || '').trim()
  return FIXED_RISK_CATEGORIES.includes(v) ? v : 'General & Other'
}
```

> ⚠️ `core/comparator.py` 现在的 risks output（`compare_risks` 函数）只输出 `{category, title}`，**不含 dashboard_category**。需要在 `comparator.py` 的输出中传递 sub_risk 字典原文（包括 dashboard_category），或在 main.py 的 `/api/compare` 端点处对每条 row 应用 `_normalize_risk_category`。**Codex 在执行 §6.2 前先确认这点**——简单起见，建议在 `comparator.py:_flatten` 里把整个 sub_risk dict（如果是 dict）传出去而不是只传 title，让 dashboard_category 自然透传。

---

## 7) 历史数据回填（可选但推荐）

新代码上线后只有**新写入**的 result JSON 带 `dashboard_category`。旧 42 条 result（包括 Apple 2024 那条）还是没有该字段，新代码 §4.4 在 `_extract_sub_risks` 里有兜底：会现场算一遍 `_normalize_risk_category`（关键词新版表，不再吸到 Strategy & Market）+ LLM fallback。

但**第一次访问 dashboard 会触发 N×几十次 LLM**（缓存命中前），首屏会很慢。建议提前一次性回填：

### 7.1 `scripts/reclassify_existing_records.py`（新建）

伪代码：

```python
"""One-shot script: load every result.json from S3, run _annotate_dashboard_category,
and write back. Idempotent."""

import os, sys, json, boto3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentcore_deploy.main import (
    _list_s3_keys, _read_s3_bytes, _write_s3_bytes,
    _annotate_dashboard_category, RESULTS_PREFIX,
)

def main():
    keys = [k for k in _list_s3_keys(f"{RESULTS_PREFIX}/") if k.endswith(".json")]
    print(f"found {len(keys)} result files")
    for i, k in enumerate(keys, 1):
        raw = _read_s3_bytes(k)
        if not raw:
            continue
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            print(f"  [{i}/{len(keys)}] SKIP {k}: bad json")
            continue
        if not isinstance(doc.get("risks"), list):
            print(f"  [{i}/{len(keys)}] SKIP {k}: no risks")
            continue
        doc["risks"] = _annotate_dashboard_category(doc["risks"])
        _write_s3_bytes(k, json.dumps(doc, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
        print(f"  [{i}/{len(keys)}] OK   {k}")

if __name__ == "__main__":
    main()
```

跑法：在 Railway shell（或本地配好 AWS env）：`python scripts/reclassify_existing_records.py`。

### 7.2 不在本次任务执行的事

- 不重跑提取（Apple 2024 的"single Risk Factors bucket"就停在这里；用户看到的是把单桶按关键词 + LLM fallback 拆到 9 个桶里，**不是**重新提取）。如果用户要彻底修复，需要走 PLAN.md 已经规划的"用 Claude Opus 4.7 重跑"流程。
- 不动 agent_reports/ 下的历史 agent_report JSON。

---

## 8) 校验清单

- [ ] `extract_item1a_risks_bedrock` prompt 增加多类引导后，Apple 2024 重跑 risks 顶层 ≥ 3 块
- [ ] 旧 result 没重跑也能正常显示——`_extract_sub_risks` 对没有 dashboard_category 的旧条目会现场算
- [ ] Apple 2024 经过 §7.1 回填后，34 条不再 33 条都进 Strategy & Market（建议改完后 Strategy & Market 应 ≤ 30%）
- [ ] dashboard `/api/dashboard/summary?force=1` 的 `top_categories` 分布更均匀（用 entropy 评估或目测）
- [ ] Apple 2024 重新调 `/api/upload/auto-fetch` 或运行 §5 修复后，`company_overview.background` 长度 ≥ 200 且不是失败串
- [ ] 5 家代表性公司 Apple/JPMorgan/Tesla/Pfizer/Lockheed background 都有内容
- [ ] `frontend && npm run dev` 起前端，Library 页详情仍能正确按 9 桶显示（每条带 original_category 可在调试时查看）
- [ ] ComparePage 的分类筛选 dropdown 仍是 9 桶，过滤行为符合预期

---

## 9) 提交策略

| Commit | 内容 | 风险 |
|---|---|---|
| 1 | §3（提取 prompt + 单桶兜底重分类）+ §5（Item 1 overview 修复） | 中 — 影响新写入 result 的 risks 顶层结构与 background |
| 2 | §4（关键词表重写、`_normalize_risk_category` 返回 tuple、`_classify_with_llm_fallback`、`_annotate_dashboard_category` 写盘）+ §6（前端 records.js / ComparePage 切到 dashboard_category） | 中 — 改了多个调用约定；后端 / 前端必须同 PR 合并 |
| 3 | §7.1 回填脚本上线并跑一次（这一步 Codex 跑、Codex 不写进 cron） | 低 — 写回 S3，但 idempotent，可重跑 |

每个 commit 都要：
- 在 `PROJECT_CHANGELOG_CN.md` 追加一节
- 末尾写本次 commit id

---

## 10) 不做的事（明确划界）

- 不重新设计 9 大类桶；只改它们的关键词表 + 兜底 LLM
- 不改 `_chunk_item1a_by_headings`（提取分块逻辑跟分类无关）
- 不动 agent_reports/ 历史文件
- 不改 RPI 公式（属于 RPI_OPTIMIZATION_PLAN.md 范畴）
- 不动 PDF 提取路径（`extract_item1a_risks_from_text` 仍走启发式；HTML 主路径修好就够覆盖现有 100% 的数据）
- 不在前端做 LLM 调用——分类都在后端完成，前端只读字段

---

## 11) 待用户确认的开放问题

1. **§4 LLM fallback 的成本**：每条不命中关键词的 sub_risk 都要调一次 Claude Opus 4.7。新关键词表收紧后估计 30%-50% 不命中。一份 10-K 30-60 条 sub_risk → 10-30 次 LLM 调用。是否接受？或者要求 fallback 只用 Nova Lite/Haiku（更便宜）？
2. **§3 LLM 二次分类 pass**：当 LLM 第一次提取退化成单桶时再调一次 LLM 拆桶。Apple 这种 case 会多 1 次 LLM。是否接受？
3. **§7 回填**：是否同意直接对 42 条历史 record 跑一次 reclassify？跑完后旧数据展示会立即刷新。
4. **`comparator.py`**：是否同意修改输出，让 dashboard_category 透传到 `compare` 接口？

---

计划已写好，可以交给 Codex 执行。
