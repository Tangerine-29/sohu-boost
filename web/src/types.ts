export interface RawFeed {
  feedId: string
  content: string
  createTime: number
  counts: { exposure?: number; comment?: number; repost?: number }
  author: { userId?: string; name?: string }
  circle?: { circleId?: string; name?: string }
  images?: string[]
  tag?: number
}

export interface TriggerRecord {
  n?: number
  sent?: number
  at?: string
  status?: string
  feedId?: string
}

export interface WindowResp {
  ok: boolean
  error?: string
  circle: string
  days: number
  feeds: RawFeed[]
  info: { totalCount?: number; pages?: number }
  triggered: Record<string, TriggerRecord>
  triggeredComments: unknown[]
}

export interface KBEntry {
  id: string
  title: string
  content: string
  tags: string
  enabled: boolean
  updated_at?: string
}

export interface AppConfig {
  keyword: string
  window_days: number
  max_exposure: number
  ai_enabled: boolean
  ai_base_url: string
  ai_api_key: string
  ai_model: string
  ai_system_prompt: string
  ai_max_len: number
  ai_reply_mode: string
  ai_skip_own: boolean
  kb_enabled: boolean
  kb_top_k: number
  kb_max_chars: number
  [k: string]: unknown
}
