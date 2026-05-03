import { useEffect } from 'react'

export interface CullingKeyboardHandlers {
  onPick: () => void
  onReject: () => void
  onUnflag: () => void
  onPrevStack: () => void
  onNextStack: () => void
  onPrevImage: () => void
  onNextImage: () => void
  onToggleMode: () => void
  onToggleZoom: () => void
  onToggleHints: () => void
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return false
}

export function useCullingKeyboard(handlers: CullingKeyboardHandlers): void {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (isTypingTarget(e.target)) return

      const k = e.key

      let consumed = true
      switch (k) {
        case 'p':
        case 'P':
          handlers.onPick()
          break
        case 'x':
        case 'X':
          handlers.onReject()
          break
        case 'u':
        case 'U':
          handlers.onUnflag()
          break
        case 'ArrowLeft':
          handlers.onPrevStack()
          break
        case 'ArrowRight':
          handlers.onNextStack()
          break
        case '[':
        case ',':
          handlers.onPrevImage()
          break
        case ']':
        case '.':
          handlers.onNextImage()
          break
        case 'e':
        case 'E':
        case 'Enter':
          handlers.onToggleMode()
          break
        case 'z':
        case 'Z':
        case ' ':
          handlers.onToggleZoom()
          break
        case '?':
          handlers.onToggleHints()
          break
        default:
          consumed = false
      }

      if (consumed) e.preventDefault()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handlers])
}
