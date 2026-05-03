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
