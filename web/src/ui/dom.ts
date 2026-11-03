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

/** 北京时间的各字段（固定 UTC+8，不跟随浏览器时区） */
function bjParts(ms: number) {
  // 先按 UTC 取出，再手动加 8 小时，避免依赖浏览器 locale
  const t = new Date(ms + 8 * 3600 * 1000)
  return {
    y: t.getUTCFullYear(),
    mo: t.getUTCMonth() + 1,
    d: t.getUTCDate(),
    h: t.getUTCHours(),
    mi: t.getUTCMinutes(),
    s: t.getUTCSeconds(),
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** 毫秒 → MM-DD HH:mm（北京时间） */
export function fmtTime(ms: number): string {
  if (!ms) return '—'
  const t = bjParts(ms)
  return `${pad(t.mo)}-${pad(t.d)} ${pad(t.h)}:${pad(t.mi)}`
}

/** 当前北京时间 HH:mm:ss */
export function nowBJ(): string {
  const t = bjParts(Date.now())
  return `${pad(t.h)}:${pad(t.mi)}:${pad(t.s)}`
}

/** 当前北京时间 完整格式 */
export function nowBJFull(): string {
  const t = bjParts(Date.now())
  return `${t.y}-${pad(t.mo)}-${pad(t.d)} ${pad(t.h)}:${pad(t.mi)}:${pad(t.s)}`
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
