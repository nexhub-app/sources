# 全功能块速写（可选功能怎么填）

用于「要一份覆盖全部功能的源」的场景。骨架见 `assets/templates/anime-full.json`（影视）与
`novel-legado-full.json`（小说）：所有可选块都在位，`TODO_` 处换成真实值；**用不到的块整块删掉**，
不要留 TODO 上线（引擎会忽略空块，但会给后续维护者埋雷）。

字段级真值仍以 `references/field-spec.md` 与 `lib/core/models/plugin_config.dart` 为准。

## 一、事实采集清单（决定保留哪些高级功能）

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

## 二、漫画端点的两段脚本

漫画源比影视多 `chapters`(话列表) 与 `images`(该话图片) 两个端点。图片地址常加密，解密逻辑写在 `overrides.images.script` 的 `parseImages` 里。chapters 常需二次请求，用 §7 的 `__meta` 协议。

在 §5.1 的 `parser.overrides` 增补：
```json
"chapters": { "type": "script", "function": "parseChapters", "script": "function parseChapters(html, context){ /* 取 mid 后返回 __meta 协议 */ }" },
"images":   { "type": "script", "function": "parseImages",   "script": "function parseImages(raw, context){ var baseUrl=(context.baseUrl||'').replace(/\\/$/,''); var urls=decrypt(raw); return urls.map(function(u){ return u.indexOf('/')===0?baseUrl+u:u; }); }" }
```
`routes` 增补：`"chapters": {"url":"/detail/{id}","method":"get","responseType":"html"}`、`"images": {"url":"{url}","method":"get","responseType":"html"}`。
`selectors` 增补：`"chapters": "TODO_话列表容器"`。

## 三、高级块速写

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
