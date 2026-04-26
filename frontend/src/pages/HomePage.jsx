import React, { useState } from 'react'
import { Link } from 'react-router-dom'

const quickCards = [
  {
    icon: '📤',
    accent: '#6366f1',
    title: 'Upload & Auto-Fetch',
    desc: 'Ingest new filings and manage saved Records in one place.',
    buttons: [
      { label: 'Open Upload →', to: '/upload', primary: true },
      { label: 'Open Records →', to: '/library' },
    ],
  },
  {
    icon: '⚖️',
    accent: '#f59e0b',
    title: 'Compare Risks',
    desc: 'Run year-over-year or cross-company comparisons to detect structural risk changes.',
    buttons: [{ label: 'Open Compare →', to: '/compare' }],
  },
  {
    icon: '📊',
    accent: '#10b981',
    title: 'Financial Tables',
    desc: 'Extract 5 core statements via Textract and store JSON/CSV for downstream analysis.',
    buttons: [{ label: 'Open Tables →', to: '/tables' }],
  },
  {
    icon: '🤖',
    accent: '#8b5cf6',
    title: 'AI Risk Agent',
    desc: 'Generate priority scores, key findings, recommendations, and full analyst-ready reports.',
    buttons: [{ label: 'Open Agent →', to: '/agent' }],
  },
  {
    icon: '📈',
    accent: '#2563eb',
    title: 'Dashboard + Stock',
    desc: 'Monitor portfolio risk and market movement together in one linked workflow.',
    buttons: [
      { label: 'Dashboard →', to: '/dashboard' },
      { label: 'Stock →', to: '/stock' },
    ],
  },
  {
    icon: '📰',
    accent: '#0ea5e9',
    title: 'News Intelligence',
    desc: 'Track recent company headlines with pressure scoring and risk-linked summaries.',
    buttons: [{ label: 'Open News →', to: '/news' }],
  },
]

const steps = [
  { idx: 'STEP 1', color: '#6366f1', icon: '📥', title: 'Ingest Filing', desc: 'Use manual upload or SEC EDGAR auto-fetch to create a new filing record.' },
  { idx: 'STEP 2', color: '#0ea5e9', icon: '🧠', title: 'Extract Risks', desc: 'Parse Item 1/1A with Standard rules or AI-enhanced Bedrock extraction.' },
  { idx: 'STEP 3', color: '#10b981', icon: '📊', title: 'Extract Tables', desc: 'Run Textract to capture key financial statements and persist outputs.' },
  { idx: 'STEP 4', color: '#f59e0b', icon: '⚖️', title: 'Compare Changes', desc: 'Detect NEW / REMOVED / MODIFIED risks across years or companies.' },
  { idx: 'STEP 5', color: '#8b5cf6', icon: '🤖', title: 'Run Agent', desc: 'Score impact/likelihood/urgency and generate structured analyst guidance.' },
  { idx: 'STEP 6', color: '#2563eb', icon: '📰', title: 'Link Market + News', desc: 'Overlay risk ratings with stock context and ranked recent news evidence.' },
]

const features = [
  ['End-to-end 10-K workflow', 'Ingest → Extract → Compare → Agent'],
  ['Dual risk extraction modes', 'Standard + AI-Enhanced'],
  ['Financial table pipeline', 'Textract + JSON/CSV persistence'],
  ['Structured risk storage and reusable records', 'S3-backed'],
  ['Cross-year and cross-company change detection', 'NEW / REMOVED / MODIFIED'],
  ['AI agent scoring and recommendations', 'Impact / Likelihood / Urgency'],
  ['Risk monitoring dashboard', 'Heatmap + ranking + risk/return'],
  ['Dedicated stock analytics page', 'Search + price/volume charts'],
  ['News intelligence module', 'Headline pressure + risk linkage'],
  ['Global configuration sync across core workflows', 'Company / Year / Industry / Ticker'],
  ['Cloud persistence and analyst export views', 'JSON / CSV / report'],
]

const roadmap = [
  ['Higher extraction consistency and confidence calibration', 'Accuracy'],
  ['Stronger risk-market-news linkage scoring', 'Correlation'],
  ['Lower page latency via warm cache and lazy loading', 'Performance'],
  ['Better evidence ranking and duplicate-news suppression', 'Signal Quality'],
  ['More explainable agent reasoning trace for analysts', 'Trust'],
]

export default function HomePage() {
  const [lang, setLang] = useState('EN')

  return (
    <div className="rl-home-shell space-y-7">
      <section className="rl-home-hero">
        <div className="rl-home-hero-grid" />
        <div className="rl-home-hero-glow" />
        <div className="rl-home-lang">
          <button className={lang === 'EN' ? 'active' : ''} onClick={() => setLang('EN')}>EN</button>
          <button className={lang === '中文' ? 'active' : ''} onClick={() => setLang('中文')}>中文</button>
        </div>
        <div className="rl-home-hero-content">
          <div className="rl-home-pill">
            <span className="dot" />
            <span>SEC 10-K ANALYSIS PLATFORM</span>
          </div>
          <h1>
            RiskLens<span>AI</span>
          </h1>
          <p>Turn 10-K filings into structured risk intelligence — extract, compare, and analyze with AI in minutes.</p>
          <div className="rl-home-powered">
            <strong>Powered by</strong>
            <span>AWS Bedrock</span>
            <span>Textract</span>
            <span>S3</span>
          </div>
        </div>
      </section>

      <section>
        <div className="section-headline">
          <div className="section-rail" />
          <div>
            <h3 className="section-title-strong">Quick Start</h3>
            <p className="section-sub">Choose where to begin across 6 core modules</p>
          </div>
        </div>
        <div className="rl-home-quick-grid">
          {quickCards.map((card) => (
            <div key={card.title} className="rl-home-quick-card-wrap">
              <article className="rl-home-quick-card" style={{ borderTopColor: card.accent }}>
                <p className="icon">{card.icon}</p>
                <h4>{card.title}</h4>
                <p className="desc">{card.desc}</p>
              </article>
              <div className="rl-home-quick-actions">
                {card.buttons.map((b) => (
                  <Link key={b.label} to={b.to} className={b.primary ? 'btn-primary rl-home-action-btn' : 'btn-secondary rl-home-action-btn'}>
                    {b.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="section-headline">
          <div className="section-rail" />
          <div>
            <h3 className="section-title-strong">How It Works</h3>
            <p className="section-sub">Keep the same 6-step flow, now with market and news linkage</p>
          </div>
        </div>
        <div className="rl-home-steps-grid">
          {steps.map((step) => (
            <article key={step.idx} className="rl-home-step-card">
              <div className="rl-home-step-top">
                <span className="step-idx" style={{ color: step.color }}>{step.idx}</span>
                <span className="step-icon" style={{ color: step.color, borderColor: `${step.color}33`, background: `${step.color}12` }}>
                  {step.icon}
                </span>
              </div>
              <h4>{step.title}</h4>
              <p>{step.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="rl-home-bottom-grid">
        <div>
          <div className="section-headline">
            <div className="section-rail" />
            <div>
              <h3 className="section-title-strong">Current Features</h3>
              <p className="section-sub">What's available today</p>
            </div>
          </div>
          <article className="card p-4">
            {features.map(([name, tag]) => (
              <div key={name} className="rl-home-row">
                <p><span>✓</span>{name}</p>
                <small>{tag}</small>
              </div>
            ))}
          </article>
        </div>

        <div>
          <div className="section-headline">
            <div className="section-rail" />
            <div>
              <h3 className="section-title-strong">Future Releases</h3>
              <p className="section-sub">Next optimization priorities</p>
            </div>
          </div>
          <article className="rl-home-roadmap">
            <div className="head">🔮 Planned next</div>
            <div className="body">
              {roadmap.map(([name, tag]) => (
                <div key={name} className="rl-home-row">
                  <p><span>◆</span>{name}</p>
                  <small>{tag}</small>
                </div>
              ))}
            </div>
          </article>
          <article className="card mt-3 p-4 text-sm leading-6 text-slate-500">
            Current modules are feature-complete for the end-to-end workflow. Future iterations focus on improving
            accuracy, cross-signal relevance, and interaction speed as company coverage expands.
          </article>
        </div>
      </section>

      <section className="card rl-home-footer">
        <p>
          RiskLens<span>AI</span> · SCU × AWS Team 1
        </p>
        <p>Mutian He · Yuhan Luan · Jiaoqing Lu · Jiayi Yan · © 2026</p>
      </section>
    </div>
  )
}
