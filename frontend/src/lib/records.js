export function flattenRisks(result) {
  if (!result || !Array.isArray(result.risks)) return []
  const out = []
  result.risks.forEach((block) => {
    const category = String(block?.category || 'Unknown').trim() || 'Unknown'
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    subs.forEach((sub) => {
      if (typeof sub === 'string') {
        const title = sub.trim()
        if (title) out.push({ category, title, labels: [] })
        return
      }
      const title = String(sub?.title || '').trim()
      if (!title) return
      const labels = Array.isArray(sub?.labels) ? sub.labels.filter(Boolean) : []
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
  return result.risks.map((block) => {
    const category = String(block?.category || 'Unknown').trim() || 'Unknown'
    const subs = Array.isArray(block?.sub_risks) ? block.sub_risks : []
    const titles = subs
      .map((sub) => (typeof sub === 'string' ? sub : sub?.title || ''))
      .map((t) => String(t || '').trim())
      .filter(Boolean)
    return { category, titles }
  })
}

