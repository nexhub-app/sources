# 排障手册：症状 → 根因 → 修法

排障顺序永远是「先定位是哪一段空，再改那一段」，不要整份重写。

## 0. 定位手段

| 手段 | 用法 |
|---|---|
| 源 JSON 自检 | `python scripts/validate_source.py 源.json` —— 抓字段级错误 |
| 站点探测 | `python scripts/probe_site.py <该端点URL>` —— 看直连能不能拿到内容、有没有反爬 |
| App 诊断日志 | 解析失败时 App 会记录端点、URL、返回条数；先看「URL 对不对」再看「选择器对不对」 |
| 二分法 | 把 `selectors` 只留 `list` + `title`，能出标题就说明容器对，再逐个加字段 |
| 手动验证 | 把日志里打印的真实 URL 粘到浏览器，确认页面结构和你写的一致 |
| 存活判定 | 看返回体：几百字节 + `Welcome to nginx` / Apache 默认页 = 域名已弃用（见 §0.1） |
| 选择器自测 | 用 lxml 在真实 HTML 上跑源里的 XPath（见 §0.2），不用等真机 |

### 0.1 先判生死：站点还在不在

| 返回 | 判定 | 处置 |
|---|---|---|
| 2xx + 几百字节 + `Welcome to nginx!` / `Apache2 Default Page` / `It works!` | 域名已弃用或站点搬走 | 别改解析。找新域名；无解就 `deprecated: true` + `migrationMessage` 说清原因 |
| 2xx + 首页正常，但某个前缀（常见 `/search/`）返回「安全验证」/滑块/CAPTCHA | 该端点有验证墙 | 该端点 `overrides.type = webview-html`，用户手动过一次（见 §0.2） |
| 2xx + 只有骨架、正文密度 <2% | 前端渲染 | 见 `site-patterns.md` 的 SPA 路线 |
| 502/521/`Failed to read origin site` | 源站挂了或拒绝机房 IP | 先换网络重试，别急着改源 |
| 301/302 到别的域名 | 站方换域 | 把新域写进 `site.baseUrl` + `mirrors` |

> 判定顺序永远是「站 → 端点 → 结构 → 字段」。跳过第一步会在死站上白改一整天。

### 0.2 验证墙（滑块 / 图形码 / Cloudflare）

- 正确处理：`overrides.<端点>.type = "webview-html"`，App 会拉起内嵌浏览器，用户手动过一次，之后同一会话内复用（`WebViewHtmlCache` 按 源+路由+URL 缓存）。
- **不要**写自动过验证的脚本：滑块/图形码本就是拦机器人的，自动化既不可靠也越界。
- 只拦一个端点时，只给那一个端点配 `webview-html`；不要顺手 `useWebview: true`（它只管 video 路由，对列表无效，还可能改变播放路径）。
- 验证页通常仍是 200，靠正文特征识别：`安全验证` / `sliderRange` / `verify_check` / `Just a moment`。

### 0.3 用 lxml 自测选择器（免真机）

```python
import json, lxml.html
sel = json.load(open('源.json'))['selectors']['search']
doc = lxml.html.parse('页面.html').getroot()
nodes = doc.xpath(sel['list'])

def pick(el, expr):
    v = el.xpath(expr)
    if isinstance(v, str):      # 关键：字符串结果不能再取 [0]
        return v
    return v[0] if v else ''

ids = [pick(el, sel['id']) for el in nodes]
assert len(nodes) >= 10 and len(set(ids)) == len(nodes), '容器或 id 选择器不对'
```

> 坑：`el.xpath('substring-before(...)')` 返回**字符串**，写成 `v[0]` 会只拿到首字符（表现为「每张卡片 id 都是 5」）。

## 1. 导入与应用层

| 症状 | 根因 | 修法 |
|---|---|---|
| 导入无反应 / 提示校验失败 | 缺 `id` / `name` / `site.baseUrl`，或 `animeSource` 没有 `latest` 路由 | 补齐；跑 validator |
| 导入成功但没覆盖旧源 | `version` 小于已装版本 | 把 `version` +1 |
| 改了内置源没生效 | `plugins/builtin/*.json` 被 .gitignore，且需重编译 | 提升 `version` 后重新构建安装 |
| 源列表里看不到 | `enabled: false` / `isHidden: true` / `ageRating: mature` 且开了年龄限制 | 逐个检查 |

## 2. 首页 / 搜索（列表为空或卡片缺字段）

| 症状 | 根因 | 修法 |
|---|---|---|
| 列表 0 条 | `selectors.<端点>.list` 没写或写错（默认 `div.item`） | 用 probe 的「高频 class」挑容器，写成 `.class` 或 `ul li` |
| 列表有卡片但没封面 | 图片懒加载，`src` 是占位图 | 改 `img@data-src, img@src` |
| 有卡片但点了没反应 | `detailUrl` 是相对地址且 `id` 不是链接 | `detailUrl` 取 `a@href`；`detail` 路由保持 `{detailUrl}` |
| 每张卡点进去都是同一部 | 详情路由没有 `{id}` / `{detailUrl}` 占位符 | 补占位符 |
| 卡了广告条目 | 广告卡的 `id` 和 `title` 都能抓到 | 收紧容器选择器，别用 `div` 这种大范围 |
| 搜索永远空 | 搜索参数名不对（`q` / `wd` / `keyword` / `searchword`） | 读首页 `<form action>` 与 `input name`（probe 会打印），别猜 |
| 搜索页 404 / `System Error` | 地址形态不对（`?s=`、`/search/{kw}.html` 各有站点不支持） | 见 `site-patterns.md`「搜索地址四种形态」逐个排除 |
| 搜索页返回「安全验证」 | 该端点有验证墙 | 该端点改 `webview-html`，用户手动过验证（§0.2） |
| 搜索有结果但点进去错乱 | `id` 取错（整串 URL 或首字符） | 用 `substring-before(substring-after(@href,'/vod/'),'.html')` 精确截取 |
| 搜索第一页正常、第二页重复 | 页码从 0 开始或参数名是 `p` / `offset` | 用 `{page-1}` 或改参数名 |

## 3. 详情页

| 症状 | 根因 | 修法 |
|---|---|---|
| 详情页整页空白 | 详情路由 URL 拼错（典型：拼出双 host） | `detail` 路由写 `{detailUrl}`；`video` 路由写 `{url}` |
| 标题/简介缺失 | 选择器是上一版页面结构 | 加 meta 兜底：`//meta[@property='og:title']/@content` |
| 标签只出一个 | 用的是单值取值 | 标签选择器指向容器内多个 `a`，引擎会合并 |
| Cloudflare 站详情打不开 | 还是直连 | 该端点改 `webview-html` + `useWebview: true` |

## 4. 目录 / 选集

| 症状 | 根因 | 修法 |
|---|---|---|
| 目录 0 条 | 目录在另一个页面（`toc` 页） | 加 `toc` 路由指向目录页；或 `chapters.url` 直接指向目录页 |
| 章节标题是一串乱码/带日期 | 选择器命中了错误的节点 | 用 `a@text` 精确到链接文本 |
| 点章节进不去 | `url` 为相对地址但没被补全 | `chapters` 的 `id` 取 `a@href`，`images` 路由用 `{chapterId}` |
| 章节顺序反了 | 站点本身倒序 | 用脚本 `return list.reverse()` |

## 5. 图片 / 正文

| 症状 | 根因 | 修法 |
|---|---|---|
| 图片 0 张 | 阅读页图片由 JS 插入 | 端点改 `webview-html`；或脚本 `__webview: true` |
| 图片全是占位图 / 5KB 小图 | 防盗链 | `antiHotlinking.referer` 填源站 origin |
| 图片顺序乱 | 容器里混了广告/头像 | 收紧 `images` 选择器到正文容器内 |
| 图片是碎块 | 站点切片 | 用 `imageTransform` 或 `config.mode` |
| 正文夹广告 | 站点在正文里插了 div | 书源用 `##正则` 清；或 content 脚本 `context.content.clean` |

## 6. 播放

| 症状 | 根因 | 修法 |
|---|---|---|
| 播放页打不开 | `video` 路由不是 `{url}` | 改成 `{url}` |
| 拿到的是网页地址而不是视频 | 用的是 `builtin` 直连，播放页里本来就没有 `<video>` | 改 `webview` + IIFE 脚本 |
| 直链 403 / 黑屏 | 缺 Referer / UA / Cookie | `antiHotlinking` 补 referer；或脚本返回 `{url, headers}` |
| 只有一条线路 | 站点多线路没解析 | 脚本返回 `{url, lines:[{name,url}]}` |
| 视频地址几分钟后失效 | 签名直链 | 正常现象；播放器重试会重新解析（缓存 5 分钟） |
| m3u8 一直转圈 | 分片也要鉴权头 | 脚本返回的 `headers` 会随播放器请求带上，务必给全 |

## 7. 脚本类

| 症状 | 根因 | 修法 |
|---|---|---|
| 脚本返回空 | 入口函数名不匹配 | 见 `script-protocol.md` §1 |
| `ctx is not defined` | 用了别家阅读器的 API 名 | 全局改 `context` |
| 返回 `[object Promise]` | async / 未 await | 改 `__meta` 两步 |
| 报超时 | 串行请求太多 | `__fetchUrls` 批量 + `__fetchConcurrency` |
| 首次正常、第二次空 | 脚本依赖模块级变量 | 用 `context.storage` |

## 8. 改动纪律

1. 一次只改一处，改完立刻验证同一段（别连改 5 个字段再去试）。
2. 修好的源记得 `version` +1 再给用户。
3. 不要把「探测通了」当成「App 里通了」：App 走的是源的网络配置 + 防盗链头 + WebView 验证，三者沙箱都模拟不了，**真机验收才算过**。
