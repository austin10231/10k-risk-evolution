# DASHBOARD_REDESIGN_PLAN.md — Dashboard 优化方案（Risk Pulse Tab）

## 0) 目标

在不修改后端、不改数据契约的前提下，把 Dashboard `Risk Pulse` 标签的浏览体验从"翻 8 页才能看完 76 家公司、年份列大半是 —"重构成"全宽热力图、空年份自动隐藏、紧凑视图一屏看完一半公司、Priority Mix / Scope Snapshot 上移做横向 summary cards"。涉及的具体痛点：

| 痛点 | 期望 |
|---|---|
| 2020 列大量公司是 "—" | 当前 paged 视野里没有 2020 数据时，自动隐藏 2020 列；用户筛选/翻页让 2020 公司进入视野时再恢复 |
| 76 家公司分页 10/页要翻 8 页 | 加 compact view 把行高从 44px → 28px，一屏可见公司数 ≈ 翻倍 |
| 右侧 RECENT FILINGS 窄、稀疏、占用横向空间 | 整块删掉，热力图扩展到全宽 |
| Priority Mix / Scope Snapshot 在右栏，需眼睛左右扫 | 上移到热力图上方，做一行横向 summary cards |
| RPI 排序方向不直观 | 后端**已经按 max RPI DESC 排好**，前端只透传——但当前 UI 没有任何提示让用户感知；加一个 sort toggle 显式说明，并允许切回 A-Z |

> 把方案完全写完后扔给 Codex 执行；这个文档里**不动一行代码**。

---

## 1) 涉及文件清单

需要改：

| 文件 | 改动量 | 说明 |
|---|---|---|
| `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/pages/DashboardPage.jsx` | 中等 | Risk Pulse Tab 整块重排；加 3 个 state（`compactView` / `showAllYears` / `sortMode`）+ 3 个 useMemo（`effectiveYears` / `sortedCompanies` / `summaryCards`）；删 Recent Filings；上移 Priority Mix / Scope Snapshot |
| `/Users/mr.tian/Desktop/10k-risk-evolution/frontend/src/index.css` | 小 | 新增 `.rl-heatmap-summary-row`、`.rl-heatmap-cell-compact`、`.rl-heatmap-row-compact` 三个 class，沿用现有暗色主题分支 |

**不需要改**：

- `agentcore_deploy/main.py` — 后端已经给了所需全部数据：
  - `priority_heatmap.companies` 已经是 `key=lambda c: (-max_rpi_by_company.get(c, -1.0), c.lower())`，即 max RPI DESC 排好，未评分公司落底（main.py L2023-2027）
  - `priority_heatmap.years` 是 scope 下所有出现过的 year 去重排序，**问题不在后端**——是前端把"全部年份"硬塞进 thead 而没有按当前 viewport 做交集
  - `priority_totals` / `priority_heatmap.avg_rpi` / `metrics.records_with_priority` 全都已经在 payload 里，summary cards 直接拼即可
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
| `L286-291` | `metricTiles` 4 张大卡片 | 拆成 4 个标准 metric + 5 个新的 summary cards（H/M/L/AvgRPI/WithPriority），共一排紧凑 |
| `L361-485` | `<section className="grid gap-4 xl:grid-cols-[1.75fr_1fr]">` 双栏 | 改单栏：去掉 grid 包装，热力图 `<div>` 直接占据 `<section>` |
| `L487-529` | 右侧 panel：Priority Mix + Scope Snapshot + Recent Filings | Priority Mix + Scope Snapshot 内容上移到 summary cards row；Recent Filings 整块删 |
| `L432-484` | `<table>` 渲染 thead/tbody | thead 用 `effectiveYears` 替代 `yearsOrdered`；cell `<a>`/`<div>` className 在 compact 模式下走 `.rl-heatmap-cell-compact` |
| `L399-407` | "Rows / Page" 选项 `[8, 10, 14, 20]` | 加大上限：`[10, 20, 40, 80]`；compact view 下默认推到 40 |
| `L361 section` 之前 | metricTiles row | 在 metricTiles row 之后插入 **summary cards row**（5 张紧凑卡） |

---

## 3) 具体改动步骤

### 3.1 删 Recent Filings + 全宽热力图

**改 `<section>` 容器（L361）**

```jsx
// 旧
<section className="grid gap-4 xl:grid-cols-[1.75fr_1fr]">
  <div className={`${panelClass} p-4`}>
    {/* heatmap */}
  </div>
  <div className={`${panelClass} p-4`}>
    {/* Priority Mix + Scope Snapshot + Recent Filings */}
  </div>
</section>

// 新
<section>
  <div className={`${panelClass} p-4`}>
    {/* heatmap full width */}
  </div>
</section>
```

**删除 `recent` useMemo（L191-195）**：整段移除，没有别的地方引用。

**删除右侧 panel 的 Priority Mix / Scope Snapshot / Recent Filings（L487-529）**：连同包裹的 `<div>` 一起删，因为整个二列 grid 已经塌成单列。

### 3.2 Priority Mix / Scope Snapshot → 横向 summary cards

在 `metricTiles` 那个 `<section>`（L350-359）之后插入一个新的 summary row：

```jsx
{/* Existing — 4 large metric tiles */}
<section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
  {metricTiles.map(...)}
</section>

{/* New — 5 compact summary cards */}
<section className="grid gap-2 sm:grid-cols-3 xl:grid-cols-5">
  <div className="rl-heatmap-summary-card border-red-200/90 bg-red-50/70">
    <p className="rl-heatmap-summary-label text-red-600">High</p>
    <p className="rl-heatmap-summary-value text-red-700">{loading ? '…' : safeNumber(priorityTotals.high)}</p>
  </div>
  <div className="rl-heatmap-summary-card border-amber-200/90 bg-amber-50/70">
    <p className="rl-heatmap-summary-label text-amber-600">Medium</p>
    <p className="rl-heatmap-summary-value text-amber-700">{loading ? '…' : safeNumber(priorityTotals.medium)}</p>
  </div>
  <div className="rl-heatmap-summary-card border-emerald-200/90 bg-emerald-50/70">
    <p className="rl-heatmap-summary-label text-emerald-600">Low</p>
    <p className="rl-heatmap-summary-value text-emerald-700">{loading ? '…' : safeNumber(priorityTotals.low)}</p>
  </div>
  <div className="rl-heatmap-summary-card border-slate-200/85 bg-slate-50/85">
    <p className="rl-heatmap-summary-label text-slate-500">Avg RPI</p>
    <p className="rl-heatmap-summary-value text-slate-700">
      {priorityHeatmap.avg_rpi === null || priorityHeatmap.avg_rpi === undefined
        ? '—'
        : safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}
    </p>
  </div>
  <div className="rl-heatmap-summary-card border-slate-200/85 bg-slate-50/85">
    <p className="rl-heatmap-summary-label text-slate-500">With Priority</p>
    <p className="rl-heatmap-summary-value text-slate-700">
      {safeNumber(metrics.records_with_priority)}/{safeNumber(metrics.records)}
    </p>
  </div>
</section>
```

CSS 在 `frontend/src/index.css` 末尾追加（**不要替换现有规则**）：

```css
/* Dashboard heatmap summary cards (DASHBOARD_REDESIGN_PLAN entry 1) */
.rl-heatmap-summary-card {
  border: 1px solid;
  border-radius: 0.75rem;       /* matches existing rounded-xl */
  padding: 0.55rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rl-heatmap-summary-label {
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.rl-heatmap-summary-value {
  font-size: 1.15rem;
  font-weight: 900;
  line-height: 1.1;
}
```

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

**Toggle UI**：在 heatmap filter grid（L381）加一个 checkbox "Show empty year columns"：

```jsx
<label className="rl-heatmap-toggle">
  <input type="checkbox" checked={showAllYears} onChange={(e) => setShowAllYears(e.target.checked)} />
  <span>Show empty year columns</span>
</label>
```

**注意**：`effectiveYears` 依赖 `pagedCompanies`，翻页/换 page size/换 industry 都会让列数变化——这是有意设计，但要在表头加一个小说明文字（hover tooltip 或紧贴 thead 的灰色脚注）："Year columns hidden when no company on this page has data for that year. Toggle 'Show empty year columns' to lock all years visible."

### 3.4 Compact view

加 state：`const [compactView, setCompactView] = useState(false)`

在 filter grid 加一个 toggle button（与 Refresh 按钮同排）：

```jsx
<button
  className={`btn-secondary ${compactView ? 'is-active' : ''}`}
  onClick={() => setCompactView((v) => !v)}
>
  {compactView ? '✓ Compact' : 'Compact view'}
</button>
```

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

UI（filter grid 内部加一个 sort 选择器）：

```jsx
<div>
  <label className="section-title">Sort</label>
  <select className="input mt-2" value={sortMode} onChange={(e) => setSortMode(e.target.value)}>
    <option value="rpi">RPI (high → low)</option>
    <option value="name">Company A → Z</option>
  </select>
</div>
```

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
- [ ] Risk Pulse Tab：删了 RECENT FILINGS 块、PRIORITY MIX / SCOPE SNAPSHOT 上移到顶部 summary row、热力图占满整宽（>= xl 屏 1280px 时也是 full width）
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
- [ ] 暗色主题（如有）下 summary cards / compact cells 文字颜色对比度仍达标——需手动看一眼

---

## 6) 注意事项 / 可能踩的坑

1. **`effectiveYears` 与 `pagedCompanies` 互相影响**：列数随翻页变动是有意设计；但要避免列宽抖动让用户视觉不适。table 用了 `min-w-full`，列数减少时表会自动收缩，OK。如果发现抖动严重，备选方案：把列宽固定（每列固定 60px），列数变少时整张表左对齐而非 stretch。
2. **`max_rpi_by_company` 在后端已经计算好**——前端不需要再算一遍。如果用户要"按当前 industry scope 重新算 max RPI"，后端的 scope-aware 逻辑（main.py L2012-2027）已经按 scope 算了，前端透传即可。
3. **未评分公司的位置**：后端把它们放到 `(-1.0, name)` 排序键，所以默认 RPI 排序时这些公司在最底部——切到 `name` 模式时就按字母混在中间。这个行为符合直觉，无需特殊处理。
4. **`heatPageSize` 改默认值**：当前默认 10。改成 20 是个轻微的行为变化——会让首屏拉取的数据量看起来更多（其实数据本来就在 payload 里，是渲染量增加）。如果担心 perf 退化，把默认保持 10、只在 compact 时强行升到 40。
5. **删除 `recent` useMemo 后**：注意 search 文件确认没有别处引用 `recent`。grep 过 `DashboardPage.jsx` 内只有 L191-195 + L518-525 两处使用，都在本计划删除范围内。
6. **不要触碰 Category Intelligence Tab**：本次只动 Risk Pulse 的 `activeTab === 'pulse'` 分支（L348-532）。Category Tab（L534-637）保持原样。
7. **CSS 命名空间**：新加的 class 全部用 `rl-heatmap-*` 前缀，与现有 CSS 风格一致；不要复用 `metric-card` 等通用 class，避免误改其他 page。
8. **后端不动**：本次重排不需要任何 backend 改动。如果后续想做"按 scope 显示 min year"的服务端预过滤优化，可以另起一份 plan，本次不做。
9. **rl-heatmap-filter-grid 现有 CSS（index.css L2592-2603）**已经支持新增的 children 自动 wrap，不需要改 grid 容器规则。
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
