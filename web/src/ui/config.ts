import { api } from '../api'
import type { AppConfig } from '../types'
import { el, flash } from './dom'

export function createConfigPanel() {
  const msg = el('span', { class: 'msg' })

  const inKeyword = el('input', { type: 'text', style: 'width:130px' })
  const inDays = el('input', { type: 'number', min: '1', max: '30', style: 'width:70px' })
  const inMax = el('input', { type: 'number', min: '0', max: '100000', style: 'width:90px' })
  const inCircle = el('input', { type: 'text', style: 'flex:1;min-width:240px' })

  // AI
  const inAiEn = el('input', { type: 'checkbox' })
  const inAiLen = el('input', { type: 'number', min: '4', max: '200', style: 'width:70px' })
  const inAiMode = el('select', {})
  inAiMode.append(
    el('option', { value: 'trigger_only' }, '只回暗号'),
    el('option', { value: 'all' }, '回所有评论'),
  )
  const inAiSkip = el('input', { type: 'checkbox' })
  const inAiBase = el('input', { type: 'text', placeholder: 'https://api.xxx.com/v1', style: 'flex:1;min-width:220px' })
  const inAiKey = el('input', { type: 'password', placeholder: 'sk-...', style: 'flex:1;min-width:220px' })
  const inAiModel = el('input', { type: 'text', placeholder: 'glm-5.3', style: 'width:150px' })
  const inAiPrompt = el('textarea', {
    rows: '5',
    placeholder: '留空使用内置人格（建院大肥鱼）',
    style: 'flex:1;min-width:300px',
  })

  // 知识库设置
  const inKbEn = el('input', { type: 'checkbox' })
  const inKbTop = el('input', { type: 'number', min: '1', max: '20', style: 'width:70px' })
  const inKbChars = el('input', { type: 'number', min: '0', max: '8000', style: 'width:90px' })

  // 测试
  const inTestFeed = el('input', { type: 'text', value: '大家好', style: 'width:160px' })
  const inTestText = el('input', { type: 'text', value: '不好', style: 'width:130px' })
  const testOut = el('div', { style: 'font-size:13px;line-height:1.7;min-height:20px' })

  function fill(c: AppConfig) {
    inKeyword.value = String(c.keyword ?? 'exposure')
    inDays.value = String(c.window_days ?? 7)
    inMax.value = String(c.max_exposure ?? 3000)
    const saved = localStorage.getItem('circle') || '<CIRCLE_ID>'
    inCircle.value = String(c.circle ?? saved)

    inAiEn.checked = Boolean(c.ai_enabled)
    inAiLen.value = String(c.ai_max_len ?? 20)
    inAiMode.value = String(c.ai_reply_mode ?? 'trigger_only')
    inAiSkip.checked = Boolean(c.ai_skip_own)
    inAiBase.value = String(c.ai_base_url ?? '')
    inAiKey.value = String(c.ai_api_key ?? '')
    inAiModel.value = String(c.ai_model ?? '')
    inAiPrompt.value = String(c.ai_system_prompt ?? '')

    inKbEn.checked = Boolean(c.kb_enabled ?? true)
    inKbTop.value = String(c.kb_top_k ?? 6)
    inKbChars.value = String(c.kb_max_chars ?? 1200)
  }

  async function load() {
    try {
      const j = await api.getConfig()
      if (j.ok) fill(j.config)
    } catch (e) {
      flash(msg, String(e), false)
    }
  }

  async function saveRules() {
    const patch: Partial<AppConfig> = {
      keyword: inKeyword.value.trim() || 'exposure',
      window_days: Number(inDays.value) || 7,
      max_exposure: Number(inMax.value) || 0,
    }
    const j = await api.saveConfig(patch)
    if (j.ok) flash(msg, '规则已保存')
    else flash(msg, j.error || '失败', false)
  }

  async function saveAi() {
    const patch: Partial<AppConfig> = {
      ai_enabled: inAiEn.checked,
      ai_max_len: Number(inAiLen.value) || 20,
      ai_reply_mode: inAiMode.value,
      ai_skip_own: inAiSkip.checked,
      ai_base_url: inAiBase.value.trim(),
      ai_api_key: inAiKey.value.trim(),
      ai_model: inAiModel.value.trim(),
      ai_system_prompt: inAiPrompt.value,
      kb_enabled: inKbEn.checked,
      kb_top_k: Number(inKbTop.value) || 6,
      kb_max_chars: Number(inKbChars.value) || 1200,
    }
    const j = await api.saveConfig(patch)
    if (j.ok) flash(msg, 'AI 设置已保存')
    else flash(msg, j.error || '失败', false)
  }

  async function test() {
    testOut.replaceChildren(
      el('span', { class: 'spinner' }),
      el('span', { style: 'margin-left:8px' }, '生成中…'),
    )
    try {
      const j = await api.aiTest(inTestFeed.value, inTestText.value)
      testOut.textContent = j.ok ? `✅ ${j.text}` : `❌ ${j.error}`
    } catch (e) {
      testOut.textContent = `❌ ${String(e)}`
    }
  }

  const node = el(
    'div',
    {},
    // 规则
    el(
      'div',
      { class: 'row' },
      el('label', {}, '触发关键词'),
      inKeyword,
      el('label', {}, '窗口(天)'),
      inDays,
      el('label', {}, '曝光上限'),
      inMax,
      el('button', { onclick: saveRules }, '保存规则'),
      msg,
    ),
    el(
      'div',
      { class: 'row', style: 'margin-top:10px' },
      el('label', {}, '圈子 ID'),
      inCircle,
    ),

    // AI
    el(
      'details',
      {},
      el('summary', {}, 'AI 自动回复设置'),
      el(
        'div',
        { class: 'row', style: 'margin-top:12px' },
        el('label', {}, '启用'),
        inAiEn,
        el('label', {}, '字数上限'),
        inAiLen,
        el('label', {}, '回复范围'),
        inAiMode,
        el('label', {}, '跳过自己'),
        inAiSkip,
      ),
      el(
        'div',
        { class: 'row', style: 'margin-top:10px' },
        el('label', {}, '接口'),
        inAiBase,
      ),
      el(
        'div',
        { class: 'row', style: 'margin-top:10px' },
        el('label', {}, '密钥'),
        inAiKey,
        el('label', {}, '模型'),
        inAiModel,
      ),
      el(
        'div',
        { class: 'row', style: 'margin-top:10px;align-items:flex-start' },
        el('label', { style: 'padding-top:10px' }, '人设'),
        inAiPrompt,
      ),
      el(
        'div',
        { class: 'row', style: 'margin-top:10px' },
        el('label', {}, '知识库'),
        inAiEn ? inKbEn : inKbEn,
        el('label', {}, '最多注入'),
        inKbTop,
        el('label', {}, '字符上限'),
        inKbChars,
        el('button', { onclick: saveAi }, '保存 AI 设置'),
      ),
      el(
        'div',
        { class: 'row', style: 'margin-top:12px' },
        el('label', {}, '测试'),
        inTestFeed,
        inTestText,
        el('button', { class: 'mini', onclick: test }, '测试生成'),
      ),
      el('div', { style: 'margin-top:10px' }, testOut),
    ),
  )

  load()
  return { node, getCircle: () => inCircle.value.trim(), getDays: () => Number(inDays.value) || 7 }
}
