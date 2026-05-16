# RiskLens Compare 功能优化计划（不改代码 · 方案稿）

> 编写时间：2026-05-15
> 编写者：Claude（Opus 4.7，1M 上下文）
> 适用范围：YoY（同一公司不同年度）与 Cross-Company（不同公司同年）两种比较模式
> 目标：将 Compare 的“准/全/可解释/可纠错”四个维度都拉到生产可用线。

---

## 1. 现状梳理

### 1.1 调用链
| 层 | 文件 | 关键函数/位置 | 作用 |
| --- | --- | --- | --- |
| 入口 | `agentcore_deploy/main.py:5088` | `path == "/api/compare"` | HTTP 路由 |
| 编排 | `agentcore_deploy/main.py:4218` | `_compare_payload` | 加载两份 result.json → 打 dashboard 类目 → 调 comparator |
| 算法 | `core/comparator.py:47` | `compare_risks` | 真正做匹配的地方 |
| 数据 | `agentcore_deploy/main.py:1376` | `_extract_sub_risks` | 把 result.risks 摊平为 sub_risk 数组（含 dashboard_category / labels） |
| 前端 | `frontend/src/pages/ComparePage.jsx` | `ComparePage` | UI；只展示 new / removed 两栏 |

### 1.2 当前算法（关键 33 行）
```python
# core/comparator.py
def compare_risks(prior_result, latest_result):
    prior = _flatten_sub_risks(prior_result)
    latest = _flatten_sub_risks(latest_result)
    mp, ml = set(), set()
    for li, lr in enumerate(latest):                      # ① 顺序遍历 latest
        up = [(pi, pr) for pi, pr in enumerate(prior) if pi not in mp]
        best_r, best_pi = 0.0, -1
        for pi, pr in up:
            r = difflib.SequenceMatcher(None,             # ② 字符级 ratio
                                         lr["norm"], pr["norm"]).ratio()
            if r > best_r: best_r, best_pi = r, pi
        if best_r >= 0.75:                                # ③ 硬阈值 0.75
            ml.add(li); mp.add(best_pi)                    # ④ 贪心配对
    return {"new_risks": [...], "removed_risks": [...]}    # ⑤ 只两桶输出
```

### 1.3 输入数据真实形态（重要前提）
- `sub_risks` 在数据层就是 **标题字符串**（详见 `core/extractor.py:_normalize_ai_risk_blocks`，把 dict/str 一律压成 title）。没有正文段落、没有严重度、没有 LLM 置信度。
- 仅有的附加结构是 `labels: List[str]`（关键词）和 `dashboard_category`（9 大固定类）。
- `_extract_sub_risks` 在每次比较时还可能触发 `_classify_with_llm_fallback`（`agentcore_deploy/main.py:1398`），慢且对结果没贡献——因为后续匹配根本没用到 `dashboard_category`。

---

## 2. 为什么“一点也不准”——问题归因

按影响从大到小排：

| # | 问题 | 触发场景 | 影响 |
| --- | --- | --- | --- |
| P0 | **纯字符级相似度** `difflib.SequenceMatcher` | "Cybersecurity incidents disrupt operations" vs "Information security breaches could harm our business" | 语义相同但 ratio 常 <0.5，直接判作"new + removed"两条 |
| P0 | **跨类目误匹配** 未按 `dashboard_category` 分桶 | "Failure to attract talent" 误匹到 "Failure to comply with regulations"（前缀相同） | 错配 + 错失真正同义项 |
| P0 | **贪心顺序匹配** 不是全局最优分配 | latest[0] 抢走原本更该匹配 latest[3] 的 prior | 配对错乱级联 |
| P1 | **阈值 0.75 硬编码**，且无 UI 可调 | 同义改写的真同伴 ratio≈0.6，被切成两条；模板化样板句 ratio>0.9 被错并 | 二元失真：不是漏配就是错并 |
| P1 | **没有"修改/重写"概念**，只输出 new/removed | 同一风险换了表述方式 → 同时计入两侧 | 用户看到的"新增/消失"数严重虚高 |
| P1 | **`labels` 完全未参与匹配** | sub_risk 标题相似但 labels 不重叠 → 几乎可以肯定是误配 | 浪费了现成的弱监督信号 |
| P2 | **归一化太弱** 仅去标点+小写 | "We may be unable to ..." vs "The Company may fail to ..." | 模板前缀拉低 ratio |
| P2 | **未处理同义词/缩写** cyber/IT、vendor/supplier、FX/currency | 标题表面无重合但意思一样 | 漏配 |
| P2 | **Cross-Company 用同一算法** | 不同公司措辞风格差异 >> 同公司 YoY | YoY 已经不准，Cross-Company 更差 |
| P3 | **前端无配对可见性** | 用户无法核对/标注错误 | 既无法 debug 也没法迭代 |
| P3 | **结果不可解释** 没分数、没原因 | 用户问"为什么这条算新？" → 无答案 | 信任崩塌（"一点也不准"的主观感受） |
| P3 | **`comparator._flatten_sub_risks` 与 `main._extract_sub_risks` 重复实现** | 维护漂移 | 两边类目/labels 行为可能不一致 |
| P3 | **每次 compare 触发 LLM fallback 分类** | dashboard_category 缺失时 | 慢，且对当前算法无收益 |

> 一句话结论：现在的 Compare 等同于"两段文本去重"，根本没在做"风险演化对比"。准不起来是结构性问题，不是调参能救的。

---

## 3. 目标态（What "good" looks like）

### 3.1 输出契约升级
当前：
```json
{ "new_risks": [...], "removed_risks": [...],
  "summary": { "new_count": n, "removed_count": m } }
```
建议升级为：
```json
{
  "latest_record_id": "...",
  "prior_record_id": "...",
  "mode": "yoy | cross",
  "scoring": { "threshold": 0.62, "method": "hybrid_v2" },
  "pairs": {
    "retained":  [ { "latest": {...}, "prior": {...}, "score": 0.91, "title_changed": false } ],
    "modified":  [ { "latest": {...}, "prior": {...}, "score": 0.74,
                     "title_changed": true,  "diff": { "added_tokens": [...], "removed_tokens": [...] } } ],
    "added":     [ {...} ],
    "removed":   [ {...} ]
  },
  "category_matrix": {
    "Technology & Cybersecurity": { "retained": 3, "modified": 1, "added": 2, "removed": 0 },
    ...
  },
  "summary": {
    "retained": x, "modified": y, "added": z, "removed": w,
    "churn_rate": (y+z+w) / (x+y+z+w),
    "avg_match_score": 0.83
  },
  "warnings": [ "category 'Capital Markets' has 0 items on prior side; matches in this category are unreliable" ]
}
```

### 3.2 用户可感知改善
- **少误判**：同义改写归到 `modified`，不再两侧各算一条。
- **可解释**：每条 retained/modified 都带分数和对端原文。
- **可调**：UI 暴露一个阈值滑块（建议 0.55–0.85，默认 0.62）。
- **可纠错**：错配可手动标记 → 计入会话级 override（先不入库，二期再做反馈学习）。
- **跨公司可读**：Cross-Company 主视图改为"按 9 大类的覆盖矩阵 + 各桶独有项列表"，而不是平铺 diff。

---

## 4. 分阶段实施方案

### Phase 1 · 算法骨架重写（无外部依赖，1–1.5 天）

目标：**不引入 embedding** 的前提下，让准确率从"勉强能看"提到"基本可用"。

1. **类目分桶**：先用 `dashboard_category` 把两侧分组，只在同桶内匹配；类目不存在或为 `General & Other` 的项放进一个独立桶（避免被"杂项"污染）。
2. **强化归一化**（新增 `_canonicalize(title)`）：
   - 剥离样板前缀：`we may`, `we are`, `the company`, `our `, `failure to`, `risks related to`, `if we`, `because we`, `inability to`, `our ability to` 等。
   - 词形归并：轻量 stemmer（Porter 即可，已在 `core` 范围常见依赖之内）。
   - 数字/年份脱敏：`2024` → `<YEAR>`，金额 `$1.2 billion` → `<MONEY>`。
   - 同义词替换字典（初版 30 条手工词表，可放 `core/compare_synonyms.py`）：
     - cyber* / IT system / information security → `infosec`
     - vendor / supplier / third party → `supplier`
     - FX / currency / foreign exchange → `currency`
     - litigation / lawsuit / legal proceedings → `litigation`
     - …
3. **混合相似度**（替代 SequenceMatcher）：
   ```
   sim = 0.5 * jaccard(token_set_canonical)
       + 0.3 * char_ngram_cosine(n=3)
       + 0.2 * label_overlap_jaccard
   ```
   - Jaccard 抗模板/词序差异；char-ngram 抗拼写/词形小差异；label_overlap 利用已有 `labels` 字段。
   - 全部纯 Python，零依赖（或仅 `numpy`，已在项目里）。
4. **全局最优分配**（替代贪心）：
   - 同桶内用 `scipy.optimize.linear_sum_assignment`（匈牙利算法）；若不想引入 scipy，写个 30 行 Jonker–Volgenant 也行，桶内规模通常 <40 × 40。
5. **三态分类**：
   - `score ≥ T_high (0.85)` → `retained`
   - `T_low (0.62) ≤ score < T_high` → `modified`
   - `score < T_low` → 不配对，归入 added / removed
6. **输出契约**：按第 3.1 节切换；同时保留 `new_risks` / `removed_risks` 兼容旧前端（一期 BFF 内做映射，前端可平滑升级）。
7. **去掉每次 compare 的 LLM 兜底分类**：`_extract_sub_risks` 在 compare 路径上只读已存的 `dashboard_category`，缺失就归桶 `General & Other`。该 LLM 调用应该前移到入库 pipeline。

**预期效果**：在内部抽样 5 对 YoY 上做 A/B（手工标注 retained/modified/added/removed），目标 F1 从估算的 ~0.4 提到 ≥0.75。

### Phase 2 · 语义嵌入（2–3 天，依赖 Bedrock）

1. **嵌入服务**：复用项目已在用的 AWS Bedrock（agentcore），选 `amazon.titan-embed-text-v2` 或 Cohere `embed-english-v3`，向量维 1024。
2. **缓存策略**：以 `(record_id, sha1(title))` 为键，向量缓存到 S3 `embeddings/` 前缀；compare 时按需补算缺失项；同一 record 入库时即可异步预热。
3. **混合公式 v2**：
   ```
   sim = 0.6 * cosine(emb_a, emb_b)
       + 0.25 * jaccard(token_set_canonical)
       + 0.15 * label_overlap_jaccard
   ```
4. **类目失效兜底**：若两侧 dashboard_category 都不可靠（例如新公司还没跑分类），跳过类目分桶，直接全局匹配；warnings 字段提示用户。
5. **阈值重新校准**：因 embedding 引入，T_low 期望可降到 0.55；用同一标注集回归。

### Phase 3 · Cross-Company 专属视图（1 天）

Cross-Company 模式逻辑分叉：

1. **主视图改为类目矩阵**：
   - 表格：行=9 大类，列= [A 独有 / 共有 / B 独有 / A 总数 / B 总数 / 共有率]
   - 共有/独有按 Phase 1+2 的 retained/modified 计入"共有"，added/removed 归各自独有。
2. **侧栏 drill-down**：点某一行展开该类下的三列详情（A 独有 · 共有对 · B 独有）。
3. **阈值不同**：Cross-Company 默认 T_low=0.55、T_high=0.80（行业表达差异更大）。
4. **公平性提示**：若 A、B sub_risk 数量差 >2×，UI 上提示"对比基数差异较大"。

### Phase 4 · 可解释与可纠错 UX（1–2 天）

`ComparePage.jsx` 的改造点（一期最小集）：

- **三栏改四栏 / 或一栏 + Tab**：Retained · Modified · Added · Removed（Retained 默认折叠，因为量大）。
- **Modified 行展开**：左右对照原文标题 + 高亮 token diff（已有 added_tokens/removed_tokens）。
- **每行右侧角标**显示相似度（如 `0.74`）；hover 显示三项分量。
- **错配纠正按钮**：每个 retained/modified 行加一个"标为错配"按钮，会话级保存到 `localStorage` + 当前 data 状态，并立刻把该对拆回 added/removed。
- **阈值滑块**：放在结果区顶部；切换时本地重排（后端返回所有候选分数 ≥0.45 的对，前端按阈值切桶）。

### Phase 5 · 离线评测与回归（贯穿）

- **标注集**：先挑 5 对 YoY + 3 对 Cross 做人工 ground truth（每个 sub_risk 标 retained/modified/added/removed/wrong-pair），存 `tests/compare_eval/labels.jsonl`。
- **评测脚本**：`scripts/eval_compare.py` 计算 macro-F1、配对准确率、类目混淆矩阵；每次算法改动跑一次，结果落 `scripts/eval_compare.report.json`。
- **回归门槛**：F1 不得低于上一次记录的 95%；否则 CI 失败。

---

## 5. 工程影响 / 风险 / 兼容性

| 项 | 评估 |
| --- | --- |
| 后端 API 兼容 | 一期保留 `new_risks` / `removed_risks` 字段，新增 `pairs`；前端按需消费。二期可删旧字段。 |
| 性能 | Phase 1 纯 Python，单次 compare <200ms（桶内规模通常 <40）。Phase 2 走缓存后单次 <300ms；冷启动可能到 2–4s。 |
| 成本 | Bedrock embedding ~1k tokens/record，按 Titan v2 价计可忽略（<$0.001 / record）。 |
| 数据迁移 | 不需要。所有改动作用于 compare 路径，已有 result.json 不动。 |
| 风险点 | 同义词词表覆盖不足 → 反复迭代；阈值过低导致误并 → 用评测集兜底。 |

---

## 6. 验收标准

1. 内部 5 对 YoY 标注集上：retained/modified/added/removed 四分类 macro-F1 **≥ 0.75**（Phase 1 目标）/ **≥ 0.85**（Phase 2 目标）。
2. Cross-Company 主视图能正确呈现 9 类的覆盖矩阵，且任意一格点击可下钻。
3. 阈值滑块从 0.55 调到 0.85 全过程页面不卡顿（前端本地切桶）。
4. 任意一条 retained/modified 都能在 UI 上看到 (a) 对端原文 (b) 相似度分数 (c) token diff。
5. 用户在 UI 点"标为错配"，对应行立刻拆回 added/removed，且 summary 计数同步刷新。
6. `scripts/eval_compare.py` 在 CI 中跑通并出报告。

---

## 7. 落地优先级建议

| 优先级 | 任务 | 工期估算 | 价值 |
| --- | --- | --- | --- |
| P0 | Phase 1（类目分桶 + 混合相似度 + 匈牙利 + 三态） | 1.5d | 解决 70% 不准问题 |
| P0 | Phase 5 标注集 + 评测脚本 | 0.5d | 防止后续退步 |
| P1 | Phase 4 UX（Modified 视图 + 分数 + 错配按钮） | 1.5d | 让"准"被用户感知到 |
| P1 | Phase 2 Embedding | 2d | 再上一个台阶 |
| P2 | Phase 3 Cross-Company 矩阵 | 1d | 跨公司模式真正可用 |

---

## 8. 待用户拍板的问题

1. **阈值默认值**：是希望偏召回（更多 modified，少漏配，但偶有误并），还是偏准确（默认更保守）？这会影响 T_low 起点。
2. **同义词词表来源**：是否允许我用 LLM 离线生成一份金融/SEC 风险用语同义表作为初版（再人工 review），还是只手工建？
3. **Cross-Company 视图**：是否同意把主视图改成"类目覆盖矩阵"（区别于 YoY 的 diff 列表）？
4. **错配纠正**：一期是否只做会话级（localStorage），二期再考虑落库与反哺阈值？
5. **Embedding 服务**：用 Bedrock Titan v2 还是 Cohere v3？（项目目前对哪家更熟、配额更宽？）

---

## 9. 不在本计划内（明确划出去）

- 不重做 `_extract_sub_risks` 的分类逻辑（这是入库 pipeline 的问题，不属于 Compare）。
- 不调整 9 大固定类目（`FIXED_RISK_CATEGORIES`）。
- 不做"风险演化叙事生成"（即用 LLM 写一段"今年比去年多了哪些风险、为什么"的总结）；这是 Phase 6 的可选增强。
- 不动 `agentcore_deploy/agent_tools.py` 里 Chat Agent 调用 compare 的链路（升级输出契约时一起带兼容字段即可）。
