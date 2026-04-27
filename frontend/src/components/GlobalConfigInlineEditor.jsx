import React, { useEffect, useState } from 'react'
import { useGlobalConfig } from '../lib/globalConfig'

const YEARS = Array.from({ length: 16 }, (_, i) => String(2025 - i))
const INDUSTRIES = [
  'Technology',
  'Healthcare',
  'Financials',
  'Energy',
  'Consumer Discretionary',
  'Consumer Staples',
  'Industrials',
  'Materials',
  'Utilities',
  'Real Estate',
  'Telecom',
  'Other',
]

function Chip({ label, value, tone = 'default' }) {
  return (
    <span className={`rl-up-chip ${tone}`} title={`${label}: ${value || 'Not Set'}`}>
      {label}: {value || '—'}
    </span>
  )
}

export default function GlobalConfigInlineEditor() {
  const { config, setConfig } = useGlobalConfig()
  const [editingConfig, setEditingConfig] = useState(false)
  const [cfgDraft, setCfgDraft] = useState(config)

  useEffect(() => {
    setCfgDraft(config)
  }, [config])

  const saveConfig = () => {
    setConfig(cfgDraft)
    setEditingConfig(false)
  }

  return (
    <div className="rl-up-right-group">
      <div className="rl-up-config-inline">
        <span className="rl-up-config-inline-label">Current Configuration</span>
        <span className="rl-config-hint" aria-label="Configuration auto-application scope">
          <span className="rl-config-hint-icon">i</span>
          <span className="rl-config-hint-tip">Auto-applies in Upload, Compare, and Tables.</span>
        </span>
        <Chip label="Company" value={config.company} tone="violet" />
        <Chip label="Year" value={config.year} tone="blue" />
        <Chip label="Ticker" value={config.ticker} tone="green" />
        <Chip label="Industry" value={config.industry} />
      </div>

      <div className="rl-up-edit-wrap">
        <button className="btn-secondary rl-up-header-edit" onClick={() => setEditingConfig((v) => !v)}>
          {editingConfig ? 'Close' : 'Edit'}
        </button>
        {editingConfig ? (
          <div className="rl-up-config-popover">
            <div>
              <label className="section-title">Company</label>
              <input
                className="input mt-2"
                value={cfgDraft.company || ''}
                onChange={(e) => setCfgDraft((p) => ({ ...p, company: e.target.value }))}
                placeholder="e.g. Apple Inc."
              />
            </div>
            <div>
              <label className="section-title">Year</label>
              <select
                className="input mt-2"
                value={cfgDraft.year || ''}
                onChange={(e) => setCfgDraft((p) => ({ ...p, year: e.target.value }))}
              >
                <option value="">—</option>
                {YEARS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="section-title">Ticker</label>
              <input
                className="input mt-2"
                value={cfgDraft.ticker || ''}
                onChange={(e) => setCfgDraft((p) => ({ ...p, ticker: e.target.value.toUpperCase() }))}
                placeholder="e.g. AAPL"
              />
            </div>
            <div>
              <label className="section-title">Industry</label>
              <select
                className="input mt-2"
                value={cfgDraft.industry || ''}
                onChange={(e) => setCfgDraft((p) => ({ ...p, industry: e.target.value }))}
              >
                <option value="">—</option>
                {INDUSTRIES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="rl-up-config-actions">
              <button className="btn-secondary" onClick={() => setCfgDraft({ company: '', year: '', ticker: '', industry: '' })}>
                Reset
              </button>
              <button className="btn-primary" onClick={saveConfig}>
                Save
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

