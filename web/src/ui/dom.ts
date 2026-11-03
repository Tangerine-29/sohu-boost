export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, unknown> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue
    if (k === 'class') node.className = String(v)
    else if (k === 'html') node.innerHTML = String(v)
    else if (k.startsWith('on') && typeof v === 'function') {
      node.addEventListener(k.slice(2).toLowerCase(), v as EventListener)
    } else if (k === 'checked' || k === 'disabled') {
      ;(node as unknown as Record<string, unknown>)[k] = Boolean(v)
    } else node.setAttribute(k, String(v))
  }
  for (const c of children) {
    node.append(typeof c === 'string' ? document.createTextNode(c) : c)
  }
  return node
}

export const q = <T extends HTMLElement = HTMLElement>(sel: string): T =>
  document.querySelector(sel) as T

export function fmtTime(ms: number): string {
  if (!ms) return '—'
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function fmtNum(n: number | undefined): string {
  if (n == null) return '—'
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

export function flash(node: HTMLElement, text: string, ok = true, ms = 3500) {
  node.textContent = text
  node.className = `msg ${ok ? 'ok' : 'err'}`
  window.setTimeout(() => {
    node.textContent = ''
    node.className = 'msg'
  }, ms)
}
