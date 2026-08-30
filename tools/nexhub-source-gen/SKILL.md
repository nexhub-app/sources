---
name: nexhub-source-gen
description: 根据 NexHub 官网「源编写教程」（21 节完整版）自动生成一个**详尽且覆盖全部功能**的源文件（plugins/builtin/*.json）。当用户说「生成/写一个源文件」「按教程出一份完整源」「帮我建一个新源（要覆盖评论/登录/网络/收藏/公告/周期表/猜你喜欢/筛选等所有功能）」时使用。本 Skill 直接产出可导入的 JSON 骨架，把每个可选功能块都列齐并标注 TODO，用户只需填真实站点规则。
type: skill
---

# NexHub 源文件生成器（代码生成 Skill）

本 Skill 把官网教程的 21 节浓缩成一份**可直接落盘的源生成器**。目标：产出一份**详尽且覆盖全部功能**的源 JSON——每个模块、每个高级块都出现在文件里（用 `TODO_xxx` 标注待填处），而非只给最小示例。

权威依据（按优先级）：
1. `lib/core/models/plugin_config.dart`（字段真值，改前必读）
2. 官网源编写教程（`assets/js/i18n.js` 的 `CONTENT.tutorial`）——本 Skill 已内联其要点
3. `lib/core/resolver/{resolver_registry,builtin_resolver,webview_resolver,script_resolver}.dart`

> 铁律：源即插件。只写 JSON，绝不把站点逻辑写进 Dart。模型会忽略未知键（如 `lang`/`builtin`），请勿当功能字段用。

---

## §1 生成工作流（调用本 Skill 时必须按此执行）

**Phase A — 收集事实**（信息不足时向用户提问，不要瞎猜）
向用户确认或自行推断以下事实，至少拿到：源类型、站点主域名/baseUrl、是否强反爬/Cloudflare、响应格式（html/json）。其余事实（登录方式、有无评论、有无周更表等）用 §3 清单逐项确认，缺省则保留对应块为 `TODO_` 占位。

**Phase B — 选模板**
- 影视/动漫 → `animeSource` 模板（§5.1）
- 漫画 → `mangaSource` 模板（§5.2，多 chapters/images 两端点）
- 小说 → `novelSource` 模板（§5.3，Legado 兼容字段，不用顶层 id/name/type/site）

**Phase C — 填真实字段**
把用户提供的真实域名、路由 URL、选择器替换掉 `TODO_` 占位。`responseType` / `useWebview` / `parser.overrides.*` 按站点反爬强度定。

**Phase D — 补全高级块**
按 §3 逐项决定保留/删除：每个高级块（comments/login/network/webFavorite/announcement/schedule/recommend/filters/antiHotlinking）要么填真实值，要么整块删掉（不要留空 `TODO_` 上线）。

**Phase E — 写出 + 校验**
1. 用 Write 工具写到 `plugins/builtin/<id>.json`（id 用小写，建议 `域名_类型`，如 `demo_anime`）。
2. 跑 `python -c "import json; json.load(open('plugins/builtin/<id>.json'))"` 确认 JSON 合法。
3. 提醒用户本机跑 `flutter analyze lib` 与真机导入验证（沙箱无 Flutter）。
4. 上线前 `grep` 确认无禁用仓库名（见 ARCHITECTURE_BASELINE）。

---

## §2 何时必须问用户（不要自作主张）

- 站点真实域名 / baseUrl（无则无法拼相对链接）
- 是否强反爬（决定 `useWebview` 与 `overrides.type`：webview / webview-html）
- 是否需要登录、评论、周更表、网络收藏、源公告、筛选——这些决定高级块是否保留
- 响应格式 html 还是 json（决定选择器语法 jsonpath / css / xpath）

---

## §3 事实采集清单（逐块确认，决定保留哪些高级功能）

| 块 | 是否常用 | 触发保留的条件 | 关键字段 |
|---|---|---|---|
| `comments` | 中 | 源站有评论区 | provider(source/bangumi)、routes.list(必需)、selectors、login |
| `comments.login` | 中 | 评论/收藏要登录 | url(WebView登录) / checkCookie / checkUrl+loggedInSelector / sendTokenAs(bearer\|key) |
| `network` | 中 | 站点被 SNI/GFW 拦、需自定义 hosts/sni | proxy/dns/hosts/sni/ech（缺省继承全局） |
| `webFavorite` | 低 | 源站有「我的书架」网页 | route/url、addRoute/addUrl、requireLogin |
| `announcement` | 低 | 作者要发公告 | title(必填)、body、url、updatedAt |
| `homeSections[style:schedule]` | 中 | 有周更表 | route 同名 week 路由 + 星期字段 |
| `recommend`/`related` 路由 | 中 | 详情页要「猜你喜欢」 | routes.recommend 或 selectors.detail.recommendations(漫画) |
| `filters` | 中 | 分类页有多维筛选 | groups / byCategory / defaults |
| `antiHotlinking` | 中 | 图片/视频防盗链 | referer / headers / userAgent |
| `webviewConfig` | 低 | useWebview 时调超时/广告拦截 | adblock、timeoutSeconds |
| `stealthMode` | 低 | 要更激进反检测 | true/false |
| `deprecated` / `migrationMessage` | 低 | 源弃用迁移提示 | deprecated、migrationMessage |

---

## §4 字段完整参考（浓缩自官网教程 21 节）

### 顶层必填 / 常用
- `id`：唯一标识，建议 `域名_类型`；同名按 version 升级/跳过。
- `name`：显示名。
- `author`：可选，显示在源详情（致谢用）。
- `version`：整数（强制转 int，默认 1）；导入时 ≥ 已装才覆盖。
- `type`：`animeSource` / `mangaSource` / `novelSource`。
- `responseType`：可选 `json` | `html`，默认解析引擎；可被路由级覆盖。
- `useWebview`：可选布尔；`true` 时整源 WebView 渲染后抽取（强反爬）。
- `site`：必填，见下。
- `parser`：必填 `{type, overrides?, script?}`。
- `ageRating`：可选 `general`/`teen`/`mature`；兼容别名 all/16/r18/nsfw；mature 默认隐藏。

### site
`domain`(必填) `baseUrl`(必填，拼相对链接) `userAgent` `cookies`(手动Cookie登录，全源携带) `headers` `mirrors[]`(每项 {name,domain,baseUrl}) `publishPageUrl` `publishMirrorSelector`(主域失效时提取镜像，正则或CSS)。

### parser（两层）
- 顶层 `parser.type`：`builtin`(纯声明式) / `hybrid`(声明式+按API overrides覆盖，最常用) / `script`(全走JS沙箱)。
- 每个 API 可在 `parser.overrides.<api>` 指定：`builtin` / `xpath` / `jsonpath` / `css` / `script` / `webview`(渲染后抽，常用于m3u8) / `webview-html`(WebView取HTML再走解析，常用于反爬搜索)。
- `script` 模式：`parser.script` + `parser.entrypoints` 映射入口函数。

### routes（端点）
每个端点支持字符串写法或 `{url,method,headers,params,responseType,parser}` 对象。占位符：`{keyword}` `{page}` `{id}` `{url}` `{detailUrl}`。常用端点：search / latest / explore / category / detail / episodes / video / chapters(漫画) / images(漫画) / week(周更) / recommend / related / webFavorite(若用route)。

> `animeSource` **必须**有 `latest` 路由，否则校验报错。

### selectors（声明式抽取）
- 列表：`selectors.list` / `title` / `cover`(img@src) / `id`(a@href)。
- 详情：`selectors.detail.{title,cover,description,tags,author,status}`；漫画还可 `recommendations:{list,title,cover,url}`。
- 剧集：`selectors.episodes`（如 `ul li a`）。
- 视频：`selectors.video` 为 `css@attr`（如 `video#player@src`）优先；否则回退 VideoExtractor 扫 video/source/iframe。
- 推荐：`selectors.recommend.{list,title,cover,id}`（未声明复用 search 的）。
- 语法：`$.field`(jsonpath) / `.class a@text`(css+@text取文本) / `//video/@src`(xpath) / 小说自定义：`@text` `@href` `@src` `@textNodes` `||`回退 `a:contains(文字)` `.0/.1/-1`取第N个。

### 相对 URL 透传（Cloudflare / `/watch?v=` 模型必备）
声明式 `id:"a@href"` 只拿相对 href，选择器不 absUrl。用两条路由透传补绝对：
- `detail` 路由设为 `"{detailUrl}"`：`MediaItem.detailUrl` 由 `id`（以 `/` 开头）经 `_detailUrlFromId` 推导绝对地址。
- `video` 路由设为 `"{url}"`：`resolveRouteUrl` 对 video 路由特例，`{url}` 相对时自动 `base+url` 补绝对再交 WebView。

---

## §5 全功能模板（每个块都在，TODO_ 标注待填）

### §5.1 影视/动漫源（animeSource，覆盖全部高级块）

```json
{
  "id": "TODO_demo_anime",
  "name": "TODO_显示名",
  "author": "TODO_作者可选",
  "version": 1,
  "type": "animeSource",
  "responseType": "html",
  "useWebview": false,
  "ageRating": "general",
  "stealthMode": true,
  "enabled": true,
  "enabledExplore": true,
  "isHidden": false,
  "site": {
    "domain": "example.com",
    "baseUrl": "https://example.com",
    "userAgent": "TODO_可选",
    "cookies": "TODO_可选(整段会话Cookie做手动登录)",
    "headers": {},
    "mirrors": [
      { "name": "主站", "domain": "example.com", "baseUrl": "https://example.com" }
    ],
    "publishPageUrl": "TODO_可选",
    "publishMirrorSelector": "TODO_可选"
  },
  "parser": {
    "type": "hybrid",
    "overrides": {
      "latest":    { "type": "builtin" },
      "search":    { "type": "builtin" },
      "detail":    { "type": "builtin" },
      "episodes":  { "type": "builtin" },
      "video":     { "type": "webview" },
      "recommend": { "type": "builtin" },
      "week":      { "type": "builtin" }
    }
  },
  "routes": {
    "latest":   { "url": "/", "method": "get", "responseType": "html" },
    "search":   { "url": "/search?q={keyword}&page={page}", "method": "get", "responseType": "html" },
    "detail":   { "url": "/detail/{id}", "method": "get", "responseType": "html" },
    "episodes": { "url": "/detail/{id}", "method": "get", "responseType": "html" },
    "video":    { "url": "{url}", "method": "get", "responseType": "html" },
    "recommend":{ "url": "/api/recommend?id={id}", "method": "get", "responseType": "json" },
    "week":     { "url": "/api/weekly", "method": "get", "responseType": "json" }
  },
  "selectors": {
    "list": "TODO_list容器",
    "title": "TODO_标题",
    "cover": "TODO_封面img@src",
    "id": "TODO_a@href",
    "detail": {
      "title": "TODO", "cover": "TODO", "description": "TODO",
      "tags": "TODO", "author": "TODO", "status": "TODO",
      "recommendations": { "list": "TODO", "title": "TODO", "cover": "TODO", "url": "TODO" }
    },
    "episodes": "TODO_ul li a",
    "video": "TODO_//video/@src 或 webview抽m3u8",
    "recommend": { "list": "TODO", "title": "TODO", "cover": "TODO", "id": "TODO" }
  },
  "category": {
    "dynamicCategories": false,
    "categoryEntries": [ { "id": "all", "title": "全部" } ]
  },
  "homeSections": [
    { "id": "latest", "title": "最新更新", "route": "latest", "style": "grid", "limit": 18 },
    { "id": "week", "title": "周更列表", "route": "week", "style": "schedule", "limit": 0, "more": false }
  ],
  "filters": {
    "groups": [ { "id": "TODO", "title": "地区", "type": "single", "options": [ { "id": "1", "title": "国产" } ] } ],
    "byCategory": {},
    "defaults": {}
  },
  "antiHotlinking": { "referer": "https://example.com", "headers": {}, "userAgent": "TODO_可选" },
  "webviewConfig": { "adblock": true, "timeoutSeconds": 20 },
  "comments": {
    "provider": "source",
    "routes": {
      "list": { "url": "/api/comments?book={id}", "responseType": "json" },
      "replies": { "url": "TODO_可选", "responseType": "json" },
      "post": { "url": "TODO_可选", "responseType": "json" },
      "reply": { "url": "TODO_可选", "responseType": "json" },
      "like": { "url": "TODO_可选", "responseType": "json" },
      "report": { "url": "TODO_可选", "responseType": "json" }
    },
    "selectors": { "items": "TODO_$.list", "content": "TODO_$.content", "author": "TODO_$.user" },
    "login": {
      "url": "https://example.com/login",
      "checkCookie": "TODO_已登录Cookie键名",
      "checkUrl": "https://example.com/me",
      "loggedInSelector": "TODO_.user-info",
      "sendTokenAs": "TODO_null|bearer|key",
      "authScheme": "Key",
      "apiKeyParam": "apiKey"
    }
  },
  "network": {
    "proxy": "TODO_direct|继承全局",
    "dns": "TODO_system",
    "hosts": { "example.com": "TODO_IP" },
    "sni": { "enabled": true, "defaultSni": "-" },
    "ech": { "enabled": true, "configs": [] }
  },
  "webFavorite": {
    "title": "我的书架",
    "route": "webFavorite",
    "url": "/user/bookshelf",
    "addUrl": "/user/favorite/add?id={id}",
    "requireLogin": true
  },
  "announcement": {
    "title": "TODO_公告标题",
    "body": "TODO_正文",
    "url": "TODO_可选",
    "updatedAt": 1700000000
  },
  "deprecated": false,
  "migrationMessage": "TODO_可选"
}
```

### §5.2 漫画源（mangaSource，在 §5.1 基础上增 chapters/images 两端点）

漫画源比影视多 `chapters`(话列表) 与 `images`(该话图片) 两个端点。图片地址常加密，解密逻辑写在 `overrides.images.script` 的 `parseImages` 里。chapters 常需二次请求，用 §7 的 `__meta` 协议。

在 §5.1 的 `parser.overrides` 增补：
```json
"chapters": { "type": "script", "function": "parseChapters", "script": "function parseChapters(html, context){ /* 取 mid 后返回 __meta 协议 */ }" },
"images":   { "type": "script", "function": "parseImages",   "script": "function parseImages(raw, context){ var baseUrl=(context.baseUrl||'').replace(/\\/$/,''); var urls=decrypt(raw); return urls.map(function(u){ return u.indexOf('/')===0?baseUrl+u:u; }); }" }
```
`routes` 增补：`"chapters": {"url":"/detail/{id}","method":"get","responseType":"html"}`、`"images": {"url":"{url}","method":"get","responseType":"html"}`。
`selectors` 增补：`"chapters": "TODO_话列表容器"`。

### §5.3 小说源（novelSource，Legado 兼容，不用顶层 id/name/type/site）

```json
{
  "bookSourceName": "TODO_演示小说",
  "bookSourceUrl": "https://m.example.com",
  "bookSourceType": 0,
  "enabledExplore": true,
  "enabledSearch": true,
  "exploreUrl": "玄幻小说::https://m.example.com/xuanhuan/\n都市小说::https://m.example.com/dushi/",
  "bookSourceGroup": "内置书源",
  "concurrentRate": 0,
  "ruleSearch": {
    "bookList": ".bookbox",
    "bookName": ".bookname a@text",
    "bookAuthor": ".author@text",
    "bookCoverUrl": ".bookimg img@src",
    "bookUrl": ".bookname a@href",
    "bookLastChapter": ".update a@text"
  },
  "ruleExplore": {
    "bookList": ".bookbox",
    "bookName": ".bookname a@text",
    "bookAuthor": ".author@text",
    "bookCoverUrl": ".bookimg img@src",
    "bookUrl": ".bookname a@href"
  },
  "ruleBookInfo": {
    "name": "h1@text",
    "author": "p:contains(作者)@text",
    "coverUrl": ".block_img2 img@src",
    "intro": ".intro_info@text",
    "tocUrl": "a[href^=\"/book_\"]@href",
    "lastChapter": "p:contains(最新) a@text",
    "bookStatus": "p:contains(状态) span@text",
    "recommendations": "TODO_推荐书名选择器(可选)"
  },
  "ruleToc": {
    "chapterList": "a[href^=\"/book_\"][href$=\".html\"]",
    "chapterName": "@text",
    "chapterUrl": "@href",
    "nextTocUrl": "a:contains(下一页)@href"
  },
  "ruleContent": {
    "content": "#nr1@html",
    "title": "#nr_title@text",
    "nextContentUrl": "a:contains(下一章)@href"
  },
  "parser": {
    "type": "hybrid",
    "overrides": {
      "content": {
        "type": "script",
        "function": "parseContent",
        "script": "function parseContent(html, context){ var raw = context.dom.queryHtml(html, '#nr1') || context.dom.queryHtml(html, '#content') || ''; raw = raw.replace(/<script.*?<\\/script>/gi, ''); return context.content.clean(raw); }"
      }
    }
  },
  "bookSourceComment": "TODO_备注"
}
```

---

## §6 高级块速写（保留时直接套用，删块时整块移除）

**comments.login 三种登录**（可组合）：
- WebView 登录：`login.url` = 登录页，成功后捕获会话 Cookie 存本地。
- Cookie 登录：`login.checkCookie` = 已登录 Cookie 键名；或在 `site.cookies` 直接粘整段会话 Cookie。
- API Key 登录：`login.sendTokenAs:"key"`，用户在源详情登录面板粘密钥，App 存本地密钥库，受保护请求追加 `Authorization: <authScheme> <密钥>`（默认前缀 Key；站点要求 Token/Bearer 改 `authScheme`；`apiKeyParam` 默认 apiKey）。
- 令牌携带 `sendTokenAs`：`null`(只靠Cookie) / `bearer`(Authorization: Bearer <checkCookie值>) / `key`(Authorization: <authScheme> <手动密钥>)。
- 登录态二次确认：`login.checkUrl` + `login.loggedInSelector`（GET checkUrl，选择器命中非空即有效）。
- 凭据只存本地不上传；未声明登录按只读/免登录处理。

**network 生效优先级**：用户覆盖 > 源 network 块 > 全局设置 > 默认值，改完即时生效。`sni` 对直连 HTTPS 真实生效（`defaultSni:"-"` 免 SNI，配合 hosts 钉 IP 绕 SNI 封锁）；`ech` 受 Dart TLS 栈限制运行时暂未接通，仅预留。

**webFavorite**：声明后在线浏览多一「网络收藏」Tab（走源站接口，与 App 本地收藏独立）。`addUrl`/`addRoute` 支持 `{id}`/`{detailUrl}`/`{title}` 占位。

**announcement**：源首页+详情页顶部横幅。`title` 必填；不填 `url` 整条不可点击。

**schedule（周更表）**：`homeSections` 加 `{id,title,route:"week",style:"schedule",limit:0,more:false}`，`routes.week` 返回带星期字段的列表，App 按该字段分到周一~周日。

**recommend（猜你喜欢）**：`routes.recommend`(优先) 或 `related`(备选)，详情页带 `{id}` 调用；漫画用 `selectors.detail.recommendations`；小说用 `ruleBookInfo.recommendations`。两者皆无则不渲染。

**filters（动态筛选）**：`groups`(筛选组，type: single/multiple)、`byCategory`(按分类覆盖)、`defaults`(分类默认参数)。

---

## §7 __meta 异步协议（脚本端点唯一安全的异步通道）

当端点需先请求另一接口再解析（如视频先调 API 拿真实地址、漫画 chapters 先取 mid 再取章节 API），脚本返回协议对象，引擎预取后再回调处理函数：

```js
function parseVideo(html, context){
  var api = extractApi(html);
  return { __meta: true, __fetchUrl: api, __processor: "__processVideo" };
}
function __processVideo(json, context){ return json.url; }
```
批量预取：`{__meta:true, __fetchUrls:[...], __fetchConcurrency:4, __processor:"..."}`。占位符偏移支持 `{page-1}`/`{page+1}`。

JS 沙箱约定：函数签名固定 `parseXxx(html, context)`；必须同步返回（数组/对象）；`context` 含 `baseUrl`/`log`/`dom`/`content`；`evaluateAsync` 对 Promise 无力，异步一律走 `__meta`；模块全局变量在 parse/processor 调用间会被重置，处理器须读 `context.id`/`context.cid`。

---

## §8 校验与常见坑

1. JSON 合法：`python -c "import json; json.load(open('plugins/builtin/<id>.json'))"`。
2. 本机 `flutter analyze lib` 确认无破坏（沙箱无 Flutter）。
3. 真机：导入 → 首页/搜索出卡片 → 点详情过 Cloudflare → 播放抽出直链。
4. 上线前 grep 确认 JSON/注释无禁用仓库名。

**坑**：
- `webview-html` 路由不要写 `script`：声明式渲染回灌走 BuiltinResolver，脚本不调用。
- 详情页相对 href 必须靠 `{detailUrl}`/`{url}` 透传补绝对，否则 WebView 加载相对地址失败。
- 视频直链需防盗链 Referer：`antiHotlinking.referer` 填源站 origin，引擎自动补同源 Referer。
- 漫画 `images` 解密逻辑必须写在脚本里，不要硬编码到站外。
- `version` 升级须 +1 才会覆盖用户编辑过的副本；`removeSource` 是屏蔽内置而非恢复。
- 不要为 `webview-html` 路由写抽取脚本；纯 `builtin` 直连遇反爬会返回挑战页（空结果）。
- 源模型忽略未知键（`lang`/`builtin`），勿当功能字段。
