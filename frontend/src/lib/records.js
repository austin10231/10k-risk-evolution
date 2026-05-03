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
    const categoryRaw = String(block?.category || 'Unknown').trim() || 'Unknown'
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      if (typeof sub === 'string') {
        const title = sub.trim()
        if (title) {
          const category = pickCategory(categoryRaw, null)
          out.push({ category, dashboard_category: category, original_category: categoryRaw, title, labels: [] })
        }
        return
      }
      const title = String(sub?.title || '').trim()
      if (!title) return
      const labels = Array.isArray(sub?.labels) ? sub.labels.filter(Boolean) : []
      const category = pickCategory(categoryRaw, sub)
      out.push({
        category,
        dashboard_category: category,
        original_category: String(sub?.original_category || categoryRaw || '').trim(),
        title,
        labels,
      })
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
      const category = pickCategory(categoryRaw, typeof sub === 'object' ? sub : null)
      if (!grouped.has(category)) grouped.set(category, [])
      grouped.get(category).push(title)
    })
  })
  return Array.from(grouped.entries()).map(([category, titles]) => ({ category, titles }))
}
