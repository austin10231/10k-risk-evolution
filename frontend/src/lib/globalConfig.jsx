import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'risklens_global_config_v1'

const DEFAULT_CONFIG = {
  company: '',
  year: '',
  ticker: '',
  industry: '',
}

const GlobalConfigContext = createContext({
  config: DEFAULT_CONFIG,
  setConfig: () => {},
  resetConfig: () => {},
})

function sanitize(next) {
  return {
    company: String(next?.company || '').trim(),
    year: String(next?.year || '').trim(),
    ticker: String(next?.ticker || '').trim().toUpperCase(),
    industry: String(next?.industry || '').trim(),
  }
}

export function GlobalConfigProvider({ children }) {
  const [config, setConfigState] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_CONFIG
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return DEFAULT_CONFIG
      return sanitize(JSON.parse(raw))
    } catch {
      return DEFAULT_CONFIG
    }
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  }, [config])

  const value = useMemo(
    () => ({
      config,
      setConfig: (partial) => setConfigState((prev) => sanitize({ ...prev, ...partial })),
      resetConfig: () => setConfigState(DEFAULT_CONFIG),
    }),
    [config],
  )

  return <GlobalConfigContext.Provider value={value}>{children}</GlobalConfigContext.Provider>
}

export function useGlobalConfig() {
  return useContext(GlobalConfigContext)
}

