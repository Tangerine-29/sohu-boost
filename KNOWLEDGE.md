# 知识库

给 AI 补充学校的真实信息，避免它乱编。

## 存储

`knowledge.txt`，**一行一句话**：

```txt
一食堂在教学楼东侧，早餐 6:30-9:00，二食堂在宿舍区
宿舍 23:00 关门，晚归要登记，周末 23:30
校园网 SSID 是 JZXY-WLAN，密码学号后六位
快递在体育馆西侧菜鸟驿站，营业到 21:00
```

- `#` 开头的行是注释，会被忽略
- 行首的 `-` `*` `+` 会被自动去掉
- 重复的行自动去重

## 注入方式

**全量注入**，不做检索匹配。所有行拼进 system prompt：

```
以下是本校的真实信息，回答涉及这些内容时必须以此为准，不要编造：
- 一食堂在教学楼东侧，早餐 6:30-9:00，二食堂在宿舍区
- 宿舍 23:00 关门，晚归要登记，周末 23:30
- ...
```

总长度受 `kb_max_chars` 限制（默认 1500），超出截断。

## 三种改法

### 1. 网页

监控面板 → 「知识库」→ 输入框写一句话 → 回车。

### 2. 直接编辑文件

```bash
vim /www/wwwroot/sohu-boost-deploy/knowledge.txt
```

改完下一轮自动生效，不用重启。

### 3. 命令行

```bash
# 加一句
python3 knowledge.py --add "体育馆在宿舍区南边"

# 看全部 + 注入预览
python3 knowledge.py

# 清空
python3 knowledge.py --reset
```

## API

```bash
# 列表
curl http://127.0.0.1:8790/api/kb

# 追加一句
curl -X POST http://127.0.0.1:8790/api/kb \
  -H 'Content-Type: application/json' \
  -d '{"line":"体育馆在宿舍区南边"}'

# 整体覆盖
curl -X POST http://127.0.0.1:8790/api/kb \
  -H 'Content-Type: application/json' \
  -d '{"text":"第一句\n第二句\n第三句"}'

# 改第 N 条（索引从 0 开始）
curl -X PUT http://127.0.0.1:8790/api/kb \
  -H 'Content-Type: application/json' \
  -d '{"id":"0","content":"新内容"}'

# 删第 N 条
curl -X DELETE http://127.0.0.1:8790/api/kb \
  -H 'Content-Type: application/json' \
  -d '{"id":"0"}'
```

## 配置

```json
{
  "kb_enabled": true,      // 总开关
  "kb_max_chars": 1500     // 注入字符上限
}
```

## 写什么有用

| ✅ 有用 | ❌ 没用 |
|---|---|
| 具体位置（"一食堂在教学楼东侧"）| 模糊描述（"食堂很好吃"）|
| 具体数字（"23:00 关门"）| 主观评价（"宿舍条件一般"）|
| 规则流程（"晚归要登记"）| 大家都知道的事 |
| 学校特有的名词、简称 | AI 能自己查到的通用知识 |

## 注意

- **每句话都会占用 prompt token**，写得越多成本越高
- 建议控制在 **30 行以内**（约 1000 字符）
- 内容会随每次 AI 调用一起发送
