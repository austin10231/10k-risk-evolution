"""Global i18n helpers for EN / ZH language switching."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


_LANG_KEY = "ui_lang"

_NAV_ZH = {
    "DATA": "数据",
    "ANALYSIS": "分析",
    "INTELLIGENCE": "智能",
    "Home": "首页",
    "Upload": "上传",
    "Dashboard": "仪表盘",
    "Stock": "股票",
    "News": "新闻",
    "Library": "资料库",
    "Compare": "对比",
    "Tables": "表格",
    "Agent": "智能体",
}

# Phrase-level replacements only (avoid single-word replacements that may alter article text).
_DOM_ZH_MAP = {
    "Choose where to begin across 6 core modules": "从 6 个核心模块开始",
    "Quick Start": "快速开始",
    "How It Works": "工作流程",
    "Current Features": "当前功能",
    "Future Releases": "未来优化方向",
    "What's available today": "当前可用能力",
    "Next optimization priorities": "下一阶段优化重点",
    "Keep the same 6-step flow, now with market and news linkage": "保持 6 步结构，并加入市场与新闻联动",
    "Open Upload": "进入上传",
    "Open Records": "进入记录",
    "Open Compare": "进入对比",
    "Open Tables": "进入表格",
    "Open Agent": "进入智能体",
    "Open News": "进入新闻",
    "Dashboard": "仪表盘",
    "Stock": "股票",
    "Upload & Auto-Fetch": "上传与自动拉取",
    "Compare Risks": "风险对比",
    "Financial Tables": "财务表格",
    "AI Risk Agent": "AI 风险智能体",
    "Dashboard + Stock": "仪表盘 + 股票",
    "News Intelligence": "新闻智能",
    "Ingest new filings and manage saved Records in one place.": "在一个入口完成新文件摄取与历史记录管理。",
    "Run year-over-year or cross-company comparisons to detect structural risk changes.": "支持跨年与跨公司对比，识别结构化风险变化。",
    "Extract 5 core statements via Textract and store JSON/CSV for downstream analysis.": "通过 Textract 提取 5 大核心报表并保存 JSON/CSV。",
    "Generate priority scores, key findings, recommendations, and full analyst-ready reports.": "生成优先级评分、关键发现、建议与完整分析报告。",
    "Monitor portfolio risk and market movement together in one linked workflow.": "在统一流程中联动查看组合风险与市场波动。",
    "Track recent company headlines with pressure scoring and risk-linked summaries.": "追踪公司近期新闻，并输出压力评分与风险关联摘要。",
    "Filings": "文件摄取",
    "Ingest new filings and manage existing records in one place": "在一个页面完成新文件摄取与记录管理",
    "New Ingestion": "新建摄取",
    "Records": "记录",
    "Manual Upload": "手动上传",
    "Auto Fetch from SEC EDGAR": "从 SEC EDGAR 自动拉取",
    "Company": "公司",
    "Year": "年份",
    "Industry": "行业",
    "Ticker": "股票代码",
    "Filing Type": "文件类型",
    "Extract & Save": "提取并保存",
    "Risk Heatmap": "风险热力图",
    "Risk Category Ranking": "风险类别排行",
    "Risk vs Return (30D)": "风险 vs 收益（30天）",
    "Market Performance": "市场表现",
    "Run Agent": "运行智能体",
    "Include YoY comparison": "包含同比对比",
    "Your report will appear here": "报告将在此显示",
    "Your query": "你的问题",
    "No risk analysis available — go to Analyze to add": "暂无风险分析数据，请先到 Analyze 生成",
    "Refresh": "刷新",
    "Time Window": "时间窗口",
    "Latest Headline": "最新新闻时间",
    "Articles Loaded": "新闻条数",
    "Avg News Pressure": "平均新闻压力",
    "Open Source": "打开原文",
    "Load": "加载",
    "Delete": "删除",
    "Language": "语言",
    "Current Configuration": "当前配置",
    "Edit": "编辑",
    "Apply": "应用",
    "Clear": "清空",
    "Run Compare": "运行对比",
    "Extract Tables": "提取表格",
    "Auto Fetch + Extract Tables": "自动拉取并提取表格",
    "Stock Ticker (manual)": "股票代码（手动）",
    "Company Name": "公司名称",
    "Filing Year": "申报年份",
    "Risk Categories": "风险类别",
    "Risk Items": "风险条目",
    "Business Overview": "公司概览",
    "No extracted financial tables found for this filing.": "该条记录暂无已提取的财务表格。",
    "Extract Financial Tables": "提取财务表格",
    "No risk analysis available for this selection yet.": "当前选择暂无风险分析结果。",
    "No matching records found.": "未找到匹配记录。",
    "Download Full JSON": "下载完整 JSON",
    "Download Full Agent Report (JSON)": "下载完整 Agent 报告（JSON）",
    "From filing ingestion to risk + market + news intelligence in 6 steps": "从文件摄取到风险、市场、新闻智能的 6 步流程",
    "From ingestion to monitoring in 6 steps": "从摄取到监控的 6 步流程",
    "Step": "步骤",
    "Open Dashboard": "打开仪表盘",
    "Open Stock": "打开股票",
    "Open Library": "打开资料库",
    "Start Analyzing": "开始分析",
    "Ingest Filing": "文件摄取",
    "Extract Risks": "风险提取",
    "Extract Tables": "表格提取",
    "Compare Changes": "变化对比",
    "Run Agent": "运行智能体",
    "Link Market + News": "联动市场与新闻",
    "Current modules are feature-complete for the end-to-end workflow. Future iterations focus on improving accuracy, cross-signal relevance, and interaction speed as company coverage expands.": "当前模块已覆盖端到端流程。后续优化将聚焦准确率、跨信号关联性以及大规模覆盖下的交互速度。",
    "End-to-end 10-K workflow": "10-K 端到端工作流",
    "Dual risk extraction modes": "双模式风险提取",
    "Financial table pipeline": "财务表格流水线",
    "Structured risk storage and reusable records": "结构化风险存储与复用记录",
    "Cross-year and cross-company change detection": "跨年与跨公司变化检测",
    "AI agent scoring and recommendations": "AI 智能体评分与建议",
    "Risk monitoring dashboard": "风险监控仪表盘",
    "Dedicated stock analytics page": "独立股票分析页面",
    "News intelligence module": "新闻智能模块",
    "Global configuration sync across core workflows": "核心流程全局配置同步",
    "Cloud persistence and analyst export views": "云端持久化与分析导出视图",
    "Higher extraction consistency and confidence calibration": "更高提取一致性与置信度校准",
    "Stronger risk-market-news linkage scoring": "更强风险-市场-新闻联动评分",
    "Lower page latency via warm cache and lazy loading": "通过热缓存与懒加载降低页面延迟",
    "Better evidence ranking and duplicate-news suppression": "更优证据排序与重复新闻抑制",
    "More explainable agent reasoning trace for analysts": "面向分析师的可解释推理链优化",
    "Track recent company headlines with optional risk-linked AI summary": "追踪近期公司新闻，并可生成风险关联 AI 摘要",
    "Marketaux API token not configured. Please set `MARKETAUX_API_TOKEN` in `.streamlit/secrets.toml`.": "未配置 Marketaux API Token。请在 `.streamlit/secrets.toml` 中设置 `MARKETAUX_API_TOKEN`。",
    "No analyzed companies found yet. You can still query by ticker below.": "当前还没有已分析公司，你仍可在下方按股票代码查询。",
    "No strong negative-pressure headline found in current window.": "当前窗口未发现高负压新闻。",
    "No recent news found for this company/ticker in the selected window.": "在所选窗口内未找到该公司/代码相关新闻。",
    "Load More": "加载更多",
    "Generate AI Risk-Linked Summary": "生成 AI 风险关联摘要",
    "Risk Intelligence Agent": "风险智能体",
    "Ask questions in plain English — get a full prioritized risk report": "用自然语言提问，获取完整优先级风险报告",
    "Go to Upload": "前往上传",
    "Suggested Queries": "建议问题",
    "Please enter a query or select one from the left.": "请输入问题或从左侧选择一个。",
    "No high-priority risks identified.": "未识别到高优先级风险。",
    "No findings available.": "暂无关键发现。",
    "No recommendations available.": "暂无建议。",
    "No risk data available.": "暂无风险数据。",
    "AgentCore is not configured": "AgentCore 未配置",
    "Financial tables extracted and saved for": "财务表格已提取并保存：",
    "No core financial tables could be identified in this filing PDF.": "该 PDF 中未识别到核心财务表格。",
    "Could not auto-download 10-K PDF from SEC EDGAR.": "无法从 SEC EDGAR 自动下载 10-K PDF。",
    "Extract Tables (Manual PDF)": "提取表格（手动 PDF）",
    "Auto Fetch + Extract Tables": "自动拉取并提取表格",
    "Please upload a PDF file.": "请上传 PDF 文件。",
    "Stock": "股票",
    "Search market data and overlay your system risk signals": "搜索市场数据并叠加系统风险信号",
    "Search Company or Ticker": "搜索公司或股票代码",
    "Select Company": "选择公司",
    "Time Range": "时间范围",
    "Close Price": "收盘价",
    "Trading Volume": "成交量",
    "No matching companies found. Try another keyword or ticker.": "未找到匹配公司，请尝试其他关键词或代码。",
    "Not enough data points in the selected range.": "所选区间数据点不足。",
    "No risk analysis available — go to Analyze to add": "暂无风险分析数据，请先到 Analyze 生成",
    "Detect risk changes year-over-year or between companies": "识别跨年或跨公司的风险变化",
    "Year-over-Year": "跨年对比",
    "Cross-Company": "跨公司对比",
    "Latest Year": "最新年份",
    "Prior Year(s)": "历史年份",
    "Need at least 2 years for": "至少需要 2 年数据：",
    "No prior year available.": "暂无可用历史年份。",
    "Select at least one prior year.": "请至少选择一个历史年份。",
    "Could not find one or both selected records.": "未找到一个或两个目标记录。",
    "Could not load result JSON for one or both records.": "未能加载一个或两个记录的结果 JSON。",
    "No differing risks detected between the two selections.": "两个选择之间未检测到差异风险。",
    "AI Change Analysis": "AI 变化分析",
    "Risk heatmap and category ranking across all filings": "跨全部文件的风险热力图与类别排行",
    "Industry Group": "行业分组",
    "Risk Overview": "风险总览",
    "Category Analysis": "类别分析",
    "Market Performance is paused to keep Dashboard navigation fast.": "为保证 Dashboard 切换速度，市场表现模块默认暂停。",
    "Enable Market Performance Data": "启用市场表现数据",
    "No filings match the selected industry filter.": "所选行业下没有匹配文件。",
    "No Agent heatmap data available for the selected scope.": "当前范围暂无 Agent 热力图数据。",
    "Market-linked charts are paused for faster page loading.": "为提升页面速度，市场联动图表默认暂停。",
    "Load market-linked charts": "加载市场联动图表",
    "No Risk vs Return points available yet. Add ticker mappings and run Agent reports first.": "暂无风险-收益散点，请先配置代码并运行 Agent。",
    "No risk category data available for the selected industry.": "所选行业暂无风险类别数据。",
    "No valid risk categories to display after filtering.": "过滤后无可展示的有效风险类别。",
    "Show all categories": "显示全部类别",
    "Add / Update": "添加 / 更新",
    "Remove Selected": "移除所选",
    "No companies available in this industry scope.": "当前行业范围暂无公司。",
    "No tickers added yet for the selected industry scope.": "当前行业范围尚未添加股票代码。",
    "No tracked tickers match the current filter.": "当前筛选条件下没有匹配的跟踪代码。",
    "Please enter a valid ticker symbol first.": "请先输入有效的股票代码。",
    "Save": "保存",
    "Missing ticker mapping:": "缺少代码映射：",
    "Market data warnings": "市场数据警告",
    "Overall Risk": "综合风险",
    "Priority Breakdown": "优先级分布",
    "Risk Themes": "风险主题",
    "Top Risks": "高优先级风险",
    "Executive Summary": "执行摘要",
    "Key Findings": "关键发现",
    "Recommendations": "建议",
    "Full List": "完整列表",
    "Risk Category Ranking": "风险类别排行",
    "Most frequent risk categories across": "最常见风险类别（范围：",
    "Run AI Summarize": "运行 AI 摘要",
    "Open Tables Page": "打开表格页面",
    "No records match the current filters.": "当前筛选条件下没有匹配记录。",
    "Browse and manage your uploaded 10-K filings": "浏览并管理已上传的 10-K 文件",
    "New Filing": "新建文件",
    "Go to Upload": "前往上传",
    "No records yet. Switch to New Analysis to upload a filing.": "暂无记录，请切换到“新建分析”上传文件。",
}

_DOM_EN_EXTRA_MAP = {
    # Existing hardcoded Chinese strings in codebase (not emitted via English source text)
    "当前对比未检测到风险评级升级，或缺少足够的事件后 20 天股价数据。":
        "No risk-upgrade event detected in this comparison, or insufficient 20-day post-event price data.",
    "请输入有效 ticker 后再保存。": "Please enter a valid ticker before saving.",
}


def _build_en_map():
    reverse = {}
    for en_text, zh_text in _DOM_ZH_MAP.items():
        if zh_text and zh_text not in reverse:
            reverse[zh_text] = en_text
    reverse.update(_DOM_EN_EXTRA_MAP)
    return reverse


_DOM_EN_MAP = _build_en_map()


def ensure_language_state() -> None:
    if _LANG_KEY not in st.session_state:
        st.session_state[_LANG_KEY] = "en"
    if st.session_state[_LANG_KEY] not in ("en", "zh"):
        st.session_state[_LANG_KEY] = "en"


def current_language() -> str:
    ensure_language_state()
    return st.session_state[_LANG_KEY]


def nav_text(text: str) -> str:
    if current_language() != "zh":
        return text
    return _NAV_ZH.get(text, text)


def render_language_switcher(key_prefix: str = "lang") -> None:
    ensure_language_state()
    cur = current_language()
    default_display = "EN" if cur == "en" else "中文"
    selected = st.segmented_control(
        "Language",
        options=["EN", "中文"],
        default=default_display,
        label_visibility="collapsed",
        key=f"{key_prefix}_switch",
    )
    if selected:
        new_lang = "en" if selected == "EN" else "zh"
        if new_lang != cur:
            st.session_state[_LANG_KEY] = new_lang
            st.rerun()


def inject_dom_translation() -> None:
    """Translate rendered UI text in-browser in both directions (EN<->ZH)."""
    lang = current_language()
    mapping = _DOM_ZH_MAP if lang == "zh" else _DOM_EN_MAP
    mapping_json = json.dumps(mapping, ensure_ascii=False)
    components.html(
        f"""
        <script>
        (function () {{
          const p = window.parent;
          const doc = p.document;
          const lang = {json.dumps(lang)};
          const map = {mapping_json};
          const keys = Object.keys(map).sort((a, b) => b.length - a.length);

          function translateText(text) {{
            let out = text;
            for (const k of keys) {{
              if (out.includes(k)) out = out.split(k).join(map[k]);
            }}
            return out;
          }}

          function shouldSkip(node) {{
            const el = node.parentElement;
            if (!el) return true;
            const tag = (el.tagName || '').toUpperCase();
            return ['SCRIPT', 'STYLE', 'TEXTAREA', 'PRE', 'CODE'].includes(tag);
          }}

          function translateUnder(root) {{
            if (!root) return;
            const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            let n;
            while ((n = walker.nextNode())) {{
              if (shouldSkip(n)) continue;
              const original = n.nodeValue || '';
              if (!original.trim()) continue;
              const translated = translateText(original);
              if (translated !== original) n.nodeValue = translated;
            }}
          }}

          function run() {{
            translateUnder(doc.body);
          }}

          if (p.__risklens_i18n_observer) {{
            p.__risklens_i18n_observer.disconnect();
          }}

          run();

          const obs = new MutationObserver((mutations) => {{
            for (const m of mutations) {{
              if (m.type === 'characterData' && m.target) {{
                const node = m.target;
                if (shouldSkip(node)) continue;
                const original = node.nodeValue || '';
                const translated = translateText(original);
                if (translated !== original) node.nodeValue = translated;
                continue;
              }}
              for (const added of m.addedNodes || []) {{
                if (added.nodeType === Node.TEXT_NODE) {{
                  if (shouldSkip(added)) continue;
                  const original = added.nodeValue || '';
                  const translated = translateText(original);
                  if (translated !== original) added.nodeValue = translated;
                }} else if (added.nodeType === Node.ELEMENT_NODE) {{
                  translateUnder(added);
                }}
              }}
            }}
          }});

          obs.observe(doc.body, {{ childList: true, subtree: true, characterData: true }});
          p.__risklens_i18n_observer = obs;
          p.__risklens_i18n_lang = lang;
        }})();
        </script>
        """,
        height=0,
        width=0,
    )
