import React, { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { startAuthLogin } from '../lib/api'
import logo from '../assets/logo.svg'

function GoogleIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303C33.655 32.657 29.263 36 24 36c-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.84 1.154 7.951 3.049l5.657-5.657C34.046 6.053 29.27 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" />
      <path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 16.108 19.003 13 24 13c3.059 0 5.84 1.154 7.951 3.049l5.657-5.657C34.046 6.053 29.27 4 24 4c-7.682 0-14.326 4.337-17.694 10.691z" />
      <path fill="#4CAF50" d="M24 44c5.167 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.162 35.091 26.715 36 24 36c-5.243 0-9.623-3.317-11.282-7.946l-6.522 5.025C9.53 39.556 16.227 44 24 44z" />
      <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.085 5.57l.003-.002 6.19 5.238C36.971 39.47 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" />
    </svg>
  )
}

function authPath({ mode, lang, returnTo }) {
  const params = new URLSearchParams()
  if (mode) params.set('mode', mode)
  if (lang) params.set('lang', lang)
  if (returnTo) params.set('return_to', returnTo)
  const query = params.toString()
  return `/auth${query ? `?${query}` : ''}`
}

function resolveReturnTo(raw) {
  if (typeof window === 'undefined') return ''
  const fallback = `${window.location.origin}/agent`
  const txt = String(raw || '').trim()
  if (!txt) return fallback
  if (txt.startsWith('/')) return `${window.location.origin}${txt}`
  return txt
}

export default function AuthPage() {
  const location = useLocation()
  const [email, setEmail] = useState('')
  const params = useMemo(() => new URLSearchParams(location.search || ''), [location.search])
  const mode = params.get('mode') === 'signup' ? 'signup' : 'signin'
  const lang = params.get('lang') === 'zh' ? 'zh' : 'en'
  const returnTo = resolveReturnTo(params.get('return_to'))
  const zh = lang === 'zh'
  const copy = zh
    ? {
      title: mode === 'signup' ? '创建你的账号' : '欢迎',
      subtitle: mode === 'signup' ? '注册 RiskLens AI 以开始使用。' : '登录 RiskLens AI 继续。',
      google: '使用 Google 继续',
      divider: '或',
      emailLabel: '工作邮箱',
      placeholder: 'you@company.com',
      submit: mode === 'signup' ? '创建账号' : '继续',
      switchPrefix: mode === 'signup' ? '已经有账号？' : '还没有账号？',
      switchText: mode === 'signup' ? '登录' : '注册',
      back: '返回官网首页',
    }
    : {
      title: mode === 'signup' ? 'Create your account' : 'Welcome',
      subtitle: mode === 'signup' ? 'Sign up to RiskLens AI to get started.' : 'Log in to RiskLens AI to continue.',
      google: 'Continue with Google',
      divider: 'OR',
      emailLabel: 'Work email address',
      placeholder: 'you@company.com',
      submit: mode === 'signup' ? 'Create account' : 'Continue',
      switchPrefix: mode === 'signup' ? 'Already have an account?' : "Don't have an account?",
      switchText: mode === 'signup' ? 'Sign in' : 'Sign up',
      back: 'Back to Landing Page',
    }

  const switchMode = mode === 'signup' ? 'signin' : 'signup'

  const continueWithGoogle = () => {
    startAuthLogin(returnTo, { idp: 'Google', prompt: 'login select_account' })
  }

  const continueWithEmail = (event) => {
    event.preventDefault()
    startAuthLogin(returnTo, {
      prompt: 'login select_account',
      loginHint: email.trim(),
    })
  }

  return (
    <main className="rl-auth-page">
      <section className="rl-auth-card" aria-labelledby="risklens-auth-title">
        <div className="rl-auth-logo-wrap">
          <img src={logo} alt="RiskLens AI" className="rl-auth-logo" />
        </div>
        <h1 id="risklens-auth-title" className="rl-auth-title">{copy.title}</h1>
        <p className="rl-auth-subtitle">{copy.subtitle}</p>

        <button type="button" className="rl-auth-google-btn" onClick={continueWithGoogle}>
          <GoogleIcon />
          <span>{copy.google}</span>
        </button>

        <div className="rl-auth-divider">
          <span />
          <strong>{copy.divider}</strong>
          <span />
        </div>

        <form className="rl-auth-form" onSubmit={continueWithEmail}>
          <label htmlFor="risklens-auth-email">{copy.emailLabel}</label>
          <input
            id="risklens-auth-email"
            type="email"
            autoComplete="email"
            placeholder={copy.placeholder}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" className="rl-auth-submit">{copy.submit}</button>
        </form>

        <p className="rl-auth-switch">
          <span>{copy.switchPrefix}</span>
          <Link to={authPath({ mode: switchMode, lang, returnTo })}>{copy.switchText}</Link>
        </p>
        <a className="rl-auth-back" href="https://risklensai.org/">{copy.back}</a>
      </section>
    </main>
  )
}
