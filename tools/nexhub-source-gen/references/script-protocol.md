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

## 3. 铁律：不要靠 async 返回结果

引擎对 `async function` / `Promise` 返回值支持不稳定（真机上 `evaluateAsync` 拿不到 Promise 结果）。要拿二次请求的数据，用 **meta 两步协议**。

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
| `__fetchUrls` | 批量预取：字符串数组，配合 `__fetchConcurrency`（默认 6） |
| `__fetchMethod` | `get`（默认）/ `post` |
| `__fetchBody` | POST 体 |
| `__fetchHeaders` | 请求头对象 |
| `__fetchResponseType` | `json`（默认）/ `text` |
| `__processor` | 预取完成后调用的同步函数名，入参是预取结果 |
| `__webview` | `true` 时先让内嵌浏览器渲染该 URL，再把渲染后 HTML 交给 `__processor` |
| `__webviewScroll` | `true` 时渲染后逐屏滚动，触发懒加载 |

- 链式：`__processor` 返回的仍是 meta 描述符时会再走一跳，**最多 4 跳**（用于「先查 id 再提交」）。
- 反查：脚本里写死要访问的地址时，拼 `context.baseUrl + '/path'`，不要写死域名。

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
| `ctx is not defined` | 照抄了别家阅读器的脚本 | 本应用注入的是 `context`，全局替换 |
| 返回 `[object Promise]` | 用了 async / 直接 `return context.http.get(...)` | 改 `__meta` 两步 |
| 第二次调用拿不到上次的变量 | 每次解析新建引擎，模块级变量会重置 | 用 `context.storage` |
| 超时 | 循环里串行请求太多 | 用 `__fetchUrls` 批量，或拆成多跳 |
| 脚本里 `?` / 箭头函数报错 | 个别引擎版本 | 用 ES5 写法（`var`、`function`、字符串拼接）最稳 |

## 7. 调试

- 脚本里 `context.log('x=' + x)`，App 的诊断日志会记录。
- 先用最小脚本验证桥接是否通：`function latest(html, context){ return [{id:'1', title:'hello'}]; }` —— 能出卡片说明管线通，再往里加逻辑。
