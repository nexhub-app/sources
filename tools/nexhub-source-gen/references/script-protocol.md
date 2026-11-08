# 脚本协议（JS 沙箱）

实现：`lib/core/resolver/script_resolver.dart` + `lib/core/resolver/js_context.dart`

只在声明式选择器做不到时才写脚本：需要签名/加密、需要二次请求、真实地址藏在 JS 变量里、需要解 base64/AES。

## 1. 入口函数怎么被调用

```json
"parser": { "type": "hybrid", "overrides": { "video": { "type": "script", "function": "parseVideo", "script": "function parseVideo(html, context){ ... }" } } }
```

- 入口名优先级：`overrides.<端点>.function` > `overrides.<端点>.entrypoints.<端点>` > `parser.entrypoints.<端点>` > **端点名本身**。
- 调用形态：`入口函数(raw, context)`。`raw` 是当前路由预取回来的 HTML 字符串或已解析的 JSON 对象。
- `parser.overrides.<端点>` 没写 `script` 时使用 `parser.script`（一份脚本可服务多个端点）。
- 超时 10 秒。**整个流程只允许同步返回**（见 §3）。

## 2. `context` 能力表

| 命名空间 | 方法 | 说明 |
|---|---|---|
| `context.http` | `get(url)` / `getJson(url)` / `post(url, body, headers)` / `postForm(url, params, headers)` / `put` / `delete` / `fetch(url, options)` | 返回 Promise。走源的网络配置与防盗链头 |
| `context.dom` | `query(html, sel)` / `queryAll(html, sel)` / `queryAttr(html, sel, attr)` / `queryXPath(html, xpath)` / `queryHtml(html, sel)` | 与服务端同一套 CSS/XPath 引擎 |
| `context.content` | `clean(html)` | 正文清洗（去脚本/广告，转纯文本） |
| `context.crypto` | `md5` `sha1` `sha256` `sha512` `hmac(key,data,algo)` `base64Encode` `base64Decode` `hexEncode` `hexDecode` `rc4(data,key)` `aesEcb` `aesCbc` `aesCfb` `aesOfb` `aesDecrypt` | 都返回 Promise |
| `context.image` | `extractImagesFromHtml` / `extractLazyImagesFromHtml` / `isValidImageUrl` / `guessFormat` / `filterImages` / `getPageUrls` | 图片处理 |
| `context.storage` | `get(key)` / `set(key, value)` / `remove(key)` | 跨调用持久化（按源隔离），适合存 token |
| `context.url` | `resolve(rel)` | 相对地址转绝对 |
| `context.log` | `log(msg)` | 写诊断日志 |
| 其它 | `context.baseUrl`、`context.page`、`context.keyword`、`context.category`、`context.id`、`context.detailUrl`、`context.chapterId`、`context.cid`、`context.mid` | 路由变量，按端点注入 |
| 全局 | `atob` / `btoa` | 沙箱已内建 polyfill，不要重复声明 |

> 沙箱内**没有** `fetch` / `XMLHttpRequest` / `document` / 文件系统；网络一律走 `context.http`。

## 3. 铁律：二次请求数据优先 __meta；入口函数一律写同步

2026-07 起引擎修好了微任务泵：`await context.http/crypto/...` 与 `.then` 链都会触发。但要注意分两条线：

- **作为「最终数据出口」的入口函数（parseVideo / parseList / parseDetail…）一律写同步函数**，异步数据一律走 `__meta` 两步。真机实证（2026-11）：async 入口的**返回值提取**在部分真机批次失效——返回的 Promise 被字符串化成 `"Instance of 'Future<dynamic>'"` 当成结果透传，parseVideo 会产出一条垃圾「直链」直接进播放器黑屏；微任务泵修的是桥接调用通道，救不了脚本级返回值通道。
- `context.crypto` 这类**纯计算**可以放心 await（详见 `references/duanju-patterns.md` §1-2）。

```js
function parseDetail(html, context) {
  var id = /var\s+bookId\s*=\s*"(\d+)"/.exec(html);
  return {
    __meta: true,
    __fetchUrl: '/api/book/' + id[1],
    __fetchHeaders: { 'Referer': 'https://example.com/' },
    __processor: 'processDetail'
  };
}
function processDetail(data, context) {
  // data 是上面接口返回的 JSON（对象）或文本
  return { id: String(data.id), title: data.name, cover: data.pic };
}
```

meta 支持的键：

| 键 | 作用 |
|---|---|
| `__fetchUrl` | 预取地址（相对路径按源 base 补全） |
| `__fetchUrls` | 批量预取：字符串数组，配合 `__fetchConcurrency`（默认 6）。**失败项为 null、顺序与数组对齐**（单源失败不炸整批，处理器按索引对应扇出清单并跳过 null） |
| `__fetchMethod` | `get`（默认）/ `post` |
| `__fetchBody` | POST 体 |
| `__fetchHeaders` | 请求头对象 |
| `__fetchResponseType` | `json`（默认）/ `text` |
| `__processor` | 预取完成后调用的同步函数名，入参是预取结果 |
| `__webview` | `true` 时先让内嵌浏览器渲染该 URL，再把渲染后 HTML 交给 `__processor` |
| `__webviewScroll` | `true` 时渲染后逐屏滚动，触发懒加载 |

- 链式：`__processor` 返回的仍是 meta 描述符时会再走一跳，**最多 4 跳**（用于「先查 id 再提交」）。
- 处理器入参形态（引擎两代事实，2026-11 实证）：**单条** meta 的处理器，新引擎逐参收 `(响应体, 响应头, context)`；旧引擎把多参整体打包成一个数组作首参 `([响应体, 响应头], context)`——按「入参=预取结果」写的处理器在旧引擎下顶层取不到 `data` 键而**恒空产出**（预取 200 且数据完整、日志 `List[0]` 是铁证）。**批量** meta 收到裸响应列表（响应体本就可能是数组，别盲目归一）。单条跳的处理器开头一律先归一，两代引擎都能跑：
  `var body = (Array.isArray(raw) && raw.length > 0 && raw[0] && typeof raw[0] === 'object') ? raw[0] : raw;`
  归一放在「解析响应的单一入口函数」里做一处即可，所有处理器都过它，不要各写一遍。
- **带权取流只能走 `__meta`**：路由级预取只附加源声明式鉴权头（comments.login）；脚本在 `storage` 里现取的令牌（登录换 token、挑战令牌等）只有放进 `__fetchHeaders` 才会发出去。「入口第一跳命中 200 + code/msg/status 齐全但 `data=null` 的空壳、`__meta` 二跳才拿到真数据」是依赖令牌端点的**常态**，不是解析坏了——别在空壳上纠错，直接确认二跳的地址与头。
- 反查：脚本里写死要访问的地址时，拼 `context.baseUrl + '/path'`，不要写死域名。**二跳地址来自脚本产出的相对 url（如选集返回的相对播放地址）时同理**——先补全绝对地址再判断「是否 http 开头」，否则链式二跳永远不触发、静默返回空。
- **路由预取数据要带进处理器**：处理器拿不到 `context`。入口函数把路由预取的数据（如站方聚合接口的响应）存进模块级变量，处理器直接读——同一 meta 链内引擎实例不销毁、模块变量共享（跨调用才重置）。
- **`__meta` 只认布尔 `true`**：写 `__meta: 1` 引擎判 `== true` 失败，描述符被当最终数据透传，结果恒空且无报错（日志里只见入口产出、无「预取成功」行）。批量/单条一律 `__meta: true`。
- Cookie 头特例：`__fetchHeaders` 显式声明的 `Cookie` 与会话 jar **按名合并**（同名显式优先），不会被 jar 里的会话 cookie 顶掉。「拦截页内联 JS 写 cookie 后自跳转」的自动挑战（无人工要素）靠它二跳携带挑战令牌，完整模式见 `references/troubleshoot.md` §0.4。

## 4. 各端点返回值形状

| 端点 | 返回 | 字段 |
|---|---|---|
| latest / search / explore / category / recommend / related | 数组 | `{id, title, cover, detailUrl | detail, description, author, director, actors, status, tags, updatedAt, episodeCount, wordCount, authorUrl, tagUrls}` |
| detail | 单个对象 | 同上 |
| episodes / chapters | 数组 | `{id, title, url, number, updatedAt}` |
| images | 字符串数组 | `['url1', 'url2']` 或 `[{url}]` |
| video | 字符串，或对象 | `'直链'` 或 `{url, type, headers, lines:[{name,url,headers}]}` |
| content | 见小说说明 | 图文块 |
| mirrors / folders | 数组 | 原样透传（不转 MediaItem） |

返回 `null` 或空数组 = 空列表，不会崩。

## 5. WebView 模式下的脚本（`type: "webview"`）

这类脚本不是函数，而是一段**在内嵌浏览器里求值、返回字符串的表达式**（`evaluateJavascript`）：

```json
"video": {
  "type": "webview",
  "script": "(function(){var v=document.querySelector('video');if(v&&(v.src||v.currentSrc))return v.src||v.currentSrc;var s=document.querySelector('video source');if(s&&s.src)return s.src;var f=document.querySelector('iframe');if(f&&f.src)return f.src;return '';})()"
}
```

- 必须自己包成 IIFE（立即执行），`return` 的字符串就是播放地址。
- 该模式下可以自由用 `document` / `window`（浏览器环境），但**不能用** `context.*`（那是沙箱 API）。
- 想同时拿到多线路：返回 JSON 字符串，如 `JSON.stringify({url:u, lines:[...]})`? —— 不支持自动解析，多线路请改用 `script` 端点返回对象。

## 6. 常见坑

| 现象 | 原因 | 解法 |
|---|---|---|
| 脚本永远返回空 | 函数名和 `override.function` 不一致 | 改名或补 `function` 字段 |
| 批量预取根本没发生、结果恒空 | `__meta` 写成了 `1`（引擎判 `== true`） | 改成 `__meta: true`（日志无「预取成功」行是铁证） |
| `ctx is not defined` | 照抄了别家阅读器的脚本 | 本应用注入的是 `context`，全局替换 |
| 返回 `[object Promise]` | 直接 `return context.http.get(...)`（没 await 也没 __meta） | `await` 它，或改 `__meta` 两步 |
| 直链/结果变成 `"Instance of ..."` 垃圾串 | 入口是 async 函数，真机上返回值提取失效（见 §3） | 入口改同步 + `__meta` |
| 列表/详情封面全挂，图片直开却 200 | 脚本返回了相对路径封面；图片层把非 http(s) 当本地文件，**永不发请求**（图片缓存索引里该源 0 条记录是铁证） | 脚本内补全：`cover = baseUrl + path`（列表与详情两处都要；协议相对 `//x/y` 补 `https:`） |
| 批量处理器把字符串当数组遍历 | 字符串也有 `.length`，`raw.length !== undefined` 判不出数组 | 用 `Array.isArray(raw)` |
| 预取 200 且数据完整，处理器却恒空产出 | 处理器把旧引擎的打包数组 `[响应体, 响应头]` 当响应体用，顶层自然没有 `data` | 处理器开头形态归一（见 §3 两代引擎事实） |
| 点播恒空、日志里二跳 meta 从未发起 | 链式二跳地址是相对路径，`indexOf('http')` 判定失败后静默返回空 | 二跳前拼 `context.baseUrl` 补全（见 §3 反查） |
| 第二次调用拿不到上次的变量 | 每次解析新建引擎，模块级变量会重置 | 用 `context.storage`；同一 meta 链内各跳共享全局（引擎实例不销毁） |
| 超时 | 循环里串行请求太多 | 用 `__fetchUrls` 批量，或拆成多跳 |
| script 端点每次白拉几百 KB | 路由 URL 指了首页，但数据其实全走 `__meta` | 哑路由指向站内极轻量且保证 200 的文件（robots.txt 形态）；聚合接口本身就是数据源时把路由 URL 直接写成它（预取即取数） |
| 脚本里 `?` / 箭头函数报错 | 个别引擎版本 | 用 ES5 写法（`var`、`function`、字符串拼接）最稳 |

## 7. 调试

- 脚本里 `context.log('x=' + x)`，App 的诊断日志会记录。
- 先用最小脚本验证桥接是否通：`function latest(html, context){ return [{id:'1', title:'hello'}]; }` —— 能出卡片说明管线通，再往里加逻辑。
