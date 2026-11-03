import { api } from '../api'
import type { RawFeed, WindowResp } from '../types'
import { el, fmtNum, fmtTime, nowBJ, q } from './dom'

export function createFeedPanel(onLoadState: (loading: boolean) => void) {
  const tbody = el('div', { class: 'feed-list' })

  function renderFeed(f: RawFeed, trig?: { n?: number }): HTMLElement {
    const hit = Boolean(trig)
    return el(
      'div',
      { class: `feed${hit ? ' hit' : ''}` },
      el('div', { class: 'time' }, fmtTime(f.createTime)),
      el(
        'div',
        { class: 'body' },
        el('div', { class: 'author' }, f.author?.name || '匿名'),
        el('div', { class: 'content' }, f.content || '（无内容）'),
      ),
      el(
        'div',
        { class: 'meta' },
        el('span', {}, '评论 ', el('em', {}, fmtNum(f.counts?.comment))),
        el('span', {}, '曝光 ', el('em', {}, fmtNum(f.counts?.exposure))),
        hit
          ? el('span', { style: 'color:#34d399' }, `✓ ${trig?.n ?? 0}`)
          : el('span', { style: 'opacity:.35' }, '—'),
      ),
    )
  }

  function render(resp: WindowResp) {
    const feeds = resp.feeds || []
    const trig = resp.triggered || {}
    tbody.replaceChildren(...feeds.map((f) => renderFeed(f, trig[f.feedId])))
    if (!feeds.length) {
      tbody.replaceChildren(el('div', { class: 'empty' }, '窗口内没有帖子'))
    }

    // 统计
    const hitIds = Object.keys(trig)
    let exposure = 0
    let comments = 0
    for (const f of feeds) {
      exposure += f.counts?.exposure ?? 0
      comments += f.counts?.comment ?? 0
    }
    let pushed = 0
    for (const r of Object.values(trig)) pushed += (r.sent ?? 0) * 2

    // 运行时查询：这些节点在 createFeedPanel 之后才挂到 DOM
    q('#s-feeds').textContent = String(feeds.length)
    q('#s-hits').textContent = String(hitIds.length)
    q('#s-exposure').textContent = fmtNum(pushed)
    q('#s-comments').textContent = String(comments)

    const now = nowBJ()
    q('#hero-sub').innerHTML =
      `圈子 <b>${resp.circle}</b> · 最近 <b>${resp.days}</b> 天 · ` +
      `更新 <b>${now}</b>（北京时间） · 帖子总曝光 <b>${fmtNum(exposure)}</b>`
  }

  async function load(circle: string, days: number) {
    onLoadState(true)
    tbody.replaceChildren(
      el(
        'div',
        { class: 'loading' },
        el('span', { class: 'spinner' }),
        el('span', {}, '读取中…（首次约 9 秒，之后走缓存）'),
      ),
    )
    try {
      const resp = await api.window(circle, days)
      if (!resp.ok) {
        tbody.replaceChildren(
          el('div', { class: 'empty', style: 'color:#f87171' }, resp.error || '读取失败'),
        )
        return
      }
      render(resp)
    } catch (e) {
      tbody.replaceChildren(
        el('div', { class: 'empty', style: 'color:#f87171' }, String(e)),
      )
    } finally {
      onLoadState(false)
    }
  }

  return { node: tbody, load }
}
