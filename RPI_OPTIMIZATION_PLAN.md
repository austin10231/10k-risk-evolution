# RPI_OPTIMIZATION_PLAN.md — RPI 评分逻辑优化方案

> 本计划由 Claude 生成，交给 Codex 执行。完成后按 `feedback_changelog` 规则更新 `PROJECT_CHANGELOG_CN.md`（含 commit id）。
>
> **强烈建议**：4 个 P 任务作为**一次 commit 一个**串行提交，便于回滚。如果一次性合并，PR 体积会偏大且 dashboard 行为同时跨多个回归点。

---

## 0) 背景与取舍

RPI 数据流（已确认）：

```
risks (list)                                         ← 提取出的风险因子
   │
   ▼  agentcore_deploy/agent.py:_prioritize_risks_impl  (LLM 调用)
enriched_risks (每条带 score / priority)
   │
   ▼  agentcore_deploy/agent.py:_build_priority_lists  (规则分桶)
priority_matrix.{high,medium,low}.count
   │
   ▼  agentcore_deploy/main.py:_risk_pressure_index  (规则加权)
record-level RPI ∈ [0, 100]
   │
   ▼  agentcore_deploy/main.py:_dashboard_summary    (聚合 max/avg)
priority_heatmap.{cells[].rpi, max_rpi, avg_rpi}
   │
   ▼  /api/dashboard/summary
frontend/src/pages/DashboardPage.jsx                  (色阶 + 数字)
```

LLM 与"权威性"问题：

- **score 三维加权 (0.4/0.35/0.25)** 与 **priority 阈值 (>=7 High, >=4 Medium)** 都写死在 prompt 里给 LLM。代码侧没有任何二次校验。
- 结论：**score 是 LLM 计算的（因此可能错），priority 也是 LLM 标的（因此可能与 score 自相矛盾）。RPI 是规则计算的（因此 RPI 公式本身没问题，但喂给它的 H/M/L 计数是 LLM 给的）。**

本计划 4 个 P 任务的总目标：让 LLM 那一层的不可靠性显式可见，不再用静默的"看似正常"的数字掩盖问题。

**新增的语义约定（贯穿整个计划）**：

| 含义 | 表示方式 |
|---|---|
| RPI 有效（已经评分） | float ∈ [0.0, 100.0] |
| RPI 无效（评分失败 / 无评分数据） | `None`（Python）/ `null`（JSON 序列化）/ `null` 或 `undefined`（JS） |
| 历史兼容：旧 record 没有 `agent_report` 也没有 `enriched_risks` | 视同评分失败，RPI = `None` |

> ⚠️ 这是行为变更：现在所有零数据 record 的 `cell.rpi` 是 `0.0`，前端显示 RPI=0；改完后会变成 `null`，前端显示"—"。这是用户明确要求的语义。

---

## P0 — LLM 打分加 Python 校验，不信任 LLM 给的 priority

### P0.1 涉及文件

- `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/agent.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/PROJECT_CHANGELOG_CN.md`（追加一行）

### P0.2 现状

`agentcore_deploy/agent.py:319-341`：拿到 LLM JSON 后，每条 enriched 都直接读 `score.get("priority", "Medium")` 和 `score.get("score", 5.0)` —— LLM 给什么就用什么。LLM 完全可以返回 `{score: 2.0, priority: "High"}`，下游 `_build_priority_lists`（L240-246）会按 priority 分到 High 桶。

### P0.3 改动

#### P0.3.1 新增一个常量与辅助函数（放在 `agent.py` 第 35 行 `MODEL_ID` 常量附近）

```python
PRIORITY_HIGH_THRESHOLD = 7.0
PRIORITY_MEDIUM_THRESHOLD = 4.0
PRIORITY_DIM_WEIGHTS = (0.4, 0.35, 0.25)  # financial_impact, likelihood, urgency

def _clamp_int_1_10(value, default: int = 5) -> int:
    try:
        n = int(round(float(value)))
    except Exception:
        n = default
    return max(1, min(10, n))

def _compute_score_from_dims(financial_impact, likelihood, urgency) -> float:
    fi = _clamp_int_1_10(financial_impact)
    lk = _clamp_int_1_10(likelihood)
    ur = _clamp_int_1_10(urgency)
    raw = (fi * PRIORITY_DIM_WEIGHTS[0]
           + lk * PRIORITY_DIM_WEIGHTS[1]
           + ur * PRIORITY_DIM_WEIGHTS[2])
    return round(float(raw), 2)

def _priority_from_score(score: float) -> str:
    s = float(score or 0.0)
    if s >= PRIORITY_HIGH_THRESHOLD:
        return "High"
    if s >= PRIORITY_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"
```

#### P0.3.2 改 `_prioritize_risks_impl` 的 enriched 构造（agent.py:327-341 当前块替换为）

```python
enriched_flat = []
for i, risk in enumerate(batch):
    raw_score = score_map.get(i)
    if isinstance(raw_score, dict):
        # P0: 不信任 LLM 给的 score / priority；用三维原值重算。
        fi = _clamp_int_1_10(raw_score.get("financial_impact"), default=5)
        lk = _clamp_int_1_10(raw_score.get("likelihood"),       default=5)
        ur = _clamp_int_1_10(raw_score.get("urgency"),          default=5)
        score = _compute_score_from_dims(fi, lk, ur)
        priority = _priority_from_score(score)
        reasoning = str(raw_score.get("reasoning", "") or "")
    else:
        # 整条记录 LLM 没返回 → 标为缺失，由 P1/P2 接管。
        fi, lk, ur = 5, 5, 5
        score = None        # ← 哨兵：null 表示未评分；P2 全面用
        priority = None
        reasoning = ""

    enriched_flat.append({
        "category": risk["category"],
        "title": risk["title"],
        "labels": risk["labels"],
        "tags": risk.get("tags", []),
        "priority": priority,            # 可能是 None（P2 处理）
        "score": score,                  # 可能是 None（P2 处理）
        "financial_impact": fi,
        "likelihood": lk,
        "urgency": ur,
        "reasoning": reasoning,
    })
```

> ⚠️ **关键设计点**：本步骤把"score 由代码算"和"priority 由代码标"两件事一起做了。LLM 现在只负责给 3 个维度（financial_impact/likelihood/urgency），其他都由 Python 决定。这样能让 P0 的目标（杜绝 score-priority 矛盾）和未来调阈值（只改 `PRIORITY_HIGH_THRESHOLD`）都很简单。

#### P0.3.3 改 `_build_priority_lists`（agent.py:228-251）

让它能跳过 `priority is None` 的条目（这些在 P2 里会被显式当成"未评分"）：

```python
def _build_priority_lists(enriched_risks: list):
    high, medium, low, unscored = [], [], [], []
    for cat_block in enriched_risks:
        for sr in cat_block.get("sub_risks", []):
            if not isinstance(sr, dict):
                continue
            entry = {
                "category": cat_block.get("category", ""),
                "title": sr.get("title", ""),
                "score": sr.get("score"),               # 可能 None
                "reasoning": sr.get("reasoning", ""),
            }
            priority = sr.get("priority")               # 可能 None
            if priority == "High":
                high.append(entry)
            elif priority == "Low":
                low.append(entry)
            elif priority == "Medium":
                medium.append(entry)
            else:
                unscored.append(entry)                  # 新桶

    def _sort_key(x):
        s = x.get("score")
        return (-1.0 if s is None else float(s))

    high.sort(key=_sort_key, reverse=True)
    medium.sort(key=_sort_key, reverse=True)
    low.sort(key=_sort_key, reverse=True)
    return high, medium, low, unscored                  # ← 多返回一个桶
```

#### P0.3.4 同步改 `_build_priority_lists` 的两个调用方（agent.py:362, agent.py:445）

```python
# _generate_agent_report_impl 顶部
high, medium, low, unscored = _build_priority_lists(enriched_risks)
# ... priority_matrix 同时多一个 unscored 字段
return {
    ...
    "priority_matrix": {
        "high":     {"count": len(high),     "top": high[:5]},
        "medium":   {"count": len(medium),   "top": medium[:3]},
        "low":      {"count": len(low),      "top": low[:3]},
        "unscored": {"count": len(unscored), "top": unscored[:3]},   # 新
    },
    ...
}
```

`_answer_user_query_impl` 那处只读 high_top，把 `_build_priority_lists` 的返回签名同步改一下就好。

### P0.4 注意事项

- **不要改 prompt** —— prompt 里仍然让 LLM 报 score 和 priority；只是代码侧不再读它的 score/priority，只读三个维度。这样 LLM 输出的 reasoning 仍然能保留（`reasoning` 字段是给前端展示用的）。
- 旧的 `score = round(float(score.get("score", 5.0)), 2)` 兜底逻辑被删除——`score` 字段现在要么是真分，要么是 `None`，**不要再用 5.0 假装存在**。这与 P2 一致。
- 此步骤完成后，**同一份 result JSON 可能同时存在 score 是 float 的旧条目（旧 record，未重跑）和 score 是 null 的新条目**。前端 / dashboard 必须容忍两者（详见 P2.3.5）。

---

## P1 — 超过 40 条风险因子时分批 LLM 打分

### P1.1 涉及文件

- `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/agent.py`

### P1.2 现状

`agent.py:277` 直接 `batch = flat_risks[:40]`，超过 40 条的全部丢弃；P0 改完后这些条目会变成 `priority=None`，被推到 `unscored` 桶；P3 之后会让这些 record 的 RPI 显式 = null（如果**所有**条目都丢失）或者按已评分的 H/M/L 计算 RPI（如果只是部分丢失）。

我们要做的是**真正给所有条目打分**，不是把缺失合理化。

### P1.3 改动

#### P1.3.1 新增 `_score_batch`（把当前 prompt 调用部分单独抽出来）

把 `agent.py:_prioritize_risks_impl` 第 277-325 行（`batch = flat_risks[:40]` 一直到 `score_map = {}`）抽成一个内部函数：

```python
_PRIORITY_BATCH_SIZE = 40

def _score_one_batch(
    batch: list,
    company: str,
    year: int,
    batch_index: int,
    batch_total: int,
) -> dict:
    """对一个 ≤40 条的 batch 调一次 Bedrock。返回 {local_id: score_dict}。
    LLM 调用失败时返回空 dict（让上层把整个 batch 标 unscored）。"""

    risks_json = json.dumps(
        [
            {
                "id": i,                     # 注意：i 是 batch 内 local id
                "title": r["title"][:200],
                "labels": r["labels"],
                "tags": r.get("tags", [])[:6],
            }
            for i, r in enumerate(batch)
        ],
        ensure_ascii=False,
    )

    prompt = f"""You are a senior financial risk analyst evaluating SEC 10-K risk factors for {company} ({year}).

This is batch {batch_index} of {batch_total} for the same filing. Score risks 1-10 in three dimensions:
1. financial_impact — potential dollar/earnings impact if the risk materializes
2. likelihood — probability of occurrence in the next 12 months
3. urgency — how soon action or attention is needed

Return ONLY a JSON array, one object per risk, in this format:
[
  {{
    "id": 0,
    "financial_impact": 8,
    "likelihood": 6,
    "urgency": 7,
    "reasoning": "One sentence explaining the priority."
  }}
]
Do NOT include score or priority — they will be computed deterministically downstream.
No preamble, no markdown."""

    try:
        raw = _invoke(prompt, max_tokens=2048)
        raw = _strip_json_fences(raw)
        scored = json.loads(raw)
        return {int(item["id"]): item for item in scored if isinstance(item, dict) and "id" in item}
    except Exception:
        return {}
```

#### P1.3.2 改 `_prioritize_risks_impl` 主流程为分批循环

```python
def _prioritize_risks_impl(risks: list, company: str, year: int) -> list:
    flat_risks = []
    for cat_block in risks:
        category = cat_block.get("category", "Unknown")
        for sub_risk in cat_block.get("sub_risks", []):
            ...  # 同当前逻辑
            flat_risks.append({...})

    if not flat_risks:
        return risks

    # P1: 全量评分。每批 ≤ _PRIORITY_BATCH_SIZE = 40。
    total = len(flat_risks)
    batches: List[List[dict]] = [
        flat_risks[i : i + _PRIORITY_BATCH_SIZE]
        for i in range(0, total, _PRIORITY_BATCH_SIZE)
    ]

    score_map_global: dict = {}                  # global_id → score_dict
    for b_idx, batch in enumerate(batches, start=1):
        local_scores = _score_one_batch(
            batch=batch,
            company=company,
            year=year,
            batch_index=b_idx,
            batch_total=len(batches),
        )
        offset = (b_idx - 1) * _PRIORITY_BATCH_SIZE
        for local_id, item in local_scores.items():
            score_map_global[offset + int(local_id)] = item

    enriched_flat = []
    for i, risk in enumerate(flat_risks):        # 注意：现在遍历的是 flat_risks 整体，不是 batch
        raw_score = score_map_global.get(i)
        # 复用 P0.3.2 的代码片段（把 LLM 三维拿出来重算 score、priority；缺失时 score/priority = None）
        ...

    category_map = {}
    for risk in enriched_flat:
        category = risk["category"]
        category_map.setdefault(category, []).append(risk)

    return [{"category": category, "sub_risks": sub_risks} for category, sub_risks in category_map.items()]
```

#### P1.3.3 失败行为约定

- 单个 batch 调用失败（`_score_one_batch` 返回空 dict）：本 batch 内的所有条目最终是 `score=None, priority=None`（落到 unscored 桶），但**其他 batch 不受影响**。
- 全部 batch 都失败：所有条目都 unscored，由 P2 把 record 的 RPI 标 null。

### P1.4 注意事项

- **限速**：调用次数从 1 次 / record 涨到 ⌈N/40⌉ 次 / record。10-K 通常 20-60 条，多数情况只增 0 或 1 次；极端长 filing（如金融 / 制药）可能 80-150 条 → 2-4 次调用。**不要并行调 batches**，Bedrock 还是串行更稳；如果用户后续 quota 提上来，可以再 parallelize。
- **日志**：在 `agent_steps` 里加一条 `f"⚙️ Tool 3a: scored {len(score_map_global)}/{total} risks across {len(batches)} batches"`，便于排查 partial fail。
- **token 预算**：Claude Opus 4.7 / Nova Pro 都能在 2048 max_tokens 里返回 40 条评分 JSON（每条约 50 tokens）。不需要调 max_tokens。
- **P0 的依赖**：本步骤的 enriched 构造代码与 P0.3.2 完全一致，建议把 P0、P1 合并成同一个 commit（它们改的是相邻代码块，分开做反而冲突）。

---

## P2 — Bedrock 调用失败时 RPI 标 null，前端显示"—"

### P2.1 涉及文件

- `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/agent.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py`
- `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/pages/DashboardPage.jsx`

### P2.2 现状

- `agent.py:319-325`：`_invoke` 抛异常 → `score_map = {}` → 所有条目 `priority="Medium", score=5.0`。priority_matrix 的 medium count = N，high/low = 0，**结果 RPI = 50.0 看起来一切正常**。
- `agent.py:575-583`：`run_agent` 顶层异常时调 `_fallback_report`（agent.py:204-225），它直接给 `priority_matrix = {high:0, medium:0, low:0}`，下游 `_risk_pressure_index(0,0,0) = 0.0`。也就是顶层失败时 RPI = 0，**和"全 Low"无法区分**。
- `main.py:1471`：`rpi = _risk_pressure_index(priority["high"], priority["medium"], priority["low"])` 永远返回 float（H+M+L=0 时返回 0.0）。
- `main.py:1494`：`if rpi > 0:` 才进 `rpi_values`，但这里既会过滤"全 Low（RPI=0，正常）"又会过滤"评分失败（RPI 应是 null）" —— P3 会拆开这两件事。

### P2.3 改动

#### P2.3.1 在 `agent.py` 增加"评分状态"字段

`_generate_agent_report_impl` 返回里加一个布尔：

```python
scoring_failed = (len(unscored) > 0 and (len(high) + len(medium) + len(low)) == 0)
return {
    ...
    "priority_matrix": {
        "high":     {"count": len(high),     "top": high[:5]},
        "medium":   {"count": len(medium),   "top": medium[:3]},
        "low":      {"count": len(low),      "top": low[:3]},
        "unscored": {"count": len(unscored), "top": unscored[:3]},
    },
    "scoring_status": "failed" if scoring_failed else (
        "partial" if len(unscored) > 0 else "ok"
    ),
    ...
}
```

`_fallback_report`（agent.py:204-225）也加：

```python
"scoring_status": "failed",
```

#### P2.3.2 在 `main.py:_risk_pressure_index` 改成可返回 None

```python
def _risk_pressure_index(
    high: int,
    medium: int,
    low: int,
    *,
    scoring_status: str = "ok",
) -> Optional[float]:
    """Returns None if scoring failed; 0.0~100.0 otherwise.
    Note: H+M+L=0 with scoring_status='ok' means an "all-Low / no risks" record
    (which legitimately has RPI=0); only scoring_status='failed' returns None."""
    if str(scoring_status) == "failed":
        return None
    total = int(high or 0) + int(medium or 0) + int(low or 0)
    if total <= 0:
        return 0.0
    weighted = (3 * int(high or 0)) + (2 * int(medium or 0)) + int(low or 0)
    return round(((weighted / total) - 1.0) / 2.0 * 100.0, 2)
```

> 三态语义：
> - `None`  → 评分失败 / 无 agent_report，前端显示 "—"
> - `0.0`   → 全 Low（合法的低风险），前端显示绿色 0
> - `>0.0`  → 正常分数

#### P2.3.3 在 `main.py:_extract_priority_counts_from_result`（L1364-1426）增加一个 `scoring_status` 字段

```python
out = {"high": 0, "medium": 0, "low": 0, "total": 0, "top_high": [], "scoring_status": "missing"}
...
agent_report = result.get("agent_report", {}) ...
status = str(agent_report.get("scoring_status", "")) or ""
# 兜底：旧 result JSON 没这个字段
if not status:
    if isinstance(agent_report, dict) and isinstance(agent_report.get("priority_matrix"), dict):
        status = "ok"               # 老 record，假设是好的
    else:
        status = "missing"          # 完全没有 agent_report
out["scoring_status"] = status
...
out["high"] = int(high)
out["medium"] = int(medium)
out["low"] = int(low)
out["total"] = int(high + medium + low)
return out
```

> "missing" 与 "failed" 在 RPI 计算阶段视为同一件事（都返回 None），但日志和指标里要分开统计便于排查老数据。

#### P2.3.4 改 `_dashboard_summary`（main.py:1461-1495）

```python
status_for_rpi = priority["scoring_status"]
if status_for_rpi in ("failed", "missing"):
    rpi = None
else:
    rpi = _risk_pressure_index(
        priority["high"], priority["medium"], priority["low"],
        scoring_status="ok",
    )
```

把 `if rpi > 0:` 那段（L1494-1495）改成（**注意 P3 会再改一次这个判断**）：

```python
if rpi is not None:
    scope["rpi_values"].append(float(rpi))
```

`heat_cells_map`（L1510-1527）里 `"rpi"` 字段：

```python
"rpi": rpi,   # 可能是 None，不再强转 float
```

聚合处（L1530-1541、L1584-1585）里也要容忍 None：

```python
max_rpi_by_company: Dict[str, float] = {}
for cell in heat_cells:
    comp = str(cell.get("company", "") or "")
    rv = cell.get("rpi")
    if rv is None:
        continue
    max_rpi_by_company[comp] = max(max_rpi_by_company.get(comp, 0.0), float(rv))
companies_sorted = sorted(
    list(scope["companies_set"]),
    key=lambda c: (-max_rpi_by_company.get(c, -1.0), c.lower()),
    # ↑ -1.0 让"无评分公司"排在所有有分公司之后，且彼此按字母序
)
```

`max_rpi` / `avg_rpi`（L1584-1585）维持现有逻辑（`scope["rpi_values"]` 已经只装 not-None 的）。

#### P2.3.5 前端 DashboardPage.jsx 显示逻辑

需要改 5 处（行号都已确认）：

**L18-27 `priorityHeatColor`** — 加灰色"未评分"分支：
```jsx
function priorityHeatColor(rpi, total) {
  const cnt = Number(total || 0)
  if (rpi === null || rpi === undefined) return '#e2e8f0'   // 未评分：浅灰
  if (!cnt) return '#f1f5f9'                                 // 无风险数据：更浅灰
  const score = Number(rpi)
  if (score >= 78) return '#ef4444'
  if (score >= 60) return '#f97316'
  if (score >= 42) return '#f59e0b'
  if (score >= 24) return '#84cc16'
  return '#22c55e'
}
```

**L444-468 热力图 cell 渲染**：
```jsx
const cell = heatCellMap.get(`${c}__${y}`)
const total = safeNumber(cell?.total)
const rpi = cell?.rpi              // 不要 safeNumber，保留 null/undefined
const bg = priorityHeatColor(rpi, total)
const isUnscored = cell && (rpi === null || rpi === undefined)
const display = (rpi === null || rpi === undefined) ? '—' : Number(rpi).toFixed(0)

return (
  <td key={`${c}-${y}`} className="py-2 px-1">
    {cell ? (
      <a
        href={`/library?record_id=${encodeURIComponent(cell.record_id || '')}`}
        ...
        title={isUnscored ? 'Risk scoring unavailable for this filing' : undefined}
        style={{ backgroundColor: bg }}
      >
        <span className="text-[9px] font-black tracking-[0.04em]">RPI</span>
        <span className="mt-[2px] text-[13px] leading-none font-black">{display}</span>
      </a>
    ) : (
      <div className="...">—</div>
    )}
  </td>
)
```

**L496 Average RPI 区域**：
```jsx
<p className="mt-1 text-sm font-semibold text-slate-700">
  Average RPI:{' '}
  {priorityHeatmap.avg_rpi === null || priorityHeatmap.avg_rpi === undefined
    ? '—'
    : safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}
</p>
```

**L634 hover popup RPI 字段**：
```jsx
<p className="mt-2 text-sm font-semibold text-slate-700">
  RPI: {hoverPopup.cell.rpi === null || hoverPopup.cell.rpi === undefined
    ? 'Not scored'
    : safeNumber(hoverPopup.cell.rpi).toFixed(1)}
</p>
```

**L368 帮助说明** — 顺手加一句：
```jsx
<p className="mt-1">RPI (0-100) is weighted by H/M/L counts. Higher RPI means higher pressure from high-priority risks. "—" indicates a filing whose risks couldn't be scored.</p>
```

### P2.4 注意事项

- **后端缓存失效**：`_DASHBOARD_SUMMARY_CACHE_TTL_SECONDS = 120`（main.py:97），改完后第一次访问 `/api/dashboard/summary?force=1` 让缓存失效。
- **JSON null 兼容**：Python `json.dumps(None) == "null"`。前端用 `=== null || === undefined` 判断。**不要写 `safeNumber(rpi)`**，那个会把 null 转成 0，把"未评分"和"全 Low" 又混回去了。
- **历史 record JSON 中没有 `scoring_status`**：P2.3.3 已用 `if not status` 兜底；如果 agent_report 存在且 priority_matrix 有数据 → 视同 "ok"（保持向后兼容，不会让所有老数据变 "—"）。
- **`/api/records/{record_id}`** 返回的 result JSON 也会带 `priority_matrix.unscored.count`，但前端 LibraryPage / Compare 等页面只是透传不消费这个字段，不需要改。

---

## P3 — 全 Low record 也要计入 avg_rpi

### P3.1 涉及文件

- `/Users/mr.tian/Desktop/10k-risk-evolution/agentcore_deploy/main.py`

### P3.2 现状

`main.py:1494`：
```python
if rpi > 0:
    scope["rpi_values"].append(float(rpi))
```

把"全 Low（RPI=0）"和"未评分"一起排除。P2 已经拆出 `rpi is None` 这一类，剩下 RPI=0 是合法的。

### P3.3 改动

把 P2.3.4 那一段（已经从 `if rpi > 0:` 改成 `if rpi is not None:`）保持不变即可——这正是 P3 想要的语义。`avg_rpi` 现在等于：

```
sum( all rpi where rpi is not None ) / count( all rpi where rpi is not None )
```

包含 RPI=0 的全 Low record。

> ✅ P3 的代码改动**已经在 P2.3.4 里做完**。这里只是显式确认两个 bug 是耦合的。

### P3.4 注意事项

- **avg_rpi 数字会下降**：原本被剔除的全 Low（=0）回到分母，平均值会被拉低。这是正确的，但需要在 PROJECT_CHANGELOG_CN.md 提醒"avg_rpi 数字会比之前略低，因为修复了将全 Low 文件排除在外的 bug"。
- **`max_rpi`** 不受影响（max 本来就允许 0）。
- **极端边界**：如果 scope 内全部 record 都是 "未评分"，`scope["rpi_values"]` 为空，`max_rpi` 与 `avg_rpi` 都是 0.0；前端按 P2 的判断显示 "—"。

---

## 4) 测试与验证清单

完成所有 P 后，跑一遍：

1. **单元自检**（手写一份脚本临时验证，不入仓）：
   - 构造 enriched_risks，模拟 LLM 返回 `{financial_impact:9, likelihood:9, urgency:9, score:1.0, priority:"Low"}`：调 `_prioritize_risks_impl` 后 priority 必须是 "High"（验证 P0）
   - 构造 60 条 risk 输入：调用次数 = 2，所有 60 条都有 score（验证 P1）
   - 让 `_invoke` 抛异常：返回 priority_matrix 的 unscored.count = N，scoring_status = "failed"（验证 P2 后端）
   - 构造 record `{H:0, M:0, L:5}`：RPI = 0，且进 rpi_values，avg_rpi 包含它（验证 P3）

2. **后端**：
   - `curl /api/dashboard/summary?force=1` → 检查 `priority_heatmap.cells[].rpi` 至少一个是 `null`（如果有未评分 record；没有的话造一个）
   - `curl /api/records/<rid>` → result.agent_report.priority_matrix 多了 unscored 与 scoring_status

3. **前端**：起 `cd frontend && npm run dev` 打开 Dashboard
   - 至少一个 cell 显示 "—"（灰色），hover 提示 "Risk scoring unavailable"
   - Average RPI 在没数据时显示 "—" 而不是 "0.0"
   - 全 Low record 的 cell 仍然显示绿色 0（不是灰）
   - 控制台无报错

4. **回归**：
   - LibraryPage 详情页：`priority_matrix.high.top[].score` 在新 record 是数字、在老 record 也是数字（P0 后旧 record 没重跑过仍然是数字）；前端不要崩
   - ComparePage：H/M/L delta 计算用的是 `priority_matrix.{high,medium,low}.count`，未引用 `unscored`，不需要改

5. **数据迁移**：
   - **不**强制重跑老 record。P0 改完后只有新 record 走新 priority 算法；老 record 的 score/priority 保留 LLM 给的值，照常显示。如果用户希望全量重跑（让所有数据一致），单独建议触发 `/api/dashboard/ensure-priority` 把老 record 都重新评分一次（这条 API 已存在，main.py:4350）。

---

## 5) 提交策略

| Commit | 内容 | 风险 |
|---|---|---|
| 1 | P0 + P1 合并提交（agent.py 改 prioritize 逻辑） | 中 — 影响所有新写入的 result JSON 的 priority/score 字段 |
| 2 | P2 后端（main.py + agent.py 增 scoring_status，rpi 可为 None） | 中 — 改了 dashboard payload schema，会让缓存中老数据有 cell.rpi=null 但 priority_totals 数字不变 |
| 3 | P2 前端（DashboardPage.jsx 4 处显示） | 低 — 纯展示 |
| 4 | （已在 commit 2 内完成）P3 实质上没有独立改动；在 changelog 单列一节即可 | — |

每个 commit 都要：
- 在 `PROJECT_CHANGELOG_CN.md` 追加一节，写明 P 编号、改了哪几个函数、行为变化
- 末尾写本次 commit id

---

## 6) 不做的事（明确划界）

- 不改 RPI 公式本身（3:2:1 加权 + 1-3 → 0-100 映射）—— 用户没要求改
- 不改前端色阶阈值（24/42/60/78）—— 跟 RPI 数值含义无关
- 不改 prompt 里的"分数权重 0.4/0.35/0.25"和"阈值 7/4"—— 用户没要求；只是把这两个数从 prompt 同步到 Python 常量，单一数据源
- 不引入新的可视化（"未评分"现在就是灰色 + "—"，不需要单独图例；如果用户后续要 legend，独立任务）
- 不动 `/api/agent/query` 与 `chat_agent.py` —— 它们用的是另一条路径，与 dashboard RPI 无关

---

计划已写好，可以交给 Codex 执行。
