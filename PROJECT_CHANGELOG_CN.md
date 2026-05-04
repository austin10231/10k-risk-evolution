# 项目简明更新记录（中文）

这个文档用于记录：
- 之前已经做过的重要改动（简明版）
- 之后每次改动（持续追加）

目标：只写“做了什么、影响哪里、为什么改”，不写太复杂的技术细节。

## 记录约定（固定执行）

- 每次我完成代码修改后，必须先更新本日志，再结束本次任务。  
- 如果有 `commit`，日志里要写上对应 `commit id`。  
- 只写用户可感知变化和关键原因，保持简明。

---

## stock页面更新日志

### 1) 布局与信息结构
- 首页从 `Tracked Companies` 开始改为左右分栏，整体比例保持约 `2 : 0.7`，并对齐 `News` 页的左右间距。
- `Tracked Companies` 区域卡片改为一行 3 个，随机展示 9 个，避免一次性展示全部公司造成拥挤。
- `Market Summary`、`Heatmap`、`Spotlight Stocks` 去掉多层外框，改为更简洁的单层容器。
- 删除了对用户价值较低的提示文案（如缓存来源说明、随机卡片说明等），页面更干净。

### 2) Tracked Companies 与股票池逻辑
- 修复“有 records 但 tracked companies 为空”的问题：补齐记录清洗与 ticker 归并逻辑。
- 对缺少 ticker 的记录增加公司名补全策略；补全失败时不进入主展示列表，避免脏数据污染页面。
- 遇到不被行情源识别的 ticker（如部分跨市场写法）会自动跳过/替换，不再让整块请求报错。

### 3) API 稳定性与缓存
- 增加多数据源 fallback（报价/历史/基础信息分层回退），减少单一上游异常导致全页失败。
- 增加冷却与失败降噪机制，避免同一错误短时间反复触发。
- 增加持久化缓存策略（含 10 分钟级别缓存），降低刷新时重复打 API，提升稳定性与成本表现。

### 4) Heatmap 体验与交互
- 重做 heatmap 为“统一总图”风格，所有公司在一个视图中展示（ticker + 涨跌幅）。
- 修复 heatmap 悬停导致白屏/跳页的问题（事件处理与状态更新冲突已规避）。
- 悬浮信息卡改为跟随位置智能展开，不再固定遮挡顶部公司。
- heatmap 支持点击跳转到公司详情页；悬停可看公司关键信息，点击可深看详情。
- 热力块尺寸下调，提升信息密度，减少“单块过大”导致的视觉压迫。

### 5) Market Summary 与 Spotlight Stocks
- `Market Summary` 改为站内直接阅读，不强依赖外跳；条目扩展为 5 条并支持可点击超链接来源。
- 修复摘要内容显示不完整、hover 出现白框等问题。
- `Spotlight Stocks` 调整为最多 3 个，并从“亮点事件/异动特征”选股，不与 leaders board 重复。
- `Spotlight Stocks` 增加小型行情图，支持快速看到近期走势而不必先点进详情。

### 6) 数据质量修复（重复、行业、指标）
- 修复 `Alphabet` 重复展示（`GOOG/GOOGL` 去重与同公司归并策略）。
- 修复行业映射错误（如 Alphabet 归类到 Technology 的规则校正）。
- 修复部分公司 `change_percent` 丢失/不显示问题，统一字段兜底与数值解析逻辑。
- 修复部分 `market cap/sector` 缺失问题，增加可用来源与映射补全。

### 7) Logo 显示质量修复
- 修复 Apple logo 外圈异常、Boeing/Lockheed 模糊等问题。
- logo 源优先级改为高质量图源优先，低质量 favicon 仅作为末级兜底。
- logo 样式改为 `contain` 展示，避免裁切变形与放大糊化。

### 8) Spotlight 视觉重做（Perplexity风格参考）
- 把 Spotlight 每条股票卡的图表显著放大，改为“左侧大图 + 右侧关键指标 + 下方解读”结构。
- 增强信息可读性：保留价格与涨跌主信息，同时右侧集中展示 `Highlight / Industry / Volume / Market Cap`。
- 图表容器改为更有层次感的单框样式，移动端自动收敛图高并改为纵向排布，避免挤压。

### 9) Spotlight 图表悬停详情
- Spotlight 区域的股票图表支持鼠标悬停查看详细点位数据（日期、收盘价、相邻点涨跌、成交量）。
- 增加悬停十字线和高亮点，便于快速定位走势节点。
- 图表区域支持点击直接进入该公司详情页。

### 10) Logo 缺失补齐
- 在不改变现有优质 logo 效果的前提下，新增缺失 ticker（如 `UBER`、`LMT`）的专属 fallback 源。
- 增加 logo 低分辨率自动跳过机制，避免命中空白/极小占位图导致“看起来没 logo”。

### 11) 列表样式简化（去卡片化）
- `Equity Sectors` 改为“行 + 细横线分隔”，不再每个 sector 都是独立圆角框。
- `Popular Companies`、`Leaders Board`、`Peers` 同步改为细分隔线列表风格，减少视觉噪音。
- 保留原有点击交互与信息布局，只调整视觉层级与间距。

### 12) 缺失 Logo 定向修复（不影响已满意样式）
- 针对仍存在空白的 `UBER`、`LMT` 增加稳定静态 logo 兜底源。
- 保留现有 logo 加载优先级与视觉效果，对已正常展示的公司不做变更。

### 13) Spotlight 图表坐标轴补充
- 在 Spotlight 股票图中增加简洁 `x轴时间`（左/中/右）与 `y轴价格`（上/中/下）刻度。
- 保持轻量视觉：仅加细基准线与弱网格，不影响现有悬停 tooltip 和点击跳转交互。

### 14) Logo 精准修正（AMZN / UBER）
- `AMZN` 改为稳定的 Amazon 品牌图标源，修复仅显示橙色弧线的问题。
- `UBER` 改为标准 Uber 品牌 logo 源，替换掉旧版 app 图标样式。
- 仅定向调整这两个 ticker，其他你已满意的 logo 展示策略保持不变。

### 15) Spotlight 改为短周期（日内优先）
- Spotlight 图表改为优先展示近 `24小时` 的日内数据，突出短期亮点变化。
- 当数据包含日内时间点时，`x轴` 自动显示 `HH:mm`（如 09:30 / 12:00 / 15:30）。
- 若某只股票暂时拿不到足够日内点位，会自动回退到短期历史，避免图表空白。

### 16) Market Summary 摘要截断修复
- 修复 `Market Summary` 中“句子看起来没显示全”的问题：后端不再只取单一短字段。
- 新闻摘要改为 `description + snippet` 的去重合并策略，优先输出更完整的一段文本。
- 升级新闻缓存键版本，避免旧缓存里的截断摘要继续被复用。

### 17) Heatmap 外框移除 + Spotlight 真正日内化
- `Tracked Heatmap` 移除外框、阴影与额外容器背景，改为无框展示。
- 后端新增 `intraday_history`（日内 30m/1h 粒度）并返回给前端。
- Spotlight 图表优先使用 `intraday_history`，确保亮点股默认看近 24h 变化，而不是 1 个月走势。
- 升级前端股票缓存 key 到 `v2`，避免继续命中旧缓存导致仍显示月线。

### 18) Market Summary 固定展示 5 条
- Market Summary 增加多种子市场查询（SPY / QQQ / DIA）与去重聚合逻辑。
- 当单一查询只返回 2-3 条时，自动补拉并凑满 5 条（有数据时优先保证满 5）。

### 19) 数据回退修复（恢复“刚刚那种数据量”）
- 修复前端股票缓存版本切换导致的“旧数据像消失了”问题：新版本缓存读取增加对旧版缓存 key 的兼容回读。
- 当 `uploaded filings` 暂时为 0 时，`Tracked Companies` 不再空白，自动回退用 watchlist 补齐展示。
- 后台预取策略从“只预取上传公司”改为“上传公司 + watchlist + 默认池”联合预取，恢复首页卡片、热力图和榜单的数据密度。

## 2026-04-27 最近已完成改动（Stock / News）

1. `c49ad26`  
   - 调整了 `stock`、`stock详情`、`news` 的左右栏比例。  
   - `stock` 首页小卡片图更饱满，视觉更像行情卡片。  
   - 详情页图表支持鼠标悬停读数（日期、价格、OHLC、成交量）。  
   - `Financial Data` 年份改为下拉选择。  
   - 优化了详情页信息密度（字体更紧凑）和 Back 按钮大小。

2. `6f22a28`  
   - `stock` 首页移除了大号 Price Trend 主图。  
   - 热力图改成“单一总图”，不再按行业拆分多个大块。  
   - 热力图支持 hover 信息卡（公司、涨跌、价格、市值、成交量）。  
   - `Financial Data` 从右侧移动到左侧主区域，可切换查看。

3. `ec8e1c7`  
   - 热力图做了第一轮重设计。  
   - 放大了 stock 主工作区间距，让布局更通透。

4. `ce8edf7`  
   - 丰富了公司详情字段，优化了详情排版。

5. `f5362b4` / `349e155` / `42763f7`  
   - 完成 stock 首页 -> 公司详情的点击进入流程（同站内路由）。

6. `f9be68b` / `ad0e56b` / `8615ded` / `1093e53`  
   - 完成 stock 页面整体风格重构（参考金融看板风格）。  
   - 增加侧栏模块、公司 logo、sector 展示与布局对齐优化。

7. `b63e687`  
   - 增加股票多数据源 fallback、限流冷却和缓存优先机制。  
   - 目标是降低 API 限流时的空白和报错概率。

8. `a96f721`  
   - 修复了 `stock/news` 页面聊天框宽度与左栏不对齐的问题。  
   - 现在聊天框和左侧主内容宽度一致，不会多出来。

9. `3ff8305`  
   - 图表 tooltip 改为仅在鼠标悬停图表时显示。  
   - 详情页公司信息卡去掉 `Sector`，只保留 `Industry`，并补充公司介绍文本。  
   - 修复价格区显示双 `+` 的问题。  
   - stock 首页小股票卡改为一行 3 个。  
   - stock 标题图标从 `💹` 改为 `📊`。

---

## 2026-04-28 最近已完成改动（Dashboard）

提交：`cf54979` `b44b85f` `ec220b4` `9033f52` `4b6b23c` `4eccca2` `9a820b4` `29d0d81`

- 统一了 Dashboard 页头与整体间距：去掉突兀白底块，和 `upload/compare` 视觉风格对齐。  
- 去掉 `Current Configuration` 模块，首页信息更聚焦。  
- 完成 Dashboard Phase1 重设计：保留 `Risk Pulse + Category Intelligence`，移除市场表现模块。  
- Heatmap 重做为分页+搜索+行业筛选，不再一次渲染全部公司；卡片只显示 `RPI`，hover 显示详情，点击可跳转到 `records` 对应记录。  
- Priority 数据链路打通：上传后自动生成优先级；历史记录支持自动补齐；Dashboard 支持自动汇总。  
- 交互与性能优化：悬浮卡改为实时跟随的非透明卡片；Recent Filings 改为轻背景样式；Dashboard summary 增加缓存，跨页面返回不再每次强制等待刷新。  
- 分类体系收敛为固定 9 类（全站统一口径），避免分类无限膨胀，Dashboard 下拉和统计更可控。

备注（已知问题）：
- 当前“未命中强规则”的风险会优先落到 `Strategy & Market`（为了避免大量进入 `General & Other`），因此短期内该类占比会偏高；后续可继续微调关键词权重来拉平分布。

---

## 当前已知现象（便于后续排查）

- `Tracked Companies` 可能显示 0：通常是 records 里没有可用 ticker。  
- 首页只出现 5 个默认股票：来自默认 watchlist（AAPL/MSFT/NVDA/AMZN/GOOGL）。

---

## 后续更新记录模板（每次追加）

### YYYY-MM-DD
- 提交：`commit id`
- 改动：
  - 做了什么
  - 影响了哪些页面/模块
  - 用户侧能看到什么变化
- 备注（可选）：
  - 已知问题 / 后续计划

---

## 2026-04-29 外部 API 调用清单（按当前项目实现）

说明：以下是项目里“真实在调用”的外部 API。免费额度以各官方套餐页当天为准，若官方未给固定日额度，则标注为“未公开固定日配额”。

### 1) 新闻相关
- `Marketaux`（`/v1/news/all`）  
  - 用途：新闻主数据源（news 页面 + agent runtime）。  
  - 免费额度：`100 requests/day`（free tier，且单次返回条数有限）。  
- `TheNewsAPI`（`/v1/news/all`）  
  - 用途：新闻 fallback（agent runtime）。  
  - 免费额度：按其 free plan 计费口径执行（项目未硬编码日上限；以控制台/官方套餐页为准）。  
- `Currents API`（`/v1/search`, `/v1/latest-news`）  
  - 用途：新闻 fallback（agent runtime），空关键词时走 latest-news。  
  - 免费额度：按其 free plan 计费口径执行（项目未硬编码日上限；以控制台/官方套餐页为准）。

### 2) 股票相关
- `TwelveData`（quote/time_series）  
  - 用途：股票主数据源之一（agent runtime）。  
  - 免费额度：`800 credits/day`（free/basic 口径）。  
- `Financial Modeling Prep (FMP)`（quote/historical-price-full）  
  - 用途：股票 fallback 数据源（agent runtime）。  
  - 免费额度：按其免费套餐口径执行（项目未硬编码日上限；以官方套餐页/控制台为准）。  
- `Yahoo Finance`（query1/query2 endpoints，经 yfinance 或直接请求）  
  - 用途：股票 fallback 与页面行情数据。  
  - 免费额度：未公开固定“每天 N 次”配额，实际受限流策略影响。  
- `Stooq`（CSV 历史价格）  
  - 用途：lite 行情 fallback。  
  - 免费额度：未公开固定日配额（项目侧未硬编码上限）。

### 3) 报告抓取与解析相关
- `SEC EDGAR`（`efts.sec.gov`, `data.sec.gov`, `www.sec.gov/Archives`）  
  - 用途：10-K 检索、元数据与原文下载。  
  - 免费额度：公开接口，无项目内配额硬编码（需遵守 SEC 访问规范）。

### 4) 模型与云能力相关
- `AWS Bedrock Runtime`（模型推理）  
  - 用途：聊天与分析生成。  
  - 额度：非“免费固定日额度”模式，按云侧账单/配额策略。  
- `AWS Textract / S3 / AgentCore Runtime`  
  - 用途：文档抽取、存储、agent runtime 调用。  
  - 额度：按 AWS 账户配额与计费策略。

### 5) 其他外部服务（前端辅助）
- `Open-Meteo`（天气）  
  - 用途：news 侧栏天气。  
  - 免费额度：按官方 fair-use/套餐口径，项目未硬编码上限。  
- `ipwho.is`、`ipapi.co`（地理定位）  
  - 用途：天气定位 fallback。  
  - 免费额度：按各自免费套餐口径，项目未硬编码上限。

### 6) 本次修复记录（news / dashboard）
- 修复 `news`：空查询时增加“双阶段热点回退”（7天失败后自动扩到30天并扩展热门 ticker）；若全部 provider 失败，明确展示错误，不再静默空白。  
- 修复 `dashboard`：`/api/dashboard/summary` 增加前端请求超时，避免页面长期停留在 `Refreshing…` 无反馈状态。

### 7) Codex 导航手册更新（agent.md）
- 重写 `agent.md` 为“快速定位手册”，明确每次改代码前的最短读取路径。  
- 明确默认主栈是 `frontend/src + agentcore_deploy`，并标注 `views/* + app.py` 为旧 Streamlit 路径，默认不优先阅读。  
- 新增“按需求类型 -> 优先文件”的入口索引（agent逻辑、聊天体验、前端页面、API、landing page）。  
- 新增“页面到文件映射”和“API到文件映射”，减少后续全仓扫描时间。

### 8) 页面加载提速（records / compare / news / dashboard）
- 后端 Runtime 改为 `ThreadingHTTPServer`，避免单线程请求排队导致页面互相阻塞。  
- 增加运行时缓存：`index`、`record result`、`ticker map`、`agent reports`、`records list`、`dashboard summary`（带 TTL 与自动失效）。  
- 统一在 S3 写入/删除后触发缓存失效，避免脏数据长期停留。  
- `dashboard` 支持后端 `force=1` 强制重算；前端点击 refresh 时会触发该模式。  
- `records` 首屏改为轻量列表请求（不再默认 `include_result=1` 全量拉取每条结果），详情保持按需加载。  
- `compare` / `records` / `upload` / `news hot quotes` 增加请求超时，避免长时间无反馈。  
- 新增记录元信息回填：新写入的 record 在 index 中保存 `risk_items/risk_categories/has_ai_summary`，减少后续列表页计算压力。

### 9) Chatbot 与主 Agent 解耦（React 主链路）
- 右下角 `FloatingChatWidget` 改为独立产品助手：
  - 不再复用 `workspaceChat/chatMemory`，不再共享主 Agent 线程与上下文。
  - 不再跳转 `/agent` 页面后再发消息，改为本地面板内直接对话。
  - 移除 `New Chat` 按钮，保留单一输入发送体验。
- 新增后端接口 `POST /api/chatbot/help`：
  - 专门用于“如何使用 RiskLens”问答，不走主 Agent 的意图路由与工具链。
  - 对“想要实时分析/行情/新闻结论”的问题会引导到主 Agent 或对应页面。
- 补充：
  - `api/meta` 增加 `/api/chatbot/help (POST)` 暴露。
  - 本次未继续修改 Streamlit 旧路径（`views/*` / `app.py`）。
  - chatbot UI 微调：聊天框缩小（`360x500`）、发送按钮嵌入输入框右侧、按钮箭头加大便于识别。
  - chatbot 文本微调：发送与回复气泡字体下调约 1-2 号（更紧凑、阅读负担更低）。
  - 侧栏 Logo 交互修复：侧栏展开时点击 Logo 触发“新建聊天”；侧栏收起时点击 Logo 仅展开侧栏。
  - chatbot 输入框高度微调：输入框最小高度进一步下调（`88px -> 80px`）。
  - Stock 页面优化：引入 `S&P 100` market universe 作为市场池（用于 market-wide 排行/同业候选），并增加后台分批预热加载。
  - 公司信息卡优化：后端新增 FMP profile 字段补全，与已有 provider 合并（行业/国家/员工/CEO/IPO/简介等）。
  - 顶部 UI 控件新增：右上角加入小尺寸语言切换与深浅色切换 tab（带图标、状态持久化）。
  - 国际化第一版：导航 Tab、侧栏常用文案、全局输入提示支持中英文切换。
  - 主题第一版：新增 dark/light 切换并覆盖主容器、导航、卡片、输入框等核心区域样式。

### 10) Stock 市场榜单与详情补全修复（本轮）
- 前端本地股票缓存升级到 `v3`，并拆分 `FULL/LITE` 两套 key，避免轻量数据覆盖完整详情数据。  
- 详情页新增“自动补全拉取”：当命中 lite 或关键字段缺失时，会触发一次 full quote 刷新（静默执行）。  
- `bundleMap` 合并策略优化：若先有 full，再收到 lite，只更新行情字段，不覆盖 CEO/IPO/Country 等资料字段。  
- `Popular Companies` 排序逻辑改为按 `market cap -> volume -> 波动幅度` 排序，不再按公司名字母顺序，展示更接近真实市场。  
- 后端 full quote 显式返回 `lite: false`，便于前端明确区分数据类型。  
- 紧急修复白屏：`routeSymbol`/`isCompanyView` 前置声明，避免在声明前被 `useEffect` 依赖读取导致运行时崩溃。  

### 11) 深色主题输入区与右上角小 Tab 优化
- 仅优化了 `dark` 模式下的输入区适配：landing 输入框、底部全局输入框、附件 chip 与占位符对比度全部重配，修复“内层发灰块/不协调”问题。  
- 保持浅色页面主样式不变，浅色结构和视觉不做改动。  
- 右上角语言/主题两个 tab 下移一点（更贴合导航线），并增强了圆角胶囊质感（渐变、阴影、hover 层次）。  

### 12) 深色主题全页适配补齐（Upload / Stock / Chat）
- 仅针对 `dark` 模式补齐了页面级样式覆盖：`Upload & Records`、`Stock`、`Compare/Tables` 相关容器和文字对比度统一增强。  
- 修复 `stock` 深色下多处文字不清晰问题（卡片标题、副标题、指标表、board tabs、financial table、详情侧栏等）。  
- 修复 `upload` 深色下输入区/结果区/配置区可读性问题（包含顶部配置条、tabs、上传行、placeholder 区域）。  
- 深色模式聊天框优化：assistant 回复气泡改为深色系，不再过亮；同时调整面板、头部、输入框和消息区对比度。  
- 浅色模式未改动。  

### 13) 右上角语言/主题 Tab 微调
- 右上角语言与深浅色两个 tab 再向下微调一点，和导航区更协调。  
- 去掉 tab 的“双层外框感”，改为单层边框视觉（浅色与深色 hover 同步）。  

### 14) 深色模式文字提亮与页面适配补强（不影响浅色）
- 按“深色模式下原本深色字体改浅色”的原则，补齐 `News / Compare / Tables / Upload / Records / Agent` 的文字对比度。  
- 统一修正深色下仍偏亮或偏浅背景的卡片/面板，确保文字和背景层次匹配。  
- 深色模式聊天继续优化：assistant 回复气泡和 agent 聊天气泡进一步改为深色系，减少刺眼感。  
- 所有改动都限定在 `rl-theme-dark` 作用域，浅色模式未改动。  

### 15) Bedrock 主模型迁移：Nova Pro → Claude Opus 4.7（Converse API）
- 提交：`eb5162b`
- 将 `agentcore_deploy/agent.py` 与 `core/bedrock.py` 的真实 Bedrock 调用统一迁移到 `client.converse(...)`，model id 改为 `anthropic.claude-opus-4-7`。  
- 同步更新 `agentcore_deploy/main.py` 与 `agentcore_deploy/chat_agent.py` 的兜底 model id 和“我是什么模型”回答文案。  
- 选择 Converse API 是为了让 Nova / Claude / 其他 Bedrock 模型共享同一套 messages schema，后续换模型主要只改常量。  
- 对外 API 行为不变；仍返回原有文本/报告结构。  
- 备注：Claude Opus 4.7 成本明显高于 Nova Pro，Railway 对应 IAM 也需要确认是否具备 `bedrock:Converse` / `bedrock:InvokeModel` 权限。  

### 16) 清理 Streamlit 残留代码
- 提交：`eb5162b`
- 删除旧 Streamlit 主栈：`app.py`、`views/*`、`components/*`、`storage/*`、旧 `core/agent.py`、`core/chat_widget.py`、`core/i18n.py`、`core/global_context.py`、`core/comprehend.py`、`core/auto_bootstrap.py`、`core/classifier.py` 以及旧部署包 `risklens_agent.zip`。  
- 保留当前生产链路需要的 `core/extractor.py`、`core/table_extractor.py`、`core/bedrock.py`，并移除其中的 Streamlit 依赖，secret 统一改为从环境变量读取。  
- 删除 `.streamlit/config.toml`，但按本次要求保留本地 `.streamlit/secrets.toml`，该文件仍由 `.gitignore` 忽略，不会 push 到 GitHub。  
- 清理根依赖中的 `streamlit`、`strands-agents`、`plotly`、`yfinance`，并更新 devcontainer / 部署手册 / Codex 导航手册中的旧 Streamlit 文案。  
- 对外行为：React + Railway 主链路不变；旧 Streamlit 入口不再存在，如需参考可从 git history 查看。  

### 17) Upload 优化 Phase 1：edgartools 作为 HTML Item 定位主路径
- 提交：`dff5b82`
- 新增 `core/sec_sections.py`，使用 edgartools 的本地 HTML parser 定位 10-K 的 `part_i_item_1` 与 `part_i_item_1a`，不额外请求 SEC 网络。  
- `core/extractor.py` 新增 `locate_item1_overview()` / `locate_item1a()`：优先走 edgartools section API，失败时自动回退到原有 BeautifulSoup + 正则切片。  
- HTML 的 Item 1 overview、Item 1A deterministic extraction、Item 1A Bedrock extraction 都改为先使用统一 section locator；前端输出 schema 仍保持 `[{"category": str, "sub_risks": [str, ...]}]` 不变。  
- 根目录与 Railway runtime requirements 都补充 `edgartools>=5.30`；Railway requirements 同步补齐 `beautifulsoup4/lxml/PyPDF2/certifi`，避免后端部署缺包。  
- 验证：Apple 2024、Tesla、Lockheed、JPMorgan、Pfizer 的真实 10-K HTML 均可定位 Item 1A，风险条数均超过 8 条；后端 `/health` 本地返回 200。  
- 备注：验证时发现现有 `find_cik()` 对部分公司名会误命中或遇到 SEC search 500，这属于 SEC CIK 搜索层问题，不属于本 Phase 的 section extraction；后续可单独增强 ticker -> CIK 映射。  

### 18) Upload 优化 Phase 2：sec-parser 语义切片兜底
- 提交：`386ced3`
- 在 `core/sec_sections.py` 增加 sec-parser 语义元素解析路径：当 edgartools 无法定位 `Item 1` / `Item 1A` 时，按语义标题切到下一个 Item 标题。  
- `core/extractor.py` 的统一 locator 顺序变为：edgartools → sec-parser → 原有 BeautifulSoup/正则 fallback，上传输出 schema 不变。  
- 根目录与 Railway runtime requirements 补充 `sec-parser>=0.58.1`，并把 `lxml` 约束调整为 `>=5.2.2,<6.0`，避免 sec-parser 与新版 lxml 约束冲突。  
- 验证：强制模拟 edgartools miss 后，Apple 2024 10-K 可由 sec-parser 切出 Item 1 / Item 1A，Item 1A 仍可抽出超过 8 条风险。  

### 19) Upload 优化 Phase 3：Bedrock Converse 工具调用结构化抽取
- 提交：`2592847`
- `core/bedrock.py` 新增 `invoke_with_schema()`，通过 Bedrock Converse `toolConfig` 提交 JSON Schema，并优先读取模型返回的 `toolUse.input`。  
- `extract_item1a_risks_bedrock()` 改用 schema `{blocks: [{category, sub_risks: [{title, source_span}]}]}`，再归一化回前端现有 `[{"category": str, "sub_risks": [str]}]`。  
- 旧的 AI 输出质量门槛从 `coverage 0.85–1.25 + evidence 0.55` 放宽为 `至少 1 条 + evidence_ratio >= 0.4`，减少高质量 LLM 输出被正则 fallback 覆盖的概率。  
- 验证：使用 fake Bedrock Converse response 验证 `toolUse.input` 解析和 Item 1A schema 归一化；未调用真实 Bedrock，避免本地费用和 model 权限不确定性。  

### 20) Upload 优化 Phase 4：长文本 Item 1A 分块与合并
- 提交：`8875a59`
- `core/extractor.py` 新增 `_chunk_item1a_by_headings()`：超长 Item 1A 会优先按内层风险标题分块，无法稳定按标题切时再按段落打包。  
- Bedrock Item 1A 抽取改为逐 chunk 调用 schema 工具输出，再把相同 category 合并，并按 normalized title 全局去重。  
- 这样可以避免超长 Item 1A 被固定字符截断，同时保持前端 `category/sub_risks` 输出结构不变。  
- 验证：本地长文本样本可拆分为多个 chunk；重复 category / title 合并去重逻辑通过。  

### 21) Upload 优化 Phase 5：旧关键词分类器状态确认
- 提交：`eb5162b`
- PLAN 中提到的 `core/classifier.py` 与 `core/bedrock.classify_risks()` 已在 Streamlit 残留清理中删除，当前 React + Railway 主链路不再调用旧关键词分类器。  
- 本轮用 `rg` 复查 `core/agentcore_deploy/frontend`，未发现 active 的旧 `core.classifier` 或 `classify_risks` 调用。  
- 备注：SASB-26 精准分类需要真实 Bedrock 输出与人工样本核对，不能只靠本地 fake response 诚实验收；后续应作为单独质量评估任务推进。  

### 22) Upload 优化 Phase 6：PDF 文本路径复用语义 section locator
- 提交：`be8a348`
- `extract_item1a_risks_from_text()` 新增 Textract 文本 → 伪 HTML 的转换，再优先走 sec-parser 定位 Item 1A。  
- 如果 sec-parser 无法在伪 HTML 中定位 Item 1A，会自动回退到旧的纯文本 `_extract_risks_from_text_fallback()`，不改变失败兜底行为。  
- 验证：本地构造的 Textract 风格文本可定位 Item 1A，并抽取出风险条目。  

### 23) SEC 自动抓取：ticker → CIK 精确映射修复
- 提交：`bfc1997`
- `core/sec_edgar.py` 新增 SEC 官方 `company_tickers.json` 的 ticker 精确匹配路径，并加入 24 小时内存缓存。  
- `find_cik(company_name, ticker)` 现在优先用 ticker 查 CIK，查不到才回退到原 SEC search；search fallback 增加公司名相似度排序，降低误命中概率。  
- 验证样本：`AAPL → 0000320193`、`JPM → 0000019617`、`TSLA → 0001318605`、`PFE → 0000078003`、`LMT → 0000936468` 全部通过。  
- 额外验证：`download_10k_html_for_company_year("Pfizer Inc", 2024, "PFE")` 返回 `pfe-20231231.htm`，不再误抓其他公司。  

### 24) Upload 优化 Phase 7：20 份 10-K 回归
- 提交：`22945ab`
- 新增 `scripts/upload_phase7_regression.py`，用于复跑 10 家公司最近 2 份 10-K 的真实 SEC HTML 回归。  
- 回归样本：`AAPL / MSFT / NVDA / AMZN / GOOGL / META / TSLA / JPM / PFE / LMT`，共 20 份 10-K。  
- 结果：Item 1A 定位 `20/20`，达到最小风险条数门槛 `20/20`，平均风险条数 `84.4`，最低风险条数 `11`（PFE 2024），最高风险条数 `330`（JPM 2024）。  
- 覆盖文件时间跨度：report date 从 `2024-06-30` 到 `2026-01-25`，包含科技、互联网、金融、制药、国防等不同 10-K 排版。  
- 备注：分类准确率未写入百分比；本地环境没有 AWS/Bedrock 凭证，也没有人工标注集，因此不能诚实验证 SASB/LLM 分类正确率。当前回归验证的是 SEC 下载、CIK 映射、Item 1A 定位与 deterministic 风险条目抽取稳定性。  

### 39) Upload "How risk scoring works" 三步说明 + Dashboard filter 折回左栏（双层布局）
- 用户提问："上传后会发生什么？"——加两处显式说明，避免靠 chat agent 兜底。
- **Upload 页**新增 `<HowScoringWorksCard>`（`frontend/src/pages/UploadPage.jsx`）：
  - 位置：`tab === 'ingest'` 区块、`ingestMode` 子 tab 切换之后、表单本体之前；manual + auto fetch 两个 sub-tab 都能看到。
  - 形式：靛蓝色边框 stepper info card，3 步横排（≥1024px）/ 竖排（窄屏），用 `→` 箭头连接：
    1. **Extract** — Risk factors pulled from Item 1A of the 10-K filing.
    2. **Score 3 dimensions** — Each risk graded 1-10 on Financial Impact, Likelihood, and Urgency.
    3. **See on Dashboard** — Aggregated into RPI (Risk Priority Index, 0-100) per filing.
  - 不可关闭、不依赖任何 state；首次用户能学，老用户视觉上自动忽略。
  - 不显式提具体权重 (0.4/0.35/0.25)、不画公式——保持 dashboard 上的 RPI 数字与这里的描述一致即可。
- **Dashboard 页 how-to-read box** 文案 1 行扩展：
  - 旧："RPI (0-100) is weighted by H/M/L counts. Higher RPI means..."
  - 新："RPI (0-100) blends three per-risk dimensions — Financial Impact, Likelihood, and Urgency — into High/Medium/Low buckets, then weights the counts. Higher RPI means..."
- **Dashboard 布局再调整（双层布局，比 entry 37 的三层更紧凑）**：
  - 删 entry 37 引入的"中部单行 filter stripe"。filter 5 个控件（Search / Industry / Sort / Rows / Page）改为**竖向堆叠**移入左栏，置于 how-to-read 灰色框下方。
  - 左栏新增 `<div className="rl-heatmap-left-col">`（flex-col）包住 headline + how-to-read + filter stack。
  - 右栏 `.rl-heatmap-priority-side` 删 `align-self: start`，让 grid 默认 stretch；新增 `.rl-heatmap-scope-snapshot` 类的 `flex: 1 1 auto`，让 Scope Snapshot 卡片在右栏内自动撑高、底部跟左栏 filter 列表底部对齐。
  - "Showing X-Y / N · Sorted by RPI..." 状态栏从顶部双栏内挪到双栏外、heatmap 表格上方，作为表格区的小副标题。
  - 全宽 heatmap 表格往上移、视觉上一屏可见行数从 ~20 提升到 ~28+（取决于屏高）。
- CSS（`frontend/src/index.css` 末尾）：
  - 新增 `.rl-heatmap-left-col`（flex-col 容器）+ `.rl-heatmap-filter-stack`（gap 0.55rem 竖排）+ `.rl-heatmap-scope-snapshot`（flex: 1 1 auto 撑高）。
  - 删除不再使用的 `.rl-heatmap-filter-row` + `.rl-heatmap-filter-cell--narrow`；`.rl-heatmap-filter-cell` 简化（去掉 grid 时代的 `flex: 1 1 160px` 弹性宽度，竖向堆叠下不需要）。
  - 新增 Upload 页 `.rl-pipeline-card` 系列：`.rl-pipeline-card-head` / `.rl-pipeline-card-icon` / `.rl-pipeline-card-title` / `.rl-pipeline-steps` / `.rl-pipeline-step` / `.rl-pipeline-step-num` / `.rl-pipeline-step-title` / `.rl-pipeline-step-body` / `.rl-pipeline-step-arrow`，靛蓝色调，≥1024px 横排带箭头、窄屏竖排无箭头。
  - 顶部块注释更新为"两层布局"，旧三层注释 deprecate。
- 验证：`npm --prefix frontend run build` 通过（54 modules / 158.83 KB CSS / 391.06 KB JS / 755ms）；grep 确认 `rl-heatmap-filter-row` / `rl-heatmap-filter-cell--narrow` 在源代码无引用（仅注释里残留以备 grep 参考）。
- 行为变化：
  - Upload 页一进 ingest tab 顶部就能看到 3 步流程介绍，再也不需要去 chat 问"评分怎么算"。
  - Dashboard Risk Pulse Tab 整体更紧凑：filter + heatmap 上下两层，filter 与 Scope Snapshot 在同一双栏 stripe 内对齐底部。一屏可见公司行数显著增加。
  - 首次或换屏宽度时左栏比右栏高的情况，Scope Snapshot 自动吸收高度差，不会再出现"右栏底下大片留白"。
- 提交：`56a617a`

### 38) Risk Pulse filter row 收紧 + heatmap 链接改到 records tab
- 收紧 filter row：删 `Show empty year columns` / `Compact` 复选框 + `Refresh` 按钮（自动刷新已由 `DASHBOARD_CACHE_TTL_MS=5min` 缓存 TTL + ensure-priority 后台 load 兜底）。
- heatmap 永远走 compact 渲染：移除 `compactView` / `showAllYears` 两个 state + 对应的 localStorage 持久化字段；`effectiveYears` 派生不再依赖 toggle，永远按当前 paged viewport 收敛；cell render 拆掉 compact-vs-default 的二选一分支，永远使用 `.rl-heatmap-cell-compact`。
- `heatPageSize` 默认从 10 提升到 40（compact 行高下一屏依然容得下），page size options `[10, 20, 40, 80]`。
- 状态栏文字保留 sort 提示与"Year columns without data on this page are hidden"说明，删掉条件分支后改为常驻提示。
- localStorage prefs 简化：`rl.dashboard.pulsePrefs.v1` 现在只存 `sortMode`，旧字段（`compactView`/`showAllYears`）会被覆盖丢弃，无需手动迁移。
- CSS（`frontend/src/index.css`）：移除不再使用的 `.rl-heatmap-toggle-cell` + `.rl-heatmap-filter-cell--action` 规则；保留 `.rl-heatmap-filter-cell` / `--narrow` / `.rl-heatmap-cell-compact`；旧的 `.rl-heatmap-filter-grid` 规则继续保留待 grep 取证。
- heatmap cell 点击跳转改成新路由：`/library?record_id=…` → `/upload?tab=records&record_id=…`（用户已弃用 LibraryPage，records 真实入口在 UploadPage 的 records tab）。
- `frontend/src/pages/UploadPage.jsx`：mount 阶段解析 `window.location.search`：
  - `?tab=records` → 自动 `setTab('records')`
  - `?record_id=<rid>` → `setSelectedId(rid)` + 把 rid 作为 `preferRid` 传给 `refreshRecords`，等 records 拉回后查匹配 record 的 `company` 字段，自动 `setSelectedCompanyKey(company.toLowerCase())` 让对应公司组展开，cancellation flag 防 race。
  - URL 异常（malformed querystring）try/catch 兜底 fallback 到默认 ingest tab。
- 验证：`npm --prefix frontend run build` 通过（54 modules / 157.41 KB CSS / 389.50 KB JS / 789ms）；grep 确认 DashboardPage 内已无 `compactView`/`showAllYears`/`/library?` 残留；CSS 内已无 `.rl-heatmap-toggle-cell`。
- 行为变化：
  - 用户感知：filter 仅剩 5 个控件（Search / Industry / Sort / Rows / Page），整体高度比 entry 37 再矮一截；不再需要 Compact 开关，默认就是紧凑模式；不再需要手动 Refresh。
  - 跳转感知：从 dashboard 点击 cell 不会再去 LibraryPage，直接落在 UploadPage 的 records tab 上、对应公司组自动展开、目标 record 高亮选中。
- 提交：`66b231e`

### 37) Dashboard Risk Pulse 三层布局重构 + 删除 5 个已完成 plan 文件
- 落地 `DASHBOARD_REDESIGN_PLAN.md` 全部改动。Risk Pulse Tab 从"左 1.75fr 热力图 + 右 1fr 多块拼接"改成单 panel 三层结构：
  - **顶部双栏 header**：左 `1fr` 是 Priority Heatmap 标题 + How to read quickly 灰色框；右 `320px` 是 Priority Mix（H/M/L 三色卡）合并 Scope Snapshot（Avg RPI / Rows with priority），与左半顶部对齐。
  - **中部单行 filter row**：Search / Industry Group / Sort / Rows / Page / Compact toggle / Show empty year columns toggle / Refresh，全部 flex 一行（`flex-wrap` 兜底窄屏自动 wrap）。
  - **底部全宽 heatmap 表格**：不再被右栏挤压，整张表占满 panel 内宽度。
- 删除项：
  - 右栏 `Recent Filings` 整段 + `recent` useMemo（之前依赖 `data.recent_records`，本次重构后不再展示）。
  - 旧的 `rl-heatmap-filter-grid` 5 列 grid（CSS 规则保留以防别处引用，JSX 不再使用）。
- 新增 state（`frontend/src/pages/DashboardPage.jsx`）：
  - `compactView`（bool, 默认 false）：紧凑视图，cell 高度 44px → ~28px、宽度 78px → ~56px、隐藏 "RPI" label，行 padding 减半。开启时 `heatPageSize` 自动从 ≤14 升到 40，一屏可见公司数 ≈ 翻倍。
  - `showAllYears`（bool, 默认 false）：年份列默认按当前 paged viewport 收敛——若 paged 公司里没有任意一家有 2020 数据，2020 列自动隐藏；翻页到含 2020 数据的公司时 2020 列自动出现。开启 toggle 后锁定显示全部年份。
  - `sortMode`（`'rpi'`/`'name'`，默认 `'rpi'`）：默认沿用后端 `priority_heatmap.companies` 的 max RPI DESC 排序（`agentcore_deploy/main.py:_dashboard_summary` L2023-2027），未评分公司落底；切到 `name` 时本地按字母重排。
  - 三个偏好通过 `localStorage` key `rl.dashboard.pulsePrefs.v1` 持久化，刷新页面记住选择；SSR / private mode / quota 失败安全降级。
- 新增 useMemo：
  - `sortedCompanies`：替代旧的 `companiesOrdered`，根据 `sortMode` 切换。
  - `effectiveYears`：基于 `pagedCompanies + heatCellMap` 派生，过滤掉视野内无数据的年份；`showAllYears` 开启时直接返回 `yearsOrdered`；空 viewport 兜底返回全量年份避免空状态。
- 行号变化（DashboardPage.jsx）：因布局重写顶部 stripe 改用 `xl:grid-cols-[1fr_320px]` + 中部 `rl-heatmap-filter-row` + 底部表格；page-size options 从 `[8, 10, 14, 20]` 扩到 `[10, 20, 40, 80]`；`pagedCompanies` 之后新增 `effectiveYears` useMemo；thead/tbody 全部用 `effectiveYears` 替代 `yearsOrdered`；cell 渲染按 `compactView` 切换 `linkClass`/`emptyClass`/`tdClass` 三套 className；状态栏新加两条说明（"Sorted by RPI..." / "Year columns without data on this page are hidden."）。
- CSS 追加（`frontend/src/index.css` 末尾）：`.rl-heatmap-priority-side`（右栏 `align-self: start`）、`.rl-heatmap-filter-row` + `.rl-heatmap-filter-cell` + `--narrow` + `--action`、`.rl-heatmap-toggle-cell`、`.rl-heatmap-cell-compact` + `--empty`。旧的 `.rl-heatmap-filter-grid` 规则**保留**，JSX 已不再使用，留作未来 grep 时的参考。
- 删除 5 份已完成的 plan：`RPI_OPTIMIZATION_PLAN.md`（落到 entry 26-28）、`CATEGORY_OPTIMIZATION_PLAN.md`（entry 25 + 31）、`S3_PLAN.md`（entry 29 + 30）、`EXTRACTION_FIX_PLAN.md`（entry 31）、`UPLOAD_OPTIMIZATION_PLAN.md`（entry 19-24）。`PLAN.md` / `DASHBOARD_REDESIGN_PLAN.md` / `AGENTS.md` / `agent.md` / `README.md` / `PROJECT_CHANGELOG_CN.md` 保留。
- 验证：`npm --prefix frontend run build` 通过（54 modules, 158.79 KB CSS / 390.40 KB JS）；grep 确认 `recent` / `companiesOrdered` / `yearsOrdered.map` 旧符号已无残留；不动后端、不动数据契约、不动 Category Intelligence Tab。
- 行为变化（用户可感知）：Risk Pulse Tab 整张图占满中央，filter 不再挤五行，76 家公司在 compact 模式下 1 屏可见 ≥25 家（4K 屏更多），2020 列在多数页面自动消失，含 2020 数据的页面会自动恢复显示；偏好刷新页面后保留。
- 提交：`d0cc3bb`

### 36) rescore_agent_priority.py：Nova Pro 截断 JSON 容错（修复 + 重试 + 原始日志）
- 现象：跑 Apple 2020 时 Nova Pro 偶发返回截断 JSON（`Unterminated string` / `Expecting value`），脚本直接 fail 整批 record。
- 改法：在 `_invoke_extraction` 之上加一层 `_invoke_with_json_retry`，两个 LLM 调用点（`_score_one_batch` 批量评分、`_generate_agent_report` 报告生成）都改走它。
- 修复策略（按数据保留度从高到低尝试）：
  1. **最长 balanced prefix**：扫描原文记录最外层容器最后一次平衡的位置，截到那里。
  2. **最后一个 top-level comma + 关闭根容器**：丢掉最后一个未完成的元素。
  3. **LIFO close**：未关闭的 string 补 `"`，剩余 stack 按相反顺序补 `}` / `]`，处理深层截断。
  4. **空容器兜底**：保留 shape，丢全部数据，确保解析不抛异常。
- 重试策略：第 1 次解析失败时，prompt 加 `CRITICAL: Output ONE complete JSON ...` 后缀（数组要求 `reasoning` < 60 字符、对象要求每条 list entry < 80 字符），`max_tokens` 翻倍（2048→4096 / 1500→3000），再调一次 Bedrock。
- 日志：每次 attempt 失败把原始返回截断到 2KB 打到 stderr，前缀 `· {label}: raw_response=...`，方便从 Railway 日志直接看 Nova Pro 实际吐了什么。
- 验证：本地 8 个单测全过——
  - well-formed → 直接 parse、`repair_used=False`
  - 截断数组（最常见模式：`[..., {...partial`）→ 保留完整元素 + 关闭 `]`，丢 partial
  - 截断对象 + 未关闭字符串 → 补 `"` + LIFO close 后可解析
  - markdown fences 包裹 → strip 后正常 parse
  - 末尾有杂文字 → 在 first `[`/`{` 之前的内容被 trim
  - 完全 garbage → 返回 `None`、err 含 `no_json_root_found`
  - 深层嵌套截断（`{"a":{"b":[1,2,{"c":"unfinished`）→ 顶层 key 保留
  - 边缘 case（空字符串、纯空白、孤立 `[`）→ 兜底到 `None` / `[]`
- 同步性：所有改动只在 `scripts/rescore_agent_priority.py` 内部，prompt suffix 与 batch / 阈值常量与 `agentcore_deploy/agent.py` 一致。
- 提交：`2cbce58`

### 35) rescore_agent_priority.py 改成完全自包含，去掉 agentcore_deploy 依赖
- 现象：在本地 / Railway 运行 entry 34 引入的 `scripts/rescore_agent_priority.py` 时报 `ModuleNotFoundError: No module named 'agent'`。根因是脚本通过 `extraction_pipeline.attach_agent_priority_report` → `agentcore_deploy.main._generate_agent_priority_report` → `_get_run_agent` → `from agent import run_agent` 调链下到一个 AgentCore 部署专用的扁平 import（`from agent import ...` 只有把 `agentcore_deploy/` 加入 `sys.path` 时才解析得到，其它运行环境直接挂）。
- 改法：脚本不再 `import scripts.extraction_pipeline` 也不再 `import agentcore_deploy.*`，scoring 整条链 inline 进脚本本身，仅依赖 `boto3` + `scripts.industry_mapping`。
  - 自带 `_s3_client` / `_bedrock_client` / `_get_bytes` / `_put_bytes` / `_invoke_extraction`，从 env 读 `S3_BUCKET` / `AWS_REGION` / `BEDROCK_REGION` / `BEDROCK_EXTRACTION_MODEL_ID`（默认 `us.amazon.nova-pro-v1:0`）。
  - 复制 entry 26/27 的 RPI 三维评分链：`_PRIORITY_HIGH_THRESHOLD=7.0` / `_PRIORITY_MEDIUM_THRESHOLD=4.0` / `_PRIORITY_DIM_WEIGHTS=(0.4,0.35,0.25)` / `_PRIORITY_BATCH_SIZE=40`；helper `_clamp_int_1_10` / `_compute_score_from_dims` / `_priority_from_score`；批量函数 `_score_one_batch` / `_prioritize_risks` / `_build_priority_lists` / `_generate_agent_report` / `_normalize_report`；最终 `_build_agent_priority_report` 是 `agentcore_deploy/agent.py:run_agent` 减去 `_answer_user_query_impl` 步骤的纯净版（rescore 没有 user_query）。
  - 文件头部加注释说明"必须与 `agentcore_deploy/agent.py` 保持同步"，避免未来分叉。
- 行为不变：输出的 `result["agent_report"]` 字段结构与原版完全一致（`priority_matrix.{high,medium,low,unscored}`、`scoring_status`、`executive_summary` 等），dashboard 与 chat_context 不需要任何改动。
- 验证：
  - `python scripts/rescore_agent_priority.py --help` 输出完整 flags（`--dry-run` / `--write` / `--industry` / `--ticker` / `--skip-already-scored` / `--limit` / `--report`）。
  - `python -c "import scripts.rescore_agent_priority as r"` 后 `sys.modules` 中**没有** `extraction_pipeline` 或任何 `agentcore_deploy.*` 模块。
  - 数学等价性自检：`_compute_score_from_dims(8,6,7) == 7.05`、`_priority_from_score(7.0) == "High"`、`_priority_from_score(6.99) == "Medium"`、`_priority_from_score(3.99) == "Low"`、`_clamp_int_1_10` 对越界 / 非数字输入正确截断。
- 后续待执行：下次 `agentcore_deploy/agent.py` 改 RPI prompt / 权重 / 阈值时，**必须同步改 rescore 脚本里 `_score_one_batch` 的 prompt 与三个常量**，否则 dashboard 上的旧 record（rescored）和新 record（live runtime 评的）会算法分叉。
- 提交：`bc31bb5`

### 34) 新增 scripts/rescore_agent_priority.py：只重跑 RPI 评分，不重新抽取
- 用途：当评分管线变化（新 prompt / 新权重 / 新 modelId — 比如 entry 32 把 RPI 切到 Nova Pro）但 `risks` 内容本身仍可信时，可以只刷 `agent_report` 字段而不付一遍 Item 1A 抽取的钱。
- 工作流程：列 `s3://<bucket>/10k_filings/<industry>/<dir>/<year>_10K_risks.json` 全量 → 对每份读 JSON 取 `result["risks"]` → 调 `extraction_pipeline.attach_agent_priority_report(result, company, year)`（即 `agentcore_deploy.main._generate_agent_priority_report`，复用 entry 26/27 的 RPI 三维评分链 + entry 32 的 extraction modelId）→ 原地覆写 `result["agent_report"]`、新增 `result["agent_report_rescored_at"]` 时间戳 → 把整份 JSON `put_bytes` 写回同一个 key。HTML / `risks` / `company_overview` 不动。
- CLI 选项：默认 `--dry-run`（只列计划，不调 Bedrock）；`--write` 真跑；`--industry`/`--ticker` 局部 rollout；`--skip-already-scored` 断点续跑（按 `agent_report.scoring_status ∈ {ok, partial}` 或老 record 的 `priority_matrix` 存在判定）；`--limit N` 成本封顶；`--report <path>` 自定义日志路径（默认 `scripts/rescore_agent_priority.report.json`）。失败 record 不打断其他 record，结尾 summary 显示 ok / skipped / failed 分布。
- 部署用法：`railway run python scripts/rescore_agent_priority.py --dry-run` 干跑、`--write` 真跑（Railway env 注入凭证、命令在本机执行）；或在 Railway 容器里直接 `python scripts/rescore_agent_priority.py --write`。
- 验证：`python scripts/rescore_agent_priority.py --help` 输出完整 flags；`from scripts import rescore_agent_priority as r; r.JSON_KEY_RE.match("10k_filings/Technology/Apple_AAPL/2025_10K_risks.json")` 命中。
- 提交：`2cfbc6c`

### 33) modelId 加上 us. 跨区域 inference profile 前缀 + 完整版本后缀
- 把 entry 32 引入的两个默认 modelId 改成 Bedrock cross-region inference profile 的标准形态：
  - `amazon.nova-pro-v1:0` → `us.amazon.nova-pro-v1:0`
  - `deepseek.v3.2` → `us.deepseek.v3.2-v1:0`
- 命中文件：`core/bedrock.py:23`、`agentcore_deploy/agent.py:28-29`、`agentcore_deploy/main.py:3827/3829/3841/3843`、`agentcore_deploy/chat_agent.py:424/457/458`、`deploy/railway.env.example:22-23`、`.streamlit/secrets.toml:9-10`（gitignored）、`scripts/README.md:31-32`。
- 验证：`from core.bedrock import EXTRACTION_MODEL_ID` 输出 `us.amazon.nova-pro-v1:0`；`from agentcore_deploy.agent import AGENT_MODEL_ID, get_model_id, get_extraction_model_id` 全部回新值；main / chat_agent 导入通过。
- 提交：`7553002`

### 32) 双模型配置：提取/分类/RPI 用 Nova Pro，agent 对话用 DeepSeek V3.2
- 拆分原本统一走 Claude Opus 4.7 的 Bedrock 调用路径，按用途拆为两套 modelId：
  - **EXTRACTION**：风险因子提取、9 桶分类兜底、RPI 三维评分、agent 优先级报告 → 默认 `amazon.nova-pro-v1:0`，env `BEDROCK_EXTRACTION_MODEL_ID` 覆盖。
  - **AGENT**：chat 对话回答用户问题、follow-up 文本润色、"我是什么模型"身份回复 → 默认 `deepseek.v3.2`，env `BEDROCK_AGENT_MODEL_ID` 覆盖。
- `core/bedrock.py`：把 `MODEL_ID` 重新定义为 `EXTRACTION_MODEL_ID = os.getenv("BEDROCK_EXTRACTION_MODEL_ID", "amazon.nova-pro-v1:0")`；`_invoke` / `invoke_with_schema` 改用 `get_extraction_model_id()` 实时读取，环境变量重启即生效；`MODEL_ID` 与 `BEDROCK_CLAUDE_OPUS_47_MODEL_ID` 留 alias 防止旧 import 报错。
- `agentcore_deploy/agent.py`：
  - 新增 `EXTRACTION_MODEL_ID` / `AGENT_MODEL_ID` 两个常量，`MODEL_ID` 改为 `AGENT_MODEL_ID` 别名。
  - `_invoke` 加可选 `model_id` 参数；新增 `_invoke_extraction` / `_invoke_agent` 两个内部 wrapper 与对应公开 helper `invoke_llm_text`（agent）/ `invoke_llm_extraction`（extraction）。
  - `_score_risks_with_llm`（L405）、`_generate_agent_report_impl`（L568）切到 `_invoke_extraction`；`_answer_user_question_impl`（L648）保持 `_invoke_agent`。
  - 公开 `get_model_id()`（agent 模型）+ 新增 `get_extraction_model_id()`，main.py 读取后注入 chat_context。
- `agentcore_deploy/main.py`：
  - 新增 `_get_extraction_llm_invoke()` / `_get_extraction_model_id()`，加对应模块级缓存 `_LLM_EXTRACTION_INVOKE` / `_EXTRACTION_MODEL_ID`，`agent.py` 旧版本时优雅降级到 chat invoker。
  - `_classify_with_llm_fallback`（dashboard 9 桶分类兜底）切到 extraction invoker。
  - chat_context 新增 `"extraction_model_id"` 字段，让 chat_agent 的"我是什么模型"回答可同时提到两套模型。
- `agentcore_deploy/chat_agent.py`：
  - `_general_chat_answer` / `_model_identity_answer` 的 fallback model_id 改为 `deepseek.v3.2`；`_model_identity_answer` 同时读取 `extraction_model_id`，回答里中英文都说明"对话用 DeepSeek V3.2 / 提取走 Nova Pro"。
- `core/extractor.py`：两处 docstring 从"Claude Opus 4.7"改为"Bedrock extraction model (Amazon Nova Pro by default — see core/bedrock.EXTRACTION_MODEL_ID)"。
- 配置：
  - `deploy/railway.env.example` 加 `BEDROCK_EXTRACTION_MODEL_ID` + `BEDROCK_AGENT_MODEL_ID` 两个示例条目和说明注释。
  - `.streamlit/secrets.toml` 同步加两条（本地调试用，本身 gitignored）。
  - `scripts/README.md` `Required environment` 段加 `Optional — Bedrock dual-model split` 区段。
- 验证：
  - `python -c "from core.bedrock import EXTRACTION_MODEL_ID, MODEL_ID, get_extraction_model_id; ..."` → 输出 `amazon.nova-pro-v1:0`。
  - `from agentcore_deploy.agent import EXTRACTION_MODEL_ID, AGENT_MODEL_ID, get_model_id, get_extraction_model_id, invoke_llm_text, invoke_llm_extraction` → 全部存在；`get_model_id() == "deepseek.v3.2"` / `get_extraction_model_id() == "amazon.nova-pro-v1:0"`。
  - `from agentcore_deploy.main import _get_model_id, _get_extraction_model_id, _get_llm_invoke, _get_extraction_llm_invoke` → 全部就绪。
  - `agentcore_deploy.chat_agent` 重新 import 通过；`_model_identity_answer` 在 context 缺失时回退到 `deepseek.v3.2` / `amazon.nova-pro-v1:0` 文案。
- 风险与注意：
  - `core/bedrock.py:invoke_with_schema` 用 Bedrock Converse 的 `toolChoice.tool` 强制结构化输出，Nova Pro 在该路径下需账户开通对应 inference profile；如 Bedrock 报 `ValidationException`，把 `BEDROCK_EXTRACTION_MODEL_ID` 改回 `anthropic.claude-opus-4-7` 即可即时回滚。
  - DeepSeek V3.2 目前 modelId 字符串按用户给定 `deepseek.v3.2` 写入；若实际需要带版本/区域前缀（如 `us.deepseek.v3-2-v1:0`），改 `BEDROCK_AGENT_MODEL_ID` 一行即可。
- 提交：`df8179f`

### 31) 提取质量修复：bullet 拆分 / 单桶退化 / dashboard 关键词 / Item 1A 切片 / CIK 校验
- 背景：基于对 5 份新结构 risks JSON（Apple/Microsoft/Chevron/Boeing/Walmart）的真实采样，发现提取层有 6 个共性问题（详见 `EXTRACTION_FIX_PLAN.md`）。本次代码改动覆盖 P1-P6，并为 P0（CIK 误标）准备好排查脚本与 pipeline 防线；S3 数据本身的处理由后续手动操作完成。
- `core/extractor.py`（P1+P2+P6+P3）：
  - LLM prompt 新增"Bullet-list handling (CRITICAL)" 段落，明确禁止把 bullet 当独立 sub_risk、禁止把 bullet 行当 category 名。
  - 新增 `_starts_with_bullet` / `_strip_bullet_prefix` / `_is_continuation_title` / `_category_looks_like_bullet` / `_is_generic_category_name` 5 个 helper；`_clean_and_dedupe_ai_risk_blocks` 把 bullet/lowercase/逗号续行的 sub_risk 合并到上一条，把残留 bullet 前缀剥掉。
  - 新增 `_consolidate_polluted_blocks`：category 名是 bullet line 的 block，把它的 sub_risks 移交给第一个非污染 block（或 fallback 到 "General Risks"）。
  - 新增 `_consolidate_small_generic_blocks`：小型 generic 名 block（如 MS 那 2 条挂在 "Risk Factors" 下的零碎条目）合并到第一个 specific block。
  - 新增 `_looks_like_skewed_or_polluted` 加宽二次分类 trigger：除原 single-bucket 外，最大 block 占比 ≥60%、Walmart 模式（≥50% 且名 generic）、任意 category 名是 bullet line、≥20 sub_risks 但 category 名 ≤3 词都会触发 LLM re-cluster。
  - 新增 `SectionTooShort` 异常 + `_ITEM1A_MIN_CHARS=5000` 下界；`locate_item1a` 重写为对每层 fallback（edgartools / sec-parser / BS4-regex）打印 stderr 字符数诊断；< 5000 字符视为软失败、跳到下一层；全部 < 5000 时返回最长候选作 last resort。
- `agentcore_deploy/main.py`（P4+P5）：
  - `_RISK_CATEGORY_KEYWORDS` 补 60+ 词条：Tech 加 `unauthorized access` / `digital platform` / `technology` / `data security` 等；Operations 加 `product safety/quality`、`safety of products`、`product recall`；Legal 加 `regulatory requirement`；ESG 加 `emission` / `carbon`；People 加 `labor union` / `work stoppage`；Strategy 加 `customer demand` 等。
  - 新增 `_RISK_CATEGORY_TIEBREAKERS` + `_apply_category_tiebreakers`：cyber 优先 Legal、supplier 优先 People、climate 优先 Legal 等 7 条 tie-breaker 规则；命中时强制让 winner 严格大于 loser，避免按字母序的错命中。
  - `_normalize_risk_category` 同时跟踪 `max_weights`：纯 weight=1 凑出来的"高分"会被降到 score=1，强制走 LLM fallback。
  - LLM fallback 阈值从 `score < 3` 收紧到 `score < 2`（3 处调用点同步），让强匹配直接命中、弱匹配交给 LLM。
  - 本地 13 个 sample title 测试 0 失败（涵盖 Apple/Boeing/Walmart 计划列出的所有错例 + cyber/supplier/safety/inflation 等 regression 用例）。
- `scripts/extraction_pipeline.py`（P0）：
  - 新增 `extract_cik_from_html` / `verify_cik`：从 HTML 头 64KB 内提 inline XBRL `dei:EntityCentralIndexKey`（兼容 ix:nonNumeric / 裸 EntityCentralIndexKey / `CIK 0000xxxx` 几种写法）；`extract_risks_for_html` 新增可选 `expected_cik` 参数，CIK 不一致时直接拒绝抽取并返回 `cik_mismatch:` 错误。
- `scripts/migrate_s3_layout.py`（P0）：
  - 新增 `--verify-cik` 选项；启用时迁移每条 record 前先比对 inline XBRL CIK 与 `industry_mapping.COMPANIES[ticker].cik`，不一致直接 FAIL（不写入 S3、不调用 Bedrock），防止重新污染新 layout。
- 新增 `scripts/audit_legacy_cik.py`（P0）：扫 `10k_filings/<industry>/<dir>/<year>_10K.html` 全量，输出 `cik_mismatch_report.json`；区分 matched / mismatched / missing_cik_in_html / missing_expected_cik / skipped 五类，仅当存在 mismatched 时退出码 1。
- 新增 `scripts/diagnose_item1a_locator.py`（P3）：默认对计划列出的 6 条切片失败 record（Chevron 2021/2022、Exxon 2021、Kroger 2023/2024/2025）跑 edgartools / sec-parser / BS4-regex 三层各自字符数 + 前 500 字 head；可用 `--industry/--company/--year` 任意组合扩展范围。
- 验证：所有改动文件 `python -c "import …"` 全部通过；分类器本地 13 个 sample title 0 失败；helper 单元行为（bullet 检测、polluted block 整合、skewed/single-bucket 触发判断）通过桌面级冒烟脚本；CIK 提取对 4 种 XBRL 输入与 4 种 verify_cik 场景全部正确。
- 后续待执行（不在本次代码 commit 内）：跑 `audit_legacy_cik.py` 看 cik_mismatch_report.json、跑 `diagnose_item1a_locator.py` 拿 Chevron/Exxon/Kroger 真根因、用 `migrate_s3_layout.py --write --force-reextract` 重抽全部 34 record。
- 提交：`b554a05`

### 30) 后端双轨读：USE_NEW_S3_LAYOUT 环境变量切换 10k_filings/ 新结构
- `agentcore_deploy/main.py` 新增 4 个常量：`NEW_FILINGS_PREFIX = "10k_filings"`、`NEW_INDEX_KEY = "10k_filings/index.json"`、`USE_NEW_LAYOUT = os.getenv("USE_NEW_S3_LAYOUT","0") == "1"`、`NEW_RECORD_ID_RE`（解析合成 `<dir>_<year>_10K` 的正则）。
- 新增辅助函数 `_load_new_layout_index_doc` / `_flatten_new_layout_index` / `_new_layout_record_id` / `_new_layout_keys_for_record_id` / `_new_layout_company_dir` / `_upsert_new_layout_index`：把新分层 index.json 与扁平 record list 互转，所有读 / 写都对齐 `_INDEX_CACHE / _RESULT_CACHE / _TICKER_MAP_CACHE` 失效语义。
- `_load_index`：当 `USE_NEW_LAYOUT=1` 时优先从 `10k_filings/index.json` flatten；新 index 缺席时软回退到旧 `filing_records_index.json`，避免切换瞬间 API 返回空列表。
- `_load_result`：合成 record_id（形如 `Apple_AAPL_2024_10K`）走 `10k_filings/<industry>/<company_dir>/<year>_10K_risks.json`，旧 record_id 仍走 `risk_analysis_results/`，在过渡期两套数据可以共存。
- `_load_company_ticker_map`：在新 layout 下从 index.json 反构 `company → ticker`，不再要求维护一份独立的 `company_ticker_map.json`；旧文件作为 fallback。
- `_invalidate_runtime_caches`：增加 `NEW_INDEX_KEY` 与 `10k_filings/` 前缀的失效路径；任意分层文件写入都会清 `_RESULT_CACHE / _RECORDS_LIST_CACHE / _DASHBOARD_SUMMARY_CACHE` 与 ticker 缓存，dashboard 不会留陈旧数据。
- `_add_record`：当 `USE_NEW_LAYOUT=1` 且 ext 是 html 时，新写入分流到 `10k_filings/<industry>/<company_dir>/<year>_10K.{html,json}` 并 mutating-update `10k_filings/index.json`，返回的合成 `record_id` 与读路径自洽；PDF 仍走旧路径不动。
- 行为变化：默认 `USE_NEW_S3_LAYOUT` 未设置 → 全走旧路径，零行为变化；只有显式设 `USE_NEW_S3_LAYOUT=1` 才切到新结构。回滚只需删除该环境变量重启即可。
- 验证：在 mock `_read_s3_bytes` 返回伪造的 `10k_filings/index.json` + 单条 risks JSON 时，`_load_index` 输出 2 条合成 record（`Apple_AAPL_2024_10K` / `Chevron_CVX_2023_10K`），`_load_result("Apple_AAPL_2024_10K")` 命中新分层 json_key，旧 rid `Apple_2024_10-K_d69b` 自动回退到 `risk_analysis_results/`，ticker map 反构出 `{"Apple":"AAPL","Chevron":"CVX"}`；关掉 flag 后 `_load_index` 重新走 legacy `filing_records_index.json` 路径。
- 提交：`208de25`

### 29) S3 重组工具集：Part 1 迁移脚本 + Part 2 批量摄入脚本
- 新增 `scripts/industry_mapping.py`：硬编码 11 个行业 × ~80 家公司的映射（GICS 2024-09），统一目录命名（`<DisplayName>_<TICKER>`），并修正历史数据的拼写错误（`ConocoPhilllips → ConocoPhillips_COP`、`lockheed → Lockheed_Martin_LMT`、`Exxon_Mobil → ExxonMobil_XOM`、`Motorola_Solutions_Inc → Motorola_Solutions_MSI`）。BRK.B 因 SEC ticker map 不区分 A/B 类，硬编码 CIK `0001067983`；PXD 因 2024-05 被 Exxon 收购退市，写入 `last_year=2023` 自动封顶。
- 新增 `scripts/extraction_pipeline.py`：复用 `agentcore_deploy/main._manual_extract_result` 与 `_generate_agent_priority_report`，确保迁移 / 批量摄入与 `/api/upload/*` 走完全相同的提取 + 评分管线，落盘 schema 完全一致。
- 新增 `scripts/migrate_s3_layout.py`（S3_PLAN.md Part 1）：扫 `s3://<bucket>/10k_html_datasets/*.html` 共 42 个 legacy 文件，按文件名 regex `^(.+)_(\d{4})_10-K_[0-9a-f]+\.html$` 解析；Airbus 默认跳过；重抽取并落到 `10k_filings/<industry>/<company_dir>/<year>_10K.{html,json}`；每 5 条 record checkpoint flush `10k_filings/index.json`；旧路径**永不删除**。`--dry-run` 默认开（可安全本地验证），需要 `--write` 才动 S3 + Bedrock。
- 新增 `scripts/bulk_ingest_targets.py` + `scripts/bulk_ingest.py`（Part 2）：去重后 ~87 个 ticker 的 SEC EDGAR 自动拉取 + 抽取 + 优先级评分 + 增量写入。每条 (公司,年份) 启动前检查 index + S3 双重命中跳过；单公司连续失败 N 次自动短路；运行 report 同时落本地 + `s3://<bucket>/10k_filings/_ingest_reports/<ISO>.json`。
- 新增 `scripts/README.md`：完整使用文档（环境变量、CLI 用法、Railway 切流量步骤）。
- `.gitignore` 加 `scripts/*.report.json` 屏蔽 dry-run 日志。
- 验证：本地 `S3_BUCKET=10k-risk-alert-app python3 scripts/migrate_s3_layout.py --dry-run` 输出 `ok=40 skipped=2 failed=0`（Airbus 2 个 SKIP，其余 40 个映射正确）；`bulk_ingest --dry-run --start-year 2023 --end-year 2024` 输出 `ok=173`（87 ticker × 2 年 - PXD 仅 2023）。
- 提交：`0691992`

### 28) RPI 优化 P2 前端：未评分显示 "—" 而不是 RPI=0
- `frontend/src/pages/DashboardPage.jsx:priorityHeatColor` 增加 `null/undefined` 浅灰分支（`#e2e8f0`），与"无风险数据"的 `#f1f5f9` 区分。
- 热力图 cell 渲染：`cell.rpi` 不再用 `safeNumber` 强制转 0；`rpi == null` 时数字显示 "—"，hover `title` 提示 "Risk scoring unavailable for this filing"。
- "Average RPI" 与 hover popup 的 RPI 字段：`null/undefined` 时分别显示 "—" 和 "Not scored"，不再渲染伪造的 0.0。
- 帮助说明文字加一句解释 "—" 含义。
- 验证：`npm --prefix frontend run build` 通过；评分失败 record 现在前端显示灰底 "—"，全 Low（RPI=0）继续显示绿底 "0"。
- 提交：`5334d23`

### 27) RPI 优化 P2 后端 + P3：评分失败 RPI 显式 null，全 Low 计入平均
- `agentcore_deploy/main.py:_risk_pressure_index` 改为三态返回 `Optional[float]`：`None` = 评分失败/缺失（前端显示"—"），`0.0` = 全 Low 或无风险（合法低分），`>0.0` = 正常分数；新增 `scoring_status` keyword-only 入参，仅当 status 是 `"failed"` 或 `"missing"` 时返回 None。
- `_extract_priority_counts_from_result` 新增 `scoring_status` 输出字段：优先读 `agent_report.scoring_status`（commit 1 注入），不存在但 `priority_matrix` 存在时回退 `"ok"`（保护历史 record），`agent_report` 完全缺失则 `"missing"`。
- `_dashboard_summary` 把 status 透传给 `_risk_pressure_index`；`if rpi > 0` 改为 `if rpi is not None`（同时修复 P3 — 全 Low（RPI=0）合法 record 重新计入 `avg_rpi`）；heatmap cell 的 `rpi` 字段在评分失败时为 JSON `null`，新增 `scoring_status` 字段；公司排序中"未评分"公司用 `-1.0` 落到列表底部。
- 行为变化（用户可感知）：dashboard 上历史评分失败的 record 不再显示伪造的 RPI=50；全 Low record 现在按 0 参与 `avg_rpi` 计算，所以 `avg_rpi` 数字会比修复前略低（之前的 bug 把 0 排除在分母外了）。
- 自检：构造 `failed/missing/ok` 三种 status 经 `_risk_pressure_index` 输出符合预期；新 / 旧 / 空 record 经 `_extract_priority_counts_from_result` 的 status 路径全部正确；源码扫描确认 `if rpi > 0` 已被替换。
- 提交：`eaab7cc`

### 26) RPI 优化 P0+P1：LLM 打分加 Python 校验 + 分批评分
- `agentcore_deploy/agent.py` 新增 `PRIORITY_HIGH_THRESHOLD=7.0` / `PRIORITY_MEDIUM_THRESHOLD=4.0` / `PRIORITY_DIM_WEIGHTS=(0.4,0.35,0.25)` / `_PRIORITY_BATCH_SIZE=40` 四个常量，以及 `_clamp_int_1_10` / `_compute_score_from_dims` / `_priority_from_score` 三个辅助函数；prompt 仍向 LLM 索要三维（financial_impact / likelihood / urgency），但 score 与 priority 改由 Python 在 `_prioritize_risks_impl` 内**重算**——LLM 自相矛盾的 `{score:2.0, priority:"High"}` 不再被接受。
- `_prioritize_risks_impl` 重写为分批：超过 40 条风险因子时按 `⌈N/40⌉` 个 batch 串行调用，所有条目都会被评分；单 batch 失败仅影响该批，其他 batch 不受牵连；`agent_steps` 多一行 `Tool 3a: scored X/Y risks across N batches` 便于排查。
- `_build_priority_lists` 返回签名从 `(high, medium, low)` 改为 `(high, medium, low, unscored)`；`priority is None` 的条目落到新 `unscored` 桶而不是默认 Medium。`_generate_agent_report_impl` / `_fallback_report` / `_normalize_report` 同步把 `priority_matrix.unscored.{count, top}` 写进输出，并新增顶层 `scoring_status ∈ {"ok", "partial", "failed", "missing"}` 字段（`_fallback_report` 直接给 `"failed"`）。
- 行为变化：评分失败时不再静默返回 `Medium=5.0` 制造看似正常的 RPI=50；该信号会被 P2 的 main.py / 前端识别成"未评分"。本次 commit 只动 agent.py，main.py / 前端的下游消费在 commit 2 / 3 完成。
- 自检：脚本模拟 LLM 自相矛盾返回（`P0`）、60 条 → 2 个 batch（`P1`）、Bedrock 全失败（`P2-failed`）、半数 batch 失败（`P2-partial`）四个场景，priority/score/scoring_status/unscored 均符合预期。
- 提交：`e75d965`

### 25) 风险分类优化：提取多桶约束 + Dashboard 9 类映射
- 提交：`65d2692`
- `core/extractor.py` 修复 Item 1 overview 回退路径：当 edgartools/sec-parser 已经切出 Item 1 正文时，不再把切片文本重新送回 raw filing 正则查找，避免 Apple 这类文件返回 `"(Could not extract Item 1 overview.)"`。  
- Item 1A Bedrock schema prompt 增加“必须按 3-8 个主题类别组织”的明确约束，并新增单桶 `"Risk Factors"` 退化检测；若 LLM 仍返回一个大桶，会触发二次 re-cluster pass。  
- `agentcore_deploy/main.py` 重写 dashboard 9 类关键词权重，移除 `risk factors` / `business risk` / `industry` / 裸 `market` 等宽泛词，弱命中时交给 LLM fallback；无 Bedrock 凭证时才回落到 `General & Other`。  
- 新写入的每条 sub risk 都会保留 `original_category`，并额外落盘 `dashboard_category`，dashboard / compare 读数据时优先使用后端字段，前端不再维护另一套关键词分类器。  
- 新增 `scripts/reclassify_existing_records.py` 用于给历史 S3 result JSON 补写 `dashboard_category/original_category`；默认 dry-run，真实写回需显式 `--write`，且默认拒绝在无 Bedrock 凭证环境写回。  
- 验证：`py_compile`、`npm --prefix frontend run build`、本地后端 `/health` 200 均通过；AAPL/TSLA/PFE/LMT 2024 与 JPM 最新 10-K 的 Item 1 overview 均可抽出 ≥200 字正文；本地分类样本覆盖 9 个 dashboard 桶且不再被 `"Risk Factors"` 强行归入 Strategy & Market。  
