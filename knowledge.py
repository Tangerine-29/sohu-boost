#!/usr/bin/env python3
"""知识库：给 AI 补充学校的真实信息，避免它乱编。

最简单用法：往 knowledge.txt 里一行写一句话，全部注入 system prompt。
也兼容旧的 knowledge.json（结构化条目），会自动合并。

注入规则：
    - 按顺序拼接所有行
    - 总长度受 kb_max_chars 限制（默认 1500），超出截断
"""

import json
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
TXT_PATH = HERE / 'knowledge.txt'
JSON_PATH = HERE / 'knowledge.json'
LOCK = threading.Lock()

DEFAULT_MAX_CHARS = 1500


def _json_lines():
    if not JSON_PATH.exists():
        return []
    try:
        d = json.loads(JSON_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for x in (d.get('lines') or []):
        s = str(x).strip()
        if s:
            out.append(s)
    for e in (d.get('entries') or []):
        if not isinstance(e, dict) or not e.get('enabled', True):
            continue
        title = str(e.get('title') or '').strip()
        content = str(e.get('content') or '').strip()
        if not content:
            continue
        out.append(f'{title}：{content}' if title else content)
    return out


def load_lines():
    """读取所有知识行（txt 优先，合并 json，去重保序）。"""
    out = []
    if TXT_PATH.exists():
        try:
            for raw in TXT_PATH.read_text(encoding='utf-8').splitlines():
                line = raw.strip().lstrip('-*+ ').strip()
                if line and not line.startswith('#'):
                    out.append(line)
        except OSError:
            pass
    out.extend(_json_lines())
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def save_lines(lines):
    with LOCK:
        text = '\n'.join(str(x).strip() for x in lines if str(x).strip())
        TXT_PATH.write_text(text + ('\n' if text else ''), encoding='utf-8')


def add_line(text):
    text = str(text).strip()
    if not text:
        return False
    if text in load_lines():
        return False
    with LOCK:
        with TXT_PATH.open('a', encoding='utf-8') as f:
            f.write(text + '\n')
    return True


def remove_line(index):
    lines = load_lines()
    if 0 <= index < len(lines):
        lines.pop(index)
        save_lines(lines)
        return True
    return False


def replace_all(text):
    lines = []
    for raw in str(text).splitlines():
        line = raw.strip().lstrip('-*+ ').strip()
        if line and not line.startswith('#'):
            lines.append(line)
    save_lines(lines)
    return len(lines)


def render_for_prompt(cfg=None):
    """生成注入 system prompt 的片段。"""
    cfg = cfg or {}
    if not cfg.get('kb_enabled', True):
        return ''
    lines = load_lines()
    if not lines:
        return ''

    max_chars = int(cfg.get('kb_max_chars') or DEFAULT_MAX_CHARS)
    head = '以下是本校的真实信息，回答涉及这些内容时必须以此为准，不要编造：'
    budget = max_chars - len(head)

    picked, total = [], 0
    for line in lines:
        if total + len(line) + 3 > budget:
            break
        picked.append(line)
        total += len(line) + 3

    if not picked:
        return ''
    return head + '\n' + '\n'.join(f'- {x}' for x in picked)


# ---------- 兼容旧 API ----------

def list_entries():
    return [
        {'id': str(i), 'title': '', 'content': line, 'tags': '',
         'enabled': True, 'updated_at': ''}
        for i, line in enumerate(load_lines())
    ]


def add(title, content, tags='', enabled=True):
    text = str(content or '').strip()
    if title and title not in text:
        text = f'{title}：{text}'
    add_line(text)
    return {'id': '', 'title': '', 'content': text, 'tags': '', 'enabled': True}


def update(entry_id, **kw):
    try:
        idx = int(entry_id)
    except (TypeError, ValueError):
        return None
    lines = load_lines()
    if not (0 <= idx < len(lines)):
        return None
    new = str(kw.get('content') or lines[idx]).strip()
    lines[idx] = new
    save_lines(lines)
    return {'id': str(idx), 'title': '', 'content': new, 'tags': '', 'enabled': True}


def delete(entry_id):
    try:
        idx = int(entry_id)
    except (TypeError, ValueError):
        return False
    return remove_line(idx)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == '--add':
        print('已添加' if add_line(' '.join(sys.argv[2:])) else '已存在或为空')
    elif len(sys.argv) > 1 and sys.argv[1] == '--reset':
        print(f'已清空，剩 {replace_all("")} 条')
    else:
        lines = load_lines()
        print(f'共有 {len(lines)} 条：')
        for i, x in enumerate(lines):
            print(f'  {i}. {x}')
        print()
        print('注入预览：')
        print(render_for_prompt({'kb_enabled': True}) or '（空）')
