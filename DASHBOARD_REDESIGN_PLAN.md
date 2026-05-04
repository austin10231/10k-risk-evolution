# DASHBOARD_REDESIGN_PLAN.md — Dashboard 优化方案（Risk Pulse Tab）

## 0) 目标

在不修改后端、不改数据契约的前提下，把 Dashboard `Risk Pulse` 标签的浏览体验从"翻 8 页才能看完 76 家公司、年份列大半是 —"重构成"顶部双栏 header（左：标题 + how-to-read；右：Priority Mix + Scope Snapshot 对齐）→ 中部单行 filter → 底部全宽 heatmap 表格"的三层结构，配合空年份列自动隐藏 + 紧凑视图。涉及的具体痛点：

| 痛点 | 期望 |
|---|---|
| 2020 列大量公司是 "—" | 当前 paged 视野里没有 2020 数据时，自动隐藏 2020 列；用户筛选/翻页让 2020 公司进入视野时再恢复 |
| 76 家公司分页 10/页要翻 8 页 | 加 compact view 把行高从 44px → 28px，一屏可见公司数 ≈ 翻倍 |
| 右侧 RECENT FILINGS 窄、稀疏、占用横向空间 | 整块删掉 |
| Priority Mix 留在右栏但布局松散；Scope Snapshot 单独占一格 | Priority Mix **保留在右栏**（用户偏好），与左侧 Priority Heatmap 标题 + "How to read quickly" 区块**顶部对齐**；Scope Snapshot 内容（Avg RPI / With Priority）并进 Priority Mix 块尾部；不再做横向 summary cards row |
| 搜索 / 筛选 / 排序 / 翻页 4-5 个控件堆成 5 行（current `rl-heatmap-filter-grid`），占大量纵向空间 | 压成**一行**横排（flex-wrap 兜底），与上方双栏分离开 |
| 表格本身宽度被右栏挤压 | 双栏只覆盖**顶部** header 区域；filter row 和 **heatmap 表格**移到双栏下方独立分层、整张表格**全宽** |
| RPI 排序方向不直观 | 后端**已经按 max RPI DESC 排好**，前端只透传——但当前 UI 没有任何提示让用户感知；加一个 sort toggle 显式说明，并允许切回 A-Z |

> 把方案完全写完后扔给 Codex 执行；这个文档里**不动一行代码**。

---

## 1) 涉及文件清单

需要改：

| 文件 | 改动量 | 说明 |
|---|---|---|
| `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/pages/DashboardPage.jsx` | 中等 | Risk Pulse Tab 拆三层（顶部双栏 header / 单行 filter / 全宽表格）；加 3 个 state（`compactView` / `showAllYears` / `sortMode`）+ 2 个 useMemo（`effectiveYears` / `sortedCompanies`）；删 Recent Filings；Priority Mix 内合并 Scope Snapshot 内容 |
| `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/index.css` | 小 | 新增 `.rl-heatmap-filter-row`、`.rl-heatmap-priority-side`、`.rl-heatmap-cell-compact` 等 class；保留并裁剪现有 `.rl-heatmap-filter-grid`（filter 不再走 grid 布局） |

**不需要改**：

- `agentcore_deploy/main.py` — 后端已经给了所需全部数据：
  - `priority_heatmap.companies` 已经是 `key=lambda c: (-max_rpi_by_company.get(c, -1.0), c.lower())`，即 max RPI DESC 排好，未评分公司落底（main.py L2023-2027）
  - `priority_heatmap.years` 是 scope 下所有出现过的 year 去重排序，**问题不在后端**——是前端把"全部年份"硬塞进 thead 而没有按当前 viewport 做交集
  - `priority_totals` / `priority_heatmap.avg_rpi` / `metrics.records_with_priority` 全都已经在 payload 里，右栏 Priority Mix + Scope Snapshot 直接读这些字段拼即可
- 其他 page、`AppShell`、`api.js`、后端任何模块

---

## 2) 现状代码事实（执行时按这个对位）

DashboardPage.jsx 关键行号（执行时如发现行号已漂移，按 anchor 字符串定位即可）：

| 行号 | 当前内容 | 计划处置 |
|---|---|---|
| `L67-73` | state 集合：`industry / selectedCategory / heatSearch / heatPageSize / heatPage / hoverPopup / stockCache` | 追加 `compactView` (bool, 默认 false) / `showAllYears` (bool, 默认 false) / `sortMode` (`'rpi'`/`'name'`，默认 `'rpi'`) |
| `L184` | `const priorityHeatmap = scopeData?.priority_heatmap || {...}` | 不变 |
| `L191-195` | `const recent = useMemo(...)` | **删除**——recent_records 不再展示 |
| `L222-228` | `companiesOrdered = priorityHeatmap.companies` (后端已 RPI DESC) | 改为 `sortedCompanies`：根据 `sortMode` 切换，`'rpi'` 直接用 `priorityHeatmap.companies`，`'name'` 走 `[...companies].sort((a,b)=>a.localeCompare(b))` |
| `L230-234` | `yearsOrdered = priorityHeatmap.years` | 不变；新增派生 `effectiveYears` |
| `L286-291` | `metricTiles` 4 张大卡片 | **保留不变**（顶部 4 张大 metric tiles 仍是 page 第一排，不再插入新的 summary cards row） |
| `L361-530` | `<section className="grid gap-4 xl:grid-cols-[1.75fr_1fr]">` 顶层双栏 | **去掉 section 级双栏**；改成单 `<section>` 包一个 `panelClass` 的 `<div>`，里面再分**三层**（顶部双栏 header / 单行 filter / 全宽表格） |
| `L362-485` | 左栏 heatmap 全块（标题 + how-to-read + filter grid + table）混在一起 | 拆成 3 段：①header 双栏左半（标题 + how-to-read），②filter row（独立一层、单行），③table（独立一层、全宽） |
| `L381-423` | `rl-heatmap-filter-grid`（5 列 grid，约占 4-5 行高度） | 替换为 `rl-heatmap-filter-row`（flex 一行 + flex-wrap 兜底），并新增 Sort 选择器 + Compact toggle |
| `L487-529` | 右侧 panel：Priority Mix + Scope Snapshot + Recent Filings | 改造成 **header 双栏右半**：保留 Priority Mix 三色卡（H/M/L），把 Scope Snapshot 的 Avg RPI / With Priority 并进同一个 panel 尾部；删 Recent Filings；整体 max-width 320px、与左半 header 顶对齐 |
| `L432-484` | `<table>` 渲染 thead/tbody | thead 用 `effectiveYears` 替代 `yearsOrdered`；cell `<a>`/`<div>` className 在 compact 模式下走 `.rl-heatmap-cell-compact` |
| `L399-407` | "Rows / Page" 选项 `[8, 10, 14, 20]` | 加大上限：`[10, 20, 40, 80]`；compact view 下默认推到 40 |

---

## 3) 具体改动步骤

### 3.1 重排 Risk Pulse 布局：三层结构（顶部双栏 / 单行 filter / 全宽表格）

**总体目标的最终 layout**：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ panelClass 容器（一个 div）                                              │
│ ┌──────────────────────────────────────┬─────────────────────────────┐  │
│ │ Priority Heatmap title + subtitle    │                             │  │
│ │ How to read quickly box              │   Priority Mix              │  │
│ │  (left half of top stripe)           │   ─ High / Medium / Low     │  │
│ │                                      │   Scope Snapshot            │  │
│ │                                      │   ─ Avg RPI                 │  │
│ │                                      │   ─ With Priority X / Y     │  │
│ │                                      │  (right half, ≈320px wide)  │  │
│ └──────────────────────────────────────┴─────────────────────────────┘  │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Filter row (single line, full width):                                │ │
│ │  Search | Industry | Sort | Rows | Page | Compact toggle | Refresh   │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ "Showing X-Y / N"                                                        │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Heatmap table (FULL width, no right-side panel anymore)              │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

**JSX 重写示意**（替换原 L361-530 的整块 `<section>`）：

```jsx
{/* 删除 recent useMemo（L191-195）的全部代码块 */}

<section>
  <div className={`${panelClass} p-4`}>
    {/* TOP STRIPE — header double-column */}
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      {/* LEFT: heatmap headline + how-to-read */}
      <div>
        <div className="section-headline">
          <div className="section-rail" />
          <div>
            <p className="section-title-strong">Priority Heatmap</p>
            <p className="section-sub">Cards display RPI only. Hover a card for company/year risk detail and stock info.</p>
          </div>
        </div>

        <div className="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/65 p-3 text-xs text-slate-600">
          <p className="font-semibold text-slate-700">How to read quickly:</p>
          <p className="mt-1">RPI (0-100) is weighted by H/M/L counts. Higher RPI means higher pressure from high-priority risks. "—" indicates a filing whose risks couldn't be scored.</p>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
            <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#22c55e' }} />Lower pressure</span>
            <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} />Mid pressure</span>
            <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#ef4444' }} />High pressure</span>
          </div>
        </div>
      </div>

      {/* RIGHT: Priority Mix + Scope Snapshot (combined) */}
      <aside className="rl-heatmap-priority-side">
        <p className="section-title">Priority Mix</p>
        <div className="mt-2 grid grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded-xl border border-red-200/90 bg-red-50/70 p-2.5">
            <p className="font-extrabold text-red-600">High</p>
            <p className="mt-0.5 text-base font-extrabold text-red-700">{loading ? '…' : safeNumber(priorityTotals.high)}</p>
          </div>
          <div className="rounded-xl border border-amber-200/90 bg-amber-50/70 p-2.5">
            <p className="font-extrabold text-amber-600">Medium</p>
            <p className="mt-0.5 text-base font-extrabold text-amber-700">{loading ? '…' : safeNumber(priorityTotals.medium)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200/90 bg-emerald-50/70 p-2.5">
            <p className="font-extrabold text-emerald-600">Low</p>
            <p className="mt-0.5 text-base font-extrabold text-emerald-700">{loading ? '…' : safeNumber(priorityTotals.low)}</p>
          </div>
        </div>

        <div className="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Scope Snapshot</p>
          <p className="mt-1 text-sm font-semibold text-slate-700">
            Average RPI:{' '}
            {priorityHeatmap.avg_rpi === null || priorityHeatmap.avg_rpi === undefined
              ? '—'
              : safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Rows with priority data: {safeNumber(metrics.records_with_priority)} / {safeNumber(metrics.records)}
          </p>
        </div>
      </aside>
    </div>

    {/* MIDDLE STRIPE — filter row, single line, full width */}
    <div className="rl-heatmap-filter-row mt-4">
      <label className="rl-heatmap-filter-cell">
        <span className="section-title">Company Search</span>
        <input className="input mt-1" placeholder="Filter companies..." value={heatSearch} onChange={(e) => setHeatSearch(e.target.value)} />
      </label>

      <label className="rl-heatmap-filter-cell">
        <span className="section-title">Industry Group</span>
        <select className="input mt-1" value={industry} onChange={(e) => setIndustry(e.target.value)}>
          {industryOptions.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </label>

      <label className="rl-heatmap-filter-cell">
        <span className="section-title">Sort</span>
        <select className="input mt-1" value={sortMode} onChange={(e) => setSortMode(e.target.value)}>
          <option value="rpi">RPI (high → low)</option>
          <option value="name">Company A → Z</option>
        </select>
      </label>

      <label className="rl-heatmap-filter-cell rl-heatmap-filter-cell--narrow">
        <span className="section-title">Rows / Page</span>
        <select className="input mt-1" value={heatPageSize} onChange={(e) => setHeatPageSize(Number(e.target.value) || 10)}>
          {[10, 20, 40, 80].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>

      <label className="rl-heatmap-filter-cell rl-heatmap-filter-cell--narrow">
        <span className="section-title">Page</span>
        <select className="input mt-1" value={heatPage} onChange={(e) => setHeatPage(Number(e.target.value) || 1)}>
          {Array.from({ length: totalHeatPages }, (_, i) => i + 1).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>

      <label className="rl-heatmap-toggle-cell">
        <input type="checkbox" checked={compactView} onChange={(e) => setCompactView(e.target.checked)} />
        <span>Compact</span>
      </label>

      <label className="rl-heatmap-toggle-cell">
        <input type="checkbox" checked={showAllYears} onChange={(e) => setShowAllYears(e.target.checked)} />
        <span>Show empty year columns</span>
      </label>

      <button className="btn-secondary rl-heatmap-filter-cell--action" onClick={() => load({ force: true })} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>

    <p className="mt-2 text-xs font-semibold text-slate-600">Showing {heatRangeLabel} / {filteredCompanies.length}</p>

    {/* BOTTOM STRIPE — full-width table */}
    {pagedCompanies.length === 0 || effectiveYears.length === 0 ? (
      <div className="mt-3 rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
        No priority heatmap data available for the selected scope.
      </div>
    ) : (
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              <th className="w-48 py-2 pr-3 text-left text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Company</th>
              {effectiveYears.map((y) => (
                <th key={y} className="py-2 px-1 text-center text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{y}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedCompanies.map((c) => (
              <tr key={c} className="border-t border-slate-100/80">
                <td className={`${compactView ? 'py-1 pr-2' : 'py-2 pr-3'} font-semibold text-slate-800`}>{c}</td>
                {effectiveYears.map((y) => {
                  /* … cell render — see §3.4 for compact-view className branching */
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
</section>
```

**关键点**：
- 只有**顶部 stripe** 是双栏（`xl:grid-cols-[1fr_320px]`）；filter row 和 table 都是单层全宽。
- 右栏宽度固定 `320px`（vs. 现在的 fr 比例），保证不会随表格宽度变化跳动。
- xl 断点（≥1280px）以下双栏自动塌成单列（grid 默认行为）；窄屏下 Priority Mix 会落到 how-to-read 下方，filter row 自动 wrap，table 仍可横向滚动。

**删除项**：
- `recent` useMemo（L191-195）整段移除
- 旧 filter grid（L381-423）的 5 个 `<div>` cell + Refresh 按钮整体替换为新 filter row
- 旧的右栏 `<div className={`${panelClass} p-4`}>`（L487-529）整个删掉，里面的 Priority Mix + Scope Snapshot 内容已并入新 header 双栏右半（**注意**：不再用 `panelClass`，因为它已经在外层 panel 内部，避免双层 panel 视觉重；改用 `rl-heatmap-priority-side` 的轻量边框/背景），Recent Filings 整段直接删

### 3.2 单行 filter row：CSS 收尾

CSS 在 `frontend/src/index.css` 末尾追加（**不要替换现有 `.rl-heatmap-filter-grid` 规则；保留它供后续如有别处使用**）：

```css
/* Heatmap filter — single horizontal row (DASHBOARD_REDESIGN_PLAN §3.1) */
.rl-heatmap-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.6rem 0.75rem;
}
.rl-heatmap-filter-cell {
  display: flex;
  flex-direction: column;
  flex: 1 1 160px;          /* grow but cap default min so search 不被挤太短 */
  min-width: 0;
}
.rl-heatmap-filter-cell--narrow { flex: 0 1 110px; }
.rl-heatmap-filter-cell--action {
  flex: 0 0 auto;
  align-self: stretch;
  margin-top: 1.4rem;        /* 对齐 input 下边缘（避开 label 顶部空间） */
}
.rl-heatmap-toggle-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex: 0 0 auto;
  align-self: stretch;
  padding: 0 0.4rem;
  margin-top: 1.4rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #475569;
  cursor: pointer;
  user-select: none;
}
.rl-heatmap-toggle-cell input { accent-color: #2563eb; }

/* Right-side Priority Mix panel (combined with Scope Snapshot)  §3.1 */
.rl-heatmap-priority-side {
  align-self: start;            /* 顶部对齐左侧 section-headline */
  width: 100%;
  display: flex;
  flex-direction: column;
}
```

**注意**：`align-items: end;` 让 filter cells 的 `<input>`/`<select>` 底部对齐；toggle 和 button 通过 `margin-top: 1.4rem` 手工补到同一基线。如果实际渲染发现 1.4rem 偏一点，调到 1.3 / 1.5rem 都行，验收时按视觉调整。

### 3.3 年份列动态（核心）

**问题根因**：thead 的列由 `yearsOrdered = priorityHeatmap.years` 驱动；后端给的是该 scope 下**所有出现过**的 year，2020 只要有 1 家有数据，整列就出现，其他 75 家全 "—"。

**修复**：派生 `effectiveYears`，只保留"当前 paged viewport 至少有 1 家公司有数据"的年份。

在 `pagedCompanies` 之后追加：

```jsx
const effectiveYears = useMemo(() => {
  const all = yearsOrdered
  if (showAllYears) return all
  if (!pagedCompanies.length || !heatCellMap.size) return all
  return all.filter((y) => pagedCompanies.some((c) => heatCellMap.has(`${c}__${y}`)))
}, [yearsOrdered, pagedCompanies, heatCellMap, showAllYears])
```

**两处替换**：
- thead 的 `yearsOrdered.map((y) => <th>...</th>)` → `effectiveYears.map(...)`
- tbody 的 `yearsOrdered.map((y) => { const cell = heatCellMap.get(...) })` → `effectiveYears.map(...)`

**空状态保护**：`pagedCompanies.length === 0 || effectiveYears.length === 0` 时显示 "No priority heatmap data ..."（沿用 L427-430 的现有空状态）。

**Toggle UI**：已在 §3.1 的新 `rl-heatmap-filter-row` 中加入 "Show empty year columns" 复选框，本节只负责 `effectiveYears` 派生 + thead/tbody 渲染替换。

**注意**：`effectiveYears` 依赖 `pagedCompanies`，翻页/换 page size/换 industry 都会让列数变化——这是有意设计，但要在 thead 上方放一个小说明文字（hover tooltip 或紧贴表头的灰色脚注）："Year columns hidden when no company on this page has data for that year. Toggle 'Show empty year columns' to lock all years visible."

### 3.4 Compact view

加 state：`const [compactView, setCompactView] = useState(false)`。Compact 复选框 UI 已在 §3.1 的新 filter row 中包含，本节只负责 cell className 切换与行高调整。

修改 cell 渲染（L460-475），抽两套 className：

```jsx
const cellLinkClass = compactView
  ? 'rl-heatmap-cell-compact'
  : 'mx-auto flex h-11 w-[78px] flex-col items-center justify-center rounded-lg border border-white/70 text-[10px] font-bold text-slate-800 transition-transform hover:scale-[1.03]'
const cellEmptyClass = compactView
  ? 'rl-heatmap-cell-compact rl-heatmap-cell-empty'
  : 'mx-auto flex h-11 w-[78px] items-center justify-center rounded-lg border border-slate-200/70 bg-slate-100/70 text-[10px] font-semibold text-slate-400'

// 在 cell 渲染：
{cell ? (
  <a className={cellLinkClass} ...>
    {!compactView ? <span className="text-[9px] font-black tracking-[0.04em]">RPI</span> : null}
    <span className={compactView ? 'text-[12px] font-black leading-none' : 'mt-[2px] text-[13px] leading-none font-black'}>
      {display}
    </span>
  </a>
) : (
  <div className={cellEmptyClass}>—</div>
)}
```

CSS 追加：

```css
/* Compact heatmap cell (DASHBOARD_REDESIGN_PLAN entry 4) */
.rl-heatmap-cell-compact {
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 1.65rem;          /* ~26px vs full 44px */
  width: 3.5rem;            /* ~56px vs full 78px */
  border-radius: 0.4rem;
  border: 1px solid rgba(255, 255, 255, 0.7);
  font-weight: 900;
  font-size: 0.72rem;       /* ~11.5px */
  color: #1e293b;
  transition: transform 120ms ease;
}
.rl-heatmap-cell-compact:hover {
  transform: scale(1.04);
}
.rl-heatmap-cell-compact.rl-heatmap-cell-empty {
  background: rgba(241, 245, 249, 0.7);
  border-color: rgba(203, 213, 225, 0.7);
  color: #94a3b8;
}
```

行高同步压缩：tbody `<tr>` 的 `<td className="py-2 pr-3">` 改成条件 className：

```jsx
const rowPaddingClass = compactView ? 'py-1 pr-2' : 'py-2 pr-3'
const cellTdClass = compactView ? 'py-1 px-1' : 'py-2 px-1'
```

替换原有硬编码 `py-2 pr-3` 与 `py-2 px-1` 处。

**Page size 联动**：当用户开启 compact 时，自动把 `heatPageSize` 设为 `40`（如果当前是默认的 `10`），让一屏看更多：

```jsx
useEffect(() => {
  if (compactView && heatPageSize <= 14) setHeatPageSize(40)
}, [compactView])
```

把 page size options 从 `[8, 10, 14, 20]` 扩到 `[10, 20, 40, 80]`，老的小值留两个用于非 compact 模式。

### 3.5 排序（解释 + UI）

**事实先确认**：后端 `companies_sorted` 已经按 `(-max_rpi_by_company.get(c, -1.0), c.lower())` 排了，即 max RPI DESC，未评分落底（main.py L2023-2027）。前端 L222-228 只是透传。所以**用户期望"按 RPI 从高到低"已经满足**——但 UI 没显式标注，用户可能感知不到。

**改动**：把"sort"做成可见的 toggle + 在 heatmap 上方显示提示文字。

新 state：`const [sortMode, setSortMode] = useState('rpi')`

替换 `companiesOrdered`（L222-228）为：

```jsx
const sortedCompanies = useMemo(() => {
  const base = Array.isArray(priorityHeatmap.companies) ? priorityHeatmap.companies : []
  const fallback = base.length ? base : Array.from(
    new Set((priorityHeatmap.cells || []).map((row) => String(row.company || '').trim()).filter(Boolean)),
  )
  if (sortMode === 'name') {
    return [...fallback].sort((a, b) => a.localeCompare(b))
  }
  // 'rpi' — backend already orders by max RPI DESC, just keep as-is.
  return fallback
}, [priorityHeatmap.companies, priorityHeatmap.cells, sortMode])
```

`filteredCompanies` 与 `pagedCompanies` 引用 `companiesOrdered` 的地方全改成 `sortedCompanies`。

UI：Sort 选择器已在 §3.1 的新 filter row 中包含；本节只负责 `sortedCompanies` 派生 + page-reset 联动。

切 `sortMode` 时 page reset 到 1（已有 useEffect 监听 `industry / heatSearch / heatPageSize`，把 `sortMode` 加进同一份 deps）：

```jsx
useEffect(() => { setHeatPage(1) }, [heatSearch, heatPageSize, industry, sortMode])
```

heatmap 副标题加一行提示："Sorted by RPI (high → low). Companies without scored filings appear at the bottom."（仅当 `sortMode === 'rpi'` 时显示）

---

## 4) 用户偏好持久化（可选，建议做）

`compactView` / `showAllYears` / `sortMode` 三个偏好用 `localStorage` 记住：

```jsx
const PREF_KEY = 'rl.dashboard.pulsePrefs.v1'
const [compactView, setCompactView] = useState(() => {
  try { return JSON.parse(localStorage.getItem(PREF_KEY) || '{}').compactView ?? false }
  catch { return false }
})
// 同样初始化 showAllYears, sortMode

useEffect(() => {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify({ compactView, showAllYears, sortMode }))
  } catch (e) { /* quota / SSR / private mode — 安全忽略 */ }
}, [compactView, showAllYears, sortMode])
```

只读一次（initializer），写在每次变化——避免 SSR 报错和 quota 异常导致 UI 崩。

---

## 5) 验证清单（前端 build + 视觉)

执行完成后逐项验证：

- [ ] `npm --prefix frontend run build` 通过；无 ESLint warning
- [ ] Risk Pulse Tab 三层布局正确：
  - 顶部 stripe：左半是 "Priority Heatmap" 标题 + "How to read quickly" 灰色框；右半是 "Priority Mix"（H/M/L 三色卡）+ "Scope Snapshot"（Avg RPI / With Priority），高度与左半 visually 对齐
  - 中部 stripe：filter row 一行排完 7 个控件（Search / Industry / Sort / Rows / Page / Compact toggle / Show empty year columns toggle / Refresh），窄屏自动 wrap
  - 底部 stripe：heatmap 表格**全宽**（不再被右侧 panel 挤压）
  - RECENT FILINGS 块**已删除**
- [ ] 默认视图（compact off / showAllYears off / sortMode='rpi'）：
  - 当前 page 上没人有 2020 数据时，2020 列不显示
  - 翻到包含 2020 数据公司的页时，2020 列自动出现
  - "Show empty year columns" 勾上后立即显示所有年份
- [ ] Compact view 勾上后：
  - 行高从 ~52px 降到 ~28px
  - cell 文字只有 RPI 数字（无 "RPI" label）
  - page size 自动跳到 40（如果之前是 10）
  - 一屏（1080p）可见公司数 ≥ 25
- [ ] Sort 切换：
  - `RPI (high → low)`（默认）：第 1 页是 RPI 最高的公司
  - `Company A → Z`：第 1 页公司名首字母靠前
  - 切换 sort 后 page 自动 reset 到 1
- [ ] localStorage：刷新页面后三个偏好（compact / showAllYears / sortMode）都被记住
- [ ] hover tooltip 正常显示（行高变化不应破坏 `tooltipPosition` 计算）
- [ ] industry filter / company search / page size 旧功能不回归
- [ ] 暗色主题（如有）下 Priority Mix 右栏 / compact cells 文字颜色对比度仍达标——需手动看一眼

---

## 6) 注意事项 / 可能踩的坑

1. **`effectiveYears` 与 `pagedCompanies` 互相影响**：列数随翻页变动是有意设计；但要避免列宽抖动让用户视觉不适。table 用了 `min-w-full`，列数减少时表会自动收缩，OK。如果发现抖动严重，备选方案：把列宽固定（每列固定 60px），列数变少时整张表左对齐而非 stretch。
1.5. **顶部 stripe 双栏 vs filter / table 单层**：注意三层都在**同一个 `panelClass` 容器内**（共享外层圆角 / 模糊背景），中间不要再嵌套 panel 容器，避免双层卡片视觉重；右栏 `rl-heatmap-priority-side` 用轻量背景，与外层 panel 区分开但不抢戏。
2. **`max_rpi_by_company` 在后端已经计算好**——前端不需要再算一遍。如果用户要"按当前 industry scope 重新算 max RPI"，后端的 scope-aware 逻辑（main.py L2012-2027）已经按 scope 算了，前端透传即可。
3. **未评分公司的位置**：后端把它们放到 `(-1.0, name)` 排序键，所以默认 RPI 排序时这些公司在最底部——切到 `name` 模式时就按字母混在中间。这个行为符合直觉，无需特殊处理。
4. **`heatPageSize` 改默认值**：当前默认 10。改成 20 是个轻微的行为变化——会让首屏拉取的数据量看起来更多（其实数据本来就在 payload 里，是渲染量增加）。如果担心 perf 退化，把默认保持 10、只在 compact 时强行升到 40。
5. **删除 `recent` useMemo 后**：注意 search 文件确认没有别处引用 `recent`。grep 过 `DashboardPage.jsx` 内只有 L191-195 + L518-525 两处使用，都在本计划删除范围内。
6. **不要触碰 Category Intelligence Tab**：本次只动 Risk Pulse 的 `activeTab === 'pulse'` 分支（L348-532）。Category Tab（L534-637）保持原样。
7. **CSS 命名空间**：新加的 class 全部用 `rl-heatmap-*` 前缀，与现有 CSS 风格一致；不要复用 `metric-card` 等通用 class，避免误改其他 page。
8. **后端不动**：本次重排不需要任何 backend 改动。如果后续想做"按 scope 显示 min year"的服务端预过滤优化，可以另起一份 plan，本次不做。
9. **`.rl-heatmap-filter-grid` 现有 CSS（index.css L2592-2603）**：filter row 改用 flex，**不再走 grid**，所以新加的 `.rl-heatmap-filter-row` 是独立 class；旧的 `.rl-heatmap-filter-grid` 规则**保留**（grep 全仓库确认无别处使用后再决定是否清理，本次不删）。
10. **PROJECT_CHANGELOG_CN.md 规则**：本计划落地后必须按现有 changelog 风格在文档末尾新增一条 entry（37 号），包括 commit hash 回填——execute 阶段处理，本计划不做。

---

## 7) 不做的事（明确划界）

- 不动 Category Intelligence Tab
- 不动后端 / `/api/dashboard/summary` 数据契约
- 不引入新的图表库 / UI 库
- 不做服务端 sort（前端透传 + 切换够用）
- 不重构 hover tooltip / stockCache 逻辑
- 不调整暗色主题色板（除非验证发现对比度不达标）
- 不做行内 inline-edit（保持 read-only dashboard）

---

计划已写好，可以交给 Codex 执行。
