#!/usr/bin/env python3
"""监听器共享配置：关键词 / 窗口天数 / 曝光上限。
网页改这个文件，comment_watcher 每轮重新读取（热生效，不用重启）。
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / 'watcher_config.json'

DEFAULTS = {
    'keyword': 'exposure',     # 标记里的关键词，例如 <exposure:300>
    'pattern': '',             # 高级：自定义正则（含 1 个捕获组）；留空则用 keyword 生成
    'window_days': 7,          # 只处理最近 N 天内的帖子
    'reply_window_days': 2,    # 只处理「启动时刻起 N 天内」产生的评论（防启动时刷屏历史评论）
    'reply_grace_minutes': 60,  # 容差：启动前 N 分钟内的评论也算有效（服务器重启不丢刚发的评论）
    'daily_cap_per_feed': 800,  # 同一帖子每天最多刷多少曝光（封号主因就是单帖暴涨）
    'boost_min_interval': 120,  # 两次刷量之间最少间隔秒数
    'boost_workers': 4,         # 刷量并发线程数（越低越慢越安全）
    'boost_batch_size': 20,     # 每批发多少条
    'boost_batch_delay': 3.0,   # 每批之间停顿秒数
    'list_page_delay': 1.5,     # 拉圈子列表时每页之间的停顿秒数
    'api_jitter': 0.2,          # 每次请求的随机抖动秒数（避免等间隔特征）
    'halt_on_ban': True,        # 兼容旧字段（等价于同时停刷量+回复）
    'halt_boost_on_ban': False, # 封禁后是否停止刷量（实测封号仍计曝光 → 默认继续）
    'halt_reply_on_ban': True,  # 封禁后是否停止回复（必停，接口直接拒绝）
    'max_exposure': 50000,     # 单条评论可要求的曝光上限
    'auto_reply': False,       # 处理完是否自动回复该评论
    'reply_template': '已处理，+{n} 曝光',   # 回复内容模板，{n}=要求曝光 {feed}=帖子ID

    # ---- AI 自动回复（OpenAI 兼容接口）----
    'ai_enabled': False,          # 开启后用 AI 生成回复，替代上面的固定模板
    'ai_base_url': '',            # 例：https://api.deepseek.com/v1
    'ai_api_key': '',             # 密钥
    'ai_model': '',               # 例：deepseek-chat / gpt-4o-mini
    'ai_system_prompt': '',       # 留空用内置人格
    'ai_max_len': 60,             # 回复最大字数
    'ai_reply_mode': 'trigger_only',  # trigger_only=只回 <exposure:N>；all=回所有新评论
    'ai_skip_own': True,          # 跳过自己账号发的评论
    'one_reply_per_feed': True,   # 同一帖子只发一条 AI 评论（避免刷屏）
    'reply_all_feeds': True,      # 【总开关】每篇帖子都发一条顶层评论（不看内容）
    'feed_mention_reply': False,  # 旧开关：只对提到关键词的帖子回复（reply_all_feeds 关闭时才生效）
    'feed_reply_hourly_cap': 10,  # 每小时最多发多少条顶层评论（0 = 不限）
    'feed_reply_only_after_start': True,  # 只评论「服务器启动之后发布」的帖子，不往回翻
    'dm_enabled': True,          # 私聊自动回复总开关
    'dm_pull_limit': 100,        # 每次拉取的消息条数
    'dm_daily_cap': 50,          # 每天最多自动回复多少条私聊（0 = 不限）
    'dm_max_len': 50,            # 私聊回复字数上限（比帖子宽松，避免截成半句）
    'dm_reply_template': '在的，稍等',   # AI 失败时的兜底文案
    'dm_skip_keywords': '',      # 命中这些词就不回（逗号分隔）
    'kb_enabled': True,          # 是否把本地知识库注入 AI  prompt
    'kb_top_k': 6,               # 最多注入几条
    'kb_max_chars': 1200,        # 注入内容的字符上限
    'mention_keywords': '大肥鱼,肥鱼,建院大肥鱼',  # 触发词，逗号分隔
}


def load():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except json.JSONDecodeError:
            pass
    return cfg


def save(cfg):
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    try:
        merged['window_days'] = max(1, min(int(merged['window_days']), 60))
    except (TypeError, ValueError):
        merged['window_days'] = DEFAULTS['window_days']
    try:
        merged['max_exposure'] = max(1, min(int(merged['max_exposure']), 5_000_000))
    except (TypeError, ValueError):
        merged['max_exposure'] = DEFAULTS['max_exposure']
    try:
        merged['boost_workers'] = max(1, min(int(merged['boost_workers']), 32))
    except (TypeError, ValueError):
        merged['boost_workers'] = DEFAULTS['boost_workers']
    try:
        merged['boost_batch_size'] = max(1, min(int(merged['boost_batch_size']), 500))
    except (TypeError, ValueError):
        merged['boost_batch_size'] = DEFAULTS['boost_batch_size']
    for fk in ('boost_batch_delay', 'list_page_delay', 'api_jitter'):
        try:
            merged[fk] = max(0.0, min(float(merged[fk]), 60.0))
        except (TypeError, ValueError):
            merged[fk] = DEFAULTS[fk]
    try:
        merged['reply_grace_minutes'] = max(0, min(int(merged['reply_grace_minutes']), 1440))
    except (TypeError, ValueError):
        merged['reply_grace_minutes'] = DEFAULTS['reply_grace_minutes']
    try:
        merged['reply_window_days'] = max(0, min(int(merged['reply_window_days']), 30))
    except (TypeError, ValueError):
        merged['reply_window_days'] = DEFAULTS['reply_window_days']
    try:
        merged['ai_max_len'] = max(4, min(int(merged['ai_max_len']), 500))
    except (TypeError, ValueError):
        merged['ai_max_len'] = DEFAULTS['ai_max_len']
    # 布尔归一
    for k in ('auto_reply', 'ai_enabled', 'ai_skip_own'):
        v = merged.get(k)
        merged[k] = v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'yes', 'on')
    merged['keyword'] = str(merged.get('keyword') or DEFAULTS['keyword']).strip() or DEFAULTS['keyword']
    merged['pattern'] = str(merged.get('pattern') or '').strip()
    CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    return merged


def build_regex(cfg=None):
    """返回编译好的正则（含 1 个数字捕获组）。"""
    cfg = cfg or load()
    pattern = cfg.get('pattern') or ''
    if pattern:
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error:
            pass  # 自定义正则非法时回落到关键词模式
    kw = re.escape(cfg.get('keyword') or DEFAULTS['keyword'])
    return re.compile(r'[<＜]\s*' + kw + r'\s*[:：]\s*(\d{1,7})\s*[>＞]', re.IGNORECASE)


def describe(cfg=None):
    """人类可读的当前规则说明。"""
    cfg = cfg or load()
    if cfg.get('pattern'):
        return f'正则 {cfg["pattern"]}'
    return f'<{cfg["keyword"]}:数字>'


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--keyword')
    ap.add_argument('--pattern')
    ap.add_argument('--days', type=int)
    ap.add_argument('--max-exposure', type=int)
    ap.add_argument('--show', action='store_true')
    a = ap.parse_args()
    cfg = load()
    for k, v in (('keyword', a.keyword), ('pattern', a.pattern),
                 ('window_days', a.days), ('max_exposure', a.max_exposure)):
        if v is not None:
            cfg[k] = v
    if any(v is not None for v in (a.keyword, a.pattern, a.days, a.max_exposure)):
        cfg = save(cfg)
        print('已保存:', json.dumps(cfg, ensure_ascii=False))
    if a.show or not any(v is not None for v in (a.keyword, a.pattern, a.days, a.max_exposure)):
        print('当前配置:', json.dumps(cfg, ensure_ascii=False))
        print('生效规则:', describe(cfg))
