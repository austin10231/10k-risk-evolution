import { useEffect } from 'react'

function toPx(n) {
  return `${Math.max(0, Math.round(Number(n) || 0))}px`
}

export default function useSlidingTabIndicator(ref, deps = []) {
  useEffect(() => {
    const host = ref?.current
    if (!host) return undefined

    const update = () => {
      const active = host.querySelector('.rl-strip-tab.active, .rl-tab-btn.active')
      if (!active) {
        host.style.setProperty('--rl-indicator-width', '0px')
        host.style.setProperty('--rl-indicator-x', '0px')
        host.style.setProperty('--rl-indicator-opacity', '0')
        return
      }

      const hostRect = host.getBoundingClientRect()
      const activeRect = active.getBoundingClientRect()
      const x = activeRect.left - hostRect.left

      host.style.setProperty('--rl-indicator-width', toPx(activeRect.width))
      host.style.setProperty('--rl-indicator-x', toPx(x))
      host.style.setProperty('--rl-indicator-opacity', '1')
    }

    const raf = requestAnimationFrame(update)
    const onResize = () => update()
    window.addEventListener('resize', onResize)

    const resizeObserver = new ResizeObserver(update)
    resizeObserver.observe(host)
    Array.from(host.children).forEach((child) => resizeObserver.observe(child))

    const mutationObserver = new MutationObserver(update)
    mutationObserver.observe(host, {
      subtree: true,
      attributes: true,
      attributeFilter: ['class'],
    })

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      resizeObserver.disconnect()
      mutationObserver.disconnect()
    }
  }, [ref, ...deps])
}

