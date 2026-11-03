import './style.css'
import { initBackground } from './three/background'
import { createConfigPanel } from './ui/config'
import { createFeedPanel } from './ui/feeds'
import { createKnowledgePanel } from './ui/knowledge'
import { el, q } from './ui/dom'

const app = q('#app')

// ---------- 头部 ----------
const hero = el(
  'div',
  { class: 'hero' },
  el('h1', {}, '曝光触发监控'),
  el('div', { class: 'sub', id: 'hero-sub' }, '正在连接…'),
)

// ---------- 面板 ----------
const config = createConfigPanel()
const feeds = createFeedPanel(() => {})

const refreshBtn = el('button', { onclick: () => feeds.load(config.getCircle(), config.getDays()) }, '刷新列表')

const controlPanel = el(
  'div',
  { class: 'panel' },
  config.node,
)

const stats = el(
  'div',
  { class: 'stats' },
  el('div', { class: 'stat' }, el('b', { id: 's-feeds' }, '—'), el('span', {}, '窗口内帖子')),
  el('div', { class: 'stat' }, el('b', { id: 's-hits' }, '—'), el('span', {}, '已触发帖数')),
  el('div', { class: 'stat' }, el('b', { id: 's-exposure' }, '—'), el('span', {}, '累计推送曝光')),
  el('div', { class: 'stat' }, el('b', { id: 's-comments' }, '—'), el('span', {}, '触发评论数')),
)

const feedPanel = el(
  'div',
  { class: 'panel', style: 'margin-top:18px' },
  el(
    'div',
    { class: 'row' },
    el('label', { style: 'font-size:13px;color:var(--fg);font-weight:600' }, '帖子列表'),
    el('span', { style: 'flex:1' }),
    refreshBtn,
  ),
  feeds.node,
)

const kb = createKnowledgePanel()
const kbPanel = el(
  'div',
  { class: 'panel', style: 'margin-top:18px' },
  el('details', {}, el('summary', { style: 'font-size:13px;color:var(--fg);font-weight:600' }, '知识库（让 AI 知道学校的真实情况）'), kb.node),
)

app.append(hero, controlPanel, stats, feedPanel, kbPanel)

// ---------- 背景 ----------
const bg = q<HTMLCanvasElement>('#bg')
let stop: (() => void) | null = null
try {
  stop = initBackground(bg)
} catch (e) {
  console.warn('Three.js 背景初始化失败，已降级', e)
}

window.addEventListener('beforeunload', () => stop?.())

// ---------- 首次加载 ----------
window.setTimeout(() => {
  feeds.load(config.getCircle(), config.getDays())
}, 300)

// 每 3 分钟刷新（与监听器轮询一致）
window.setInterval(() => feeds.load(config.getCircle(), config.getDays()), 180000)
