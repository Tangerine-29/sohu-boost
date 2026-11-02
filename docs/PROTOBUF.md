# 埋点协议与 schema

曝光计数由客户端上报埋点事件驱动，不是直接调"加曝光"接口。

## 上报通道

```
POST https://opapi-ol.sns.sohu.com/openapi/pingback/log/report
Content-Type: multipart/form-data; boundary=alamofire.boundary.<16hex>
```

body 是标准 multipart，但只有一个 part：

```
--boundary
Content-Disposition: form-data; name="message"; filename="message"
Content-Type: application/octet-stream

<二进制：varint 长度前缀 + Log 消息>
--boundary--
```

## 关键点：负载不在 HTTPBody 里

用 Frida hook `setHTTPBody:` 会看到空值——因为 multipart 的 part 数据是**独立参数**传入 `uploadTaskWithRequest:fromData:` 的。

这是分析时最容易踩的坑。

## Log 消息结构

```
Log {
  publicMeta     = 1   // 设备/用户/时间
  basicMeta      = 2
  pageViewMeta   = 3   // 页面浏览
  elementViewMeta= 4   // 元素浏览
  clickMeta      = 5   // 点击
  ...
}
```

曝光对应 `pageViewMeta`，其中：

```
PageViewMeta {
  feedIdList = 8 (repeated string)   // 一次可带多个 feedId
}
```

事件类型枚举：

```
Event: E_PAGE_VIEW = 1, E_CLICK = 3
```

## schema 来源

从 Swift 二进制的 `SwiftProtobuf` 元数据静态恢复，共：

- 9 个消息
- 128 个字段
- 20 个枚举

完整结构见根目录的 [`schema.json`](../schema.json)。

## 编解码

[`payload.py`](../payload.py) 提供：

```python
encode_message(fields)      # dict → bytes
frame_message(raw)          # 加 varint 长度前缀
build_feed_detail(feed_id, public_meta)  # 构造 P_FEED_DETAIL
decode_delimited(data)      # 反向解析
```

## 计数行为

- 每上报 1 条 ≈ **+2 曝光**
- 服务端 30~100 秒批量落账
- 纯协议对 `feeds/show` 无效（读接口不计数）
