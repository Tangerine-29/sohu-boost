import { api } from '../api'
import { el, flash } from './dom'

export function createKnowledgePanel() {
  const list = el('div')
  const msg = el('span', { class: 'msg' })
  const input = el('input', {
    type: 'text',
    placeholder: '写一句话，回车添加。例如：一食堂在教学楼东侧，早餐 6:30-9:00',
    style: 'flex:1;min-width:320px',
  })

  async function reload() {
    list.replaceChildren(
      el('div', { class: 'loading' }, el('span', { class: 'spinner' }), el('span', {}, '加载中…')),
    )
    try {
      const j = await api.kbList()
      if (!j.ok) {
        list.replaceChildren(el('div', { class: 'empty', style: 'color:#f87171' }, '读取失败'))
        return
      }
      const lines = (j as unknown as { lines: string[] }).lines || []
      if (!lines.length) {
        list.replaceChildren(
          el('div', { class: 'empty' }, '还没有内容，上面写一句试试'),
        )
        return
      }
      list.replaceChildren(...lines.map((text, i) => renderLine(text, i)))
    } catch (e) {
      list.replaceChildren(el('div', { class: 'empty', style: 'color:#f87171' }, String(e)))
    }
  }

  function renderLine(text: string, i: number): HTMLElement {
    return el(
      'div',
      { class: 'kb-item' },
      el(
        'div',
        { class: 'kb-head' },
        el('span', { class: 'kb-tag' }, String(i + 1)),
        el('span', { class: 'kb-spacer' }),
        el('button', { class: 'mini', onclick: () => edit(i, text) }, '编辑'),
        el('button', { class: 'mini danger', onclick: () => remove(i) }, '删除'),
      ),
      el('div', { class: 'kb-body' }, text),
    )
  }

  async function add() {
    const line = input.value.trim()
    if (!line) return
    const j = await api.kbAdd({ line } as never)
    if (!j.ok) {
      flash(msg, (j as unknown as { error?: string }).error || '添加失败', false)
      return
    }
    const added = (j as unknown as { added?: boolean }).added
    flash(msg, added ? '已添加' : '这句已经在里面了', added !== false)
    input.value = ''
    reload()
  }

  async function edit(i: number, old: string) {
    const v = prompt('修改内容', old)
    if (v === null) return
    const j = await api.kbUpdate({ id: String(i), content: v })
    if (j.ok) {
      flash(msg, '已保存')
      reload()
    } else flash(msg, (j as unknown as { error?: string }).error || '失败', false)
  }

  async function remove(i: number) {
    if (!confirm('确定删除这条？')) return
    const j = await api.kbDelete(String(i))
    if (j.ok) {
      flash(msg, '已删除')
      reload()
    } else flash(msg, '失败', false)
  }

  input.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  })

  const node = el(
    'div',
    {},
    el(
      'div',
      { class: 'row' },
      input,
      el('button', { onclick: add }, '添加'),
      el('button', { class: 'mini', onclick: reload }, '刷新'),
    ),
    el('div', { class: 'row', style: 'margin-top:8px' }, msg),
    el('div', { style: 'margin-top:14px' }, list),
  )

  reload()
  return { node }
}
