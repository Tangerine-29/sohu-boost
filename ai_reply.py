#!/usr/bin/env python3
"""AI 自动回复：调 OpenAI 兼容接口生成回复内容。

零第三方依赖，只用 urllib。任何 OpenAI 兼容服务都能用：
    OpenAI        https://api.openai.com/v1
    DeepSeek      https://api.deepseek.com/v1
    Moonshot      https://api.moonshot.cn/v1
    TokenAI 等聚合 https://<你的网关>/v1
    本地 Ollama   http://127.0.0.1:11434/v1
"""

import json
import time

import token_stats
import urllib.error
import urllib.request

DEFAULT_SYSTEM = (
    "你是「建院大肥鱼」，狐友校园社区（贵州建设职业技术学院圈）里的老用户，"
    "男生，说话接地气、嘴贫、爱玩梗，像宿舍里那个贫但靠谱的哥们。\n\n"
    "硬性要求：\n"
    "1. 每次回复不超过 18 个字，一句能说完绝不说第二句\n"
    "2. 用口语，可以用校园梗/网络梗，但别硬凹、别每句都塞梗\n"
    "3. 必须结合上面给的帖子内容和对方那句话来回，不要答非所问\n"
    "4. 不暴露自己是 AI 或机器人，不说「自动回复」「已处理」这类机制词\n"
    "5. 不加引号、不写「回复：」这种前缀、不换行\n"
    "6. 最多一个 emoji，也可以不用\n"
    "7. 只输出你要说的那一句话本身：不要解释、不要复述要求、"
    "不要写「用户要…」「我要…」「这条回复…」这类旁白"
)


def chat(base_url, api_key, model, messages, timeout=25, temperature=0.85):
    """调用 chat/completions，返回回复文本；失败抛异常。"""
    url = base_url.rstrip('/') + '/chat/completions'
    payload = json.dumps({
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': 400,
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        # Cloudflare 会拦 Python 默认 UA（403 error 1010），伪装成浏览器
        'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/131.0.0.0 Safari/537.36'),
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    last_exc = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8', 'replace'))
            break
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    else:
        raise last_exc if last_exc else RuntimeError('重试耗尽')
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError(f'接口无 choices: {str(data)[:160]}')
    msg = choices[0].get('message') or {}
    # 记录 token 消耗
    try:
        token_stats.record_usage(data.get('usage'), model)
    except Exception:  # noqa: BLE001
        pass
    # 只取 content，reasoning_content 是思考链，不能当回复用
    return str(msg.get('content') or '').strip()


META_HINTS = (
    '用户要', '用户说', '要针对', '这条回复', '结合帖子', '人设是',
    '字内', '回复先生成', '我需要', '我们应该', '让我', '首先',
)


def looks_like_reasoning(text):
    """判断是不是模型把思考过程写进 content 了。"""
    if not text:
        return False
    t = text.strip()
    hits = sum(1 for k in META_HINTS if k in t)
    # 命中 2 个以上特征，或明显是任务复述
    return hits >= 2 or t.startswith(('用户要', '要针对', '我需要', '让我'))


def build_messages(comment_text, feed_content='', author='', extra=''):
    """上下文格式：作者名和内容拼成一行，像群聊里的「昵称:内容」。

        帖子：大家好
        下面有人回复：春柳:不好
    """
    lines = []
    if feed_content:
        lines.append(f'帖子：{feed_content[:200]}')
    if comment_text:
        name = (author or '').strip() or '有人'
        lines.append(f'下面有人回复：{name}:{comment_text[:200]}')
    if extra:
        lines.append(f'补充说明：{extra}')
    user = '\n'.join(lines) + '\n\n按你的人设，针对那条回复回一句：'
    return [
        {'role': 'system', 'content': DEFAULT_SYSTEM},
        {'role': 'user', 'content': user},
    ]


META_HINTS = (
    '用户要', '用户说', '要针对', '这条回复', '结合帖子', '人设是',
    '字内', '回复先生成', '我需要', '我们应该', '让我', '首先',
)


def looks_like_reasoning(text):
    """判断是不是模型把思考过程写进 content 了。"""
    if not text:
        return False
    t = text.strip()
    hits = sum(1 for k in META_HINTS if k in t)
    # 命中 2 个以上特征，或明显是任务复述
    return hits >= 2 or t.startswith(('用户要', '要针对', '我需要', '让我'))



def generate(cfg, comment_text, feed_content='', author='', extra='', retries=2):
    """按配置生成一条回复。返回 (ok, text_or_error)。"""
    base = (cfg.get('ai_base_url') or '').strip()
    key = (cfg.get('ai_api_key') or '').strip()
    model = (cfg.get('ai_model') or '').strip()
    if not base or not model:
        return False, '未配置 ai_base_url / ai_model'
    system = (cfg.get('ai_system_prompt') or '').strip() or DEFAULT_SYSTEM
    msgs = build_messages(comment_text, feed_content, author, extra)
    msgs[0]['content'] = system
    limit = int(cfg.get('ai_max_len') or 20)

    last_err = '未知错误'
    for attempt in range(retries + 1):
        try:
            text = chat(base, key, model, msgs, temperature=0.85 + 0.1 * attempt)
        except urllib.error.HTTPError as exc:
            body = ''
            try:
                body = exc.read().decode('utf-8', 'replace')[:160]
            except Exception:  # noqa: BLE001
                pass
            last_err = f'HTTP {exc.code} {body}'
            continue
        except Exception as exc:  # noqa: BLE001
            last_err = f'{exc.__class__.__name__}: {exc}'
            continue

        text = text.replace('\n', ' ').strip().strip('"\'「」“”')
        if not text:
            last_err = '模型返回空内容'
            continue
        if looks_like_reasoning(text):
            last_err = f'返回思考过程而非回复: {text[:40]}'
            continue        # 重试
        if len(text) < 4:
            last_err = f'回复过短（{len(text)}字）: {text}'
            continue        # 重试
        return True, text[:limit]
    return False, last_err


if __name__ == '__main__':
    import argparse
    import sys
    sys.path.insert(0, '.')
    import watcher_config

    ap = argparse.ArgumentParser()
    ap.add_argument('--text', default='这条帖子写得不错')
    ap.add_argument('--feed', default='')
    ap.add_argument('--author', default='')
    args = ap.parse_args()

    cfg = watcher_config.load()
    ok, out = generate(cfg, args.text, args.feed, args.author)
    print('模型:', cfg.get('ai_model'), '| 接口:', cfg.get('ai_base_url'))
    print('结果:', ('✅ ' if ok else '❌ ') + out)
