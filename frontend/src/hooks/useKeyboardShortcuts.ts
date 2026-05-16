import { useEffect } from 'react'

type ShortcutMap = Record<string, () => void>

/**
 * Register global keyboard shortcuts. Only fires when no input/textarea
 * is focused (except for Ctrl+Enter which fires from any element).
 */
export function useKeyboardShortcuts(shortcuts: ShortcutMap) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      const isInput = tag === 'input' || tag === 'textarea' || tag === 'select'

      // Ctrl+Enter always fires
      if (e.ctrlKey && e.key === 'Enter' && shortcuts['Ctrl+Enter']) {
        e.preventDefault()
        shortcuts['Ctrl+Enter']()
        return
      }

      // Esc always fires
      if (e.key === 'Escape' && shortcuts['Escape']) {
        shortcuts['Escape']()
        return
      }

      // Other shortcuts only when not in an input
      if (isInput) return

      // ? for help
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && shortcuts['?']) {
        e.preventDefault()
        shortcuts['?']()
        return
      }

      // Number keys 1-7 for tab switching
      if (/^[1-7]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const key = `Tab${e.key}` as keyof ShortcutMap
        if (shortcuts[key]) {
          e.preventDefault()
          shortcuts[key]()
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [shortcuts])
}
