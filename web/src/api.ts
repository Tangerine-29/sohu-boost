import type { AppConfig, KBEntry, WindowResp } from './types'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  return (await r.json()) as T
}

export const api = {
  window(circle: string, days: number, pages = 5): Promise<WindowResp> {
    const q = new URLSearchParams({ circle, days: String(days), pages: String(pages) })
    return req<WindowResp>(`/api/window?${q}`)
  },

  getConfig(): Promise<{ ok: boolean; config: AppConfig }> {
    return req('/api/config')
  },

  saveConfig(patch: Partial<AppConfig>): Promise<{ ok: boolean; error?: string }> {
    return req('/api/config', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(patch),
    })
  },

  aiTest(feed: string, text: string): Promise<{ ok: boolean; text?: string; error?: string }> {
    return req('/api/ai/test', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ feed, text }),
    })
  },

  kbList(): Promise<{ ok: boolean; entries: KBEntry[]; total: number }> {
    return req('/api/kb')
  },

  kbAdd(e: Partial<KBEntry>): Promise<{ ok: boolean; entry?: KBEntry; error?: string }> {
    return req('/api/kb', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(e) })
  },

  kbUpdate(e: Partial<KBEntry> & { id: string }): Promise<{ ok: boolean; entry?: KBEntry; error?: string }> {
    return req('/api/kb', { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(e) })
  },

  kbDelete(id: string): Promise<{ ok: boolean; error?: string }> {
    return req('/api/kb', { method: 'DELETE', headers: JSON_HEADERS, body: JSON.stringify({ id }) })
  },
}
