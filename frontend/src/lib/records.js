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

const RISK_CATEGORY_KEYWORDS = {
  'Capital Markets': [
    'common stock', 'stockholder', 'shareholder', 'market price', 'securities', 'dividend', 'equity offering', 'dilution', 'ownership of our stock', 'capital market',
  ],
  'Financial & Liquidity': [
    'financial risk', 'financial condition', 'financial statements', 'liquidity', 'cash flow', 'debt', 'credit', 'interest rate', 'refinancing', 'impairment', 'profitability', 'revenue', 'inflation', 'foreign exchange', 'currency', 'solvency', 'capital resources',
  ],
  'Legal & Regulatory': [
    'legal', 'regulatory', 'regulation', 'compliance', 'litigation', 'laws', 'government', 'policy', 'policies', 'antitrust', 'sanction', 'fines', 'bribery', 'corruption', 'intellectual property', 'tax-related', 'reit', 'status as a reit',
  ],
  'Technology & Cybersecurity': [
    'technology', 'cyber', 'cybersecurity', 'information security', 'data breach', 'data privacy', 'privacy', 'it system', 'system outage', 'software', 'cloud', 'artificial intelligence', 'machine learning', 'generative ai', 'digital', 'ransomware',
  ],
  'Operations & Supply Chain': [
    'operations', 'operational', 'business operations', 'supply chain', 'supplier', 'procurement', 'manufacturing', 'production', 'logistics', 'distribution', 'inventory', 'quality', 'safety', 'business continuity', 'disruption',
  ],
  'People & Governance': [
    'employment', 'workforce', 'labor', 'union', 'human capital', 'talent', 'hiring', 'retention', 'management', 'leadership', 'executive', 'board', 'governance', 'internal control', 'culture',
  ],
  'ESG & Sustainability': [
    'esg', 'environment', 'environmental', 'sustainability', 'climate', 'climate change', 'carbon', 'emissions', 'greenhouse gas', 'social responsibility',
  ],
  'Strategy & Market': [
    'strategy', 'strategic', 'market', 'industry', 'competition', 'competitive', 'customer', 'demand', 'pricing', 'growth', 'reputation', 'brand', 'macro', 'geopolitical', 'business risk', 'general risk', 'risk factors', 'risks specific to our company',
  ],
}

export function normalizeRiskCategory(category, title = '', labels = []) {
  const catText = String(category || '').trim()
  const titleText = String(title || '').trim()
  const labelText = (Array.isArray(labels) ? labels : []).map((x) => String(x || '').trim()).filter(Boolean).join(' ')
  const fullText = `${catText} ${titleText} ${labelText}`.trim().toLowerCase()
  if (!fullText) return 'General & Other'

  const scores = Object.fromEntries(FIXED_RISK_CATEGORIES.map((cat) => [cat, 0]))
  const lowerCat = catText.toLowerCase()

  Object.entries(RISK_CATEGORY_KEYWORDS).forEach(([target, phrases]) => {
    phrases.forEach((phraseRaw) => {
      const phrase = String(phraseRaw || '').toLowerCase()
      if (!phrase) return
      if (fullText.includes(phrase)) scores[target] += 1
      if (lowerCat.includes(phrase)) scores[target] += 2
    })
  })

  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const [bestCategory, bestScore] = ranked[0] || ['General & Other', 0]
  if (bestScore > 0) return bestCategory
  if (catText || titleText) return 'Strategy & Market'
  return 'General & Other'
}

export function flattenRisks(result) {
  if (!result || !Array.isArray(result.risks)) return []
  const out = []
  result.risks.forEach((block) => {
    const categoryRaw = String(block?.category || 'Unknown').trim() || 'Unknown'
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      if (typeof sub === 'string') {
        const title = sub.trim()
        const category = normalizeRiskCategory(categoryRaw, title, [])
        if (title) out.push({ category, title, labels: [] })
        return
      }
      const title = String(sub?.title || '').trim()
      if (!title) return
      const labels = Array.isArray(sub?.labels) ? sub.labels.filter(Boolean) : []
      const category = normalizeRiskCategory(categoryRaw, title, labels)
      out.push({ category, title, labels })
    })
  })
  return out
}

export function riskItemCount(result) {
  return flattenRisks(result).length
}

export function riskCategoryCount(result) {
  if (!result || !Array.isArray(result.risks)) return 0
  return result.risks.length
}

export function companyOverview(result) {
  if (!result || typeof result !== 'object') return {}
  return result.company_overview && typeof result.company_overview === 'object' ? result.company_overview : {}
}

export function groupedRiskTitles(result) {
  if (!result || !Array.isArray(result.risks)) return []
  const grouped = new Map()
  result.risks.forEach((block) => {
    const categoryRaw = String(block?.category || 'Unknown').trim() || 'Unknown'
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      const title = String(typeof sub === 'string' ? sub : sub?.title || '').trim()
      if (!title) return
      const labels = typeof sub === 'string' ? [] : (Array.isArray(sub?.labels) ? sub.labels.filter(Boolean) : [])
      const category = normalizeRiskCategory(categoryRaw, title, labels)
      if (!grouped.has(category)) grouped.set(category, [])
      grouped.get(category).push(title)
    })
  })
  return Array.from(grouped.entries()).map(([category, titles]) => ({ category, titles }))
}
