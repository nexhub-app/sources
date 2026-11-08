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
| 引擎能力探针 | lxml 的 XPath 是全集、App 引擎是子集；lxml 测过不代表 App 能用。终极手段：在主仓库里放个临时脚本 `dart run`（项目自带 XPath 引擎依赖），对真实 HTML 跑候选选择器，直接打出每条命中数——App 引擎的行为（含静默 0 条）只有它说了算 |

### 0.1 先判生死：站点还在不在

| 返回 | 判定 | 处置 |
|---|---|---|
| 2xx + 几百字节 + `Welcome to nginx!` / `Apache2 Default Page` / `It works!` | 域名已弃用或站点搬走 | 别改解析。找新域名；无解就 `deprecated: true` + `migrationMessage` 说清原因 |
| 2xx + 首页正常，但某个前缀（常见 `/search/`）返回「安全验证」/滑块/CAPTCHA | 该端点有验证墙 | 该端点 `overrides.type = webview-html`，用户手动过一次（见 §0.2） |
| 2xx + 几百字节小页 + 标题「请稍候」类 + 内联脚本写 cookie 后自跳转 | 该端点的 **JS 自动挑战**（无人工要素） | 走脚本两步现取令牌（见 §0.4），**不要**开 webview |
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
>
> 更大的坑：**lxml 全都支持，App 引擎是子集**。节点集谓词（`li[.//img]`、`li[a]`、`li[contains(.,'x')]`）、`and` 组合谓词，lxml 全部能过，App 里全部静默 0 条。lxml 验证只证明「选择器语义对」，不证明「App 引擎吃这个写法」——写法对照 `selectors.md` 的谓词能力边界表，拿不准就上引擎能力探针。

### 0.4 JS 自动挑战（200 小页面、无人工要素的拦截页）

与滑块/图形码（§0.2）同属端点级拦截，但**无人工要素**：拦截页仍是 200、只有
几百字节，标题多为「请稍候」类；内联脚本 `document.cookie` 写一个挑战 cookie，
再带一个附加查询参数自跳转（`location.replace(原URL+参数)`），常伴自定义响应头
（`X-*-Verify` 类）。浏览器里脚本执行完即自动放行——这类挑战**不该开 webview**
（慢且依赖浏览器环境健康度），用脚本两步协议在直连层自愈：

1. 首跳（引擎预取路由）拿到拦截页 → 入口脚本识别挑战特征（在页面里找挑战
   cookie 的名字），**当场提取新鲜令牌**，返回 meta 描述符。
2. `__fetchUrl` = 原端点 URL + 挑战要求的附加参数（通常任意值即可）；
   `__fetchHeaders` 带 `Cookie: <挑战cookie名>=<令牌>`；`__fetchResponseType:
   'text'`；`__processor` 交给列表解析函数。
3. 令牌每次现取，站点轮换也不怕——**绝不把令牌写死进 JSON**。

```js
function parseX(raw, context) {
  var list = parseList(raw, context);        // 先按真实结果页解析
  if (list.length > 0) return list;          // 会话已暖 → 单跳直出
  var m = /challenge_cookie=([0-9a-f]{8,})/.exec(String(raw || ''));
  if (!m) return list;                       // 非挑战页（真异常）→ 空列表
  return {
    __meta: true,
    __fetchUrl: context.baseUrl + '/search?kw='
        + encodeURIComponent(context.keyword || '') + '&_challenge_pass=1',
    __fetchHeaders: { 'Cookie': 'challenge_cookie=' + m[1] },
    __fetchResponseType: 'text',
    __processor: 'parseList'
  };
}
```

前置条件与校验：

- 引擎必须「显式请求头与会话 jar 按名合并、同名显式优先」。旧实现里显式
  `Cookie` 会被 jar 回带（PHP 会话每页都下发）整条顶掉，二跳永远带不上令牌
  ——**二跳仍返回拦截页时先查这一条**。
- 列表解析在脚本里做（script 端点返回最终数组），口径照抄声明式选择器：
  容器块切分 → 图锚的 `title`/`href` → 封面 `data-src` 优先、占位图排除。
- `context.keyword` 是**未编码**的原始搜索词，拼 URL 必须
  `encodeURIComponent`（路由 `{keyword}` 的编码只发生在占位符替换时）。
- 验证边界：挑战参数取任意值都能过、连续搜索无频控，可直接 curl 复核；
  若站方后续把挑战升级出真人工要素，退回 §0.2 的 webview-html。

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
| 列表 0 条，但页面里肉眼能看到条目 | `list` 用了 XPath **节点集谓词**（`li[.//a[...]]` / `li[a]` / `li[contains(.,'x')]`）或 `and` 组合——引擎不支持且**静默返回 0** | 把条目定成叶子锚点直接选：`//容器//a[卡片类]`，字段改成锚点自身 `@title` / `@href` 截取（见 `selectors.md` 谓词能力边界） |
| 列表 0 条、换端点数量差异大 | 同模板族里分类页与搜索页条目包裹不同（li 网格 vs 另一种卡片） | 每个端点分别实抓实测；叶子锚点写法常一套通吃 |
| 列表有卡片但没封面 | 图片懒加载，`src` 是占位图 | 改 `img@data-src, img@src` |
| 有卡片但点了没反应 | `detailUrl` 是相对地址且 `id` 不是链接 | `detailUrl` 取 `a@href`；`detail` 路由保持 `{detailUrl}` |
| 每张卡点进去都是同一部 | 详情路由没有 `{id}` / `{detailUrl}` 占位符 | 补占位符 |
| 卡了广告条目 | 广告卡的 `id` 和 `title` 都能抓到 | 收紧容器选择器，别用 `div` 这种大范围 |
| 搜索永远空 | 搜索参数名不对（`q` / `wd` / `keyword` / `searchword`） | 读首页 `<form action>` 与 `input name`（probe 会打印），别猜 |
| 搜索页 404 / `System Error` | 地址形态不对（`?s=`、`/search/{kw}.html` 各有站点不支持） | 见 `site-patterns.md`「搜索地址四种形态」逐个排除 |
| 搜索页返回「安全验证」 | 该端点有验证墙 | 该端点改 `webview-html`，用户手动过验证（§0.2） |
| 搜索 200 但只有几百字节「请稍候」小页 | 端点有 JS 自动挑战（无人工要素，内联写 cookie 自跳转） | 脚本两步现取令牌二跳（§0.4），别开 webview |
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
| 脚本源封面全挂、图片直开却 200 | 脚本返回相对路径封面；图片层把非 http(s) 一律当本地文件，**永不发请求**（诊断铁证：图片缓存索引里该源 0 条记录） | 脚本内补全绝对地址（列表+详情两处），见 `script-protocol.md` §6 |
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
| **一部分影片能播、一部分永久转圈** | 聚合资源站：详情页聚合多家第三方资源「线路」，各线路独立 CDN、寿命不一（500 / 域名消失 / 连接挂起都会见到），站点默认线路常先死。死 CDN 上游无解，站点网页端自己也播不了 | `parseVideo` 做**探活**（§6.1）；注意单线路影片若上游已死则无解，不要误判成解析 bug |
| curl 一切正常、App 里黑屏转圈 | 差异在解析流程或播放器装配，不在网络 | 按 §6.2 分层定位 |

### 6.1 聚合资源站多线路探活（`__meta` 两跳，站点无关式样）

这类站点播放页 URL 是三段式 `{id}-{line}-{ep}`，**换 line 段就是同集数换线路**；播放页上会列出全部线路的同集数链接。线路是否存活只能靠探测（HTTP 拉一次 m3u8 文本，`#EXTM3U` / `#EXTINF` 视为存活；500 / DNS 失败 / 挂起都会以异常或 null 形式出现在批量预取结果里）。式样：

```js
var CANDS = []; // 跨跳共享：同一条 meta 链内引擎实例不销毁
function parseVideo(raw, context) {
  var now = extractNow(raw);                    // 本线路直链（var now= 或全页正则兜底）
  CANDS = now ? [now] : [];
  var sibs = siblingPages(raw, context.url);    // 按 {id}-{line}-{ep} 换 line 段推导其余线路页
  if (!sibs.length) return now || '';           // 单线路：无 alternate，保持旧行为
  return { __meta: true, __fetchUrls: sibs, __fetchResponseType: 'text', __processor: 'pickPageNow' };
}
function pickPageNow(raw, context) {            // 跳1回：各线路播放页文本（失败项为 null）
  var bodies = Array.isArray(raw) ? raw : [raw];
  for (var i = 0; i < bodies.length; i++) {
    var u = extractNow(bodies[i]);
    if (u && CANDS.indexOf(u) < 0) CANDS.push(u);
  }
  if (CANDS.length <= 1) return CANDS[0] || ''; // 单候选不必探（没有替代者）
  return { __meta: true, __fetchUrls: CANDS.slice(0), __fetchResponseType: 'text', __processor: 'pickLive' };
}
function pickLive(raw, context) {               // 跳2回：各候选 m3u8 文本，失败项为 null
  var bodies = Array.isArray(raw) ? raw : [raw];
  for (var i = 0; i < bodies.length; i++) {
    var b = String(bodies[i] == null ? '' : bodies[i]);
    if (/^\s*#EXTM3U/.test(b) || b.indexOf('#EXTINF') >= 0) return CANDS[i];
  }
  return CANDS[0] || '';                        // 全死回退本线路原链，别返回空
}
```

要点：当前线路直链放 CANDS[0]——存活即原样返回，探活只在必要时付出代价；批量预取并发完成，单条失败填 null 不中断整批；站点对快速连发可能弹验证墙，批量结果整批为 null 时自然回退本线路原链，属可接受降级。

### 6.2 「curl 全通但 App 黑屏」分层定位

1. **单 URL 层**：curl 拉直链（主清单→子清单→随机抽几个分片，换 `-A` UA / 加 / 不加 Referer 各试一遍），确认资源本身活着。
2. **播放内核层**：用 App 自带的 libmpv 动态库直接驱动（ctypes：`mpv_create → set_option_string`（复刻应用装配的全部属性，尤其 `demuxer-lavf-format=hls` 与 `demuxer-lavf-o` 里的 `protocol_whitelist`——漏了它复刻就不算数）`→ loadfile → mpv_wait_event` 循环收 log / end-file reason）。比 curl 更接近真相：能暴露 500、DNS 失败、TLS 链、挂起这四类死法。
3. **多采样**：换 3-4 部不同影片（不同时期上传）各走一遍——聚合站按影片/线路轮换 CDN 家族，一部能播不代表全站能播。
4. **崩溃日志**：控制台输出会被截断，落盘的崩溃日志（应用数据目录 `crash_log.txt`）里有完整的 Flutter 异常——转场黑掉、点击没反应这类「看起来像播放问题」的故障，真凶常在这里（例：空 id 条目让多张卡片共用同一 Hero 标签 → 转场抛 "multiple heroes share the same tag"，表现为点卡片没反应/闪红）。
5. **解析流程层**：以上都干净再查解析（脚本→meta 链→播放器 open 路径），看解析日志里直链有没有被中间层改写。

## 7. 脚本类

| 症状 | 根因 | 修法 |
|---|---|---|
| 脚本返回空 | 入口函数名不匹配 | 见 `script-protocol.md` §1 |
| `ctx is not defined` | 用了别家阅读器的 API 名 | 全局改 `context` |
| 返回 `[object Promise]` | async / 未 await | 改 `__meta` 两步 |
| 报超时 | 串行请求太多 | `__fetchUrls` 批量 + `__fetchConcurrency` |
| 首次正常、第二次空 | 脚本依赖模块级变量 | 用 `context.storage` |
| 预取 200 数据完整、处理器恒 `List[0]` | 处理器把旧引擎的打包数组 `[响应体, 响应头]` 当响应体，顶层没有 `data` | 处理器开头形态归一（`script-protocol.md` §3） |
| 列表/搜索全空、离线沙箱与真机结论相反 | 沙箱直接喂响应体，真机旧引擎喂的是打包数组——离线复现要喂同形态 | 同上；归一后两形态通吃 |
| 依赖令牌的端点第一跳只有空壳（200 + code/msg 齐全但 `data=null`） | 路由级预取不带脚本 storage 里现取的令牌，只带声明式鉴权 | 正常态；带权取流走 `__meta` 二跳 + `__fetchHeaders`（`script-protocol.md` §3） |

## 8. 改动纪律

1. 一次只改一处，改完立刻验证同一段（别连改 5 个字段再去试）。
2. 修好的源记得 `version` +1 再给用户。
3. 不要把「探测通了」当成「App 里通了」：App 走的是源的网络配置 + 防盗链头 + WebView 验证，三者沙箱都模拟不了，**真机验收才算过**。
