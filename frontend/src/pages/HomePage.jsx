import React from 'react'
import { Link } from 'react-router-dom'

const cards = [
  { to: '/dashboard', title: 'Dashboard', desc: 'Portfolio metrics, risk distribution and recent records.' },
  { to: '/library', title: 'Library', desc: 'Browse all uploaded/fetched filings from S3 index.' },
  { to: '/analyze', title: 'Analyze', desc: 'Inspect one filing with category and sub-risk breakdown.' },
  { to: '/compare', title: 'Compare', desc: 'Year-over-year or record-vs-record risk delta.' },
  { to: '/news', title: 'News', desc: 'MarketAux news stream with ticker/company filters.' },
  { to: '/stock', title: 'Stock', desc: 'Live quote snapshot and 1Y history from Yahoo Finance.' },
  { to: '/agent', title: 'Agent', desc: 'Chat interface powered by Railway runtime + AgentCore logic.' },
]

export default function HomePage() {
  return (
    <div className="space-y-4">
      <section className="card p-6">
        <p className="inline-flex rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-extrabold uppercase tracking-[0.14em] text-brand-700">
          Product Frontend v1
        </p>
        <h3 className="mt-3 text-3xl font-extrabold text-slate-900">Full Product, Decoupled</h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          This frontend keeps the same product structure as your Streamlit app, now split from the backend.
          Every module below is wired to Railway API endpoints.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <Link key={card.to} to={card.to} className="card group p-5 transition hover:-translate-y-0.5 hover:border-brand-200">
            <p className="section-title">Module</p>
            <h4 className="mt-2 text-xl font-extrabold text-slate-900 group-hover:text-brand-700">{card.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-600">{card.desc}</p>
            <p className="mt-4 text-sm font-bold text-brand-600">Open →</p>
          </Link>
        ))}
      </section>
    </div>
  )
}
