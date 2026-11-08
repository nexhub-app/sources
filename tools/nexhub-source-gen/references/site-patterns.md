# 站点类型 → 源骨架

先探测，再选骨架。探测命令：

```bash
python scripts/probe_site.py https://站点首页
```

| 探测结果 | 站点类型 | 解析路线 | 起点模板 |
|---|---|---|---|
| `Content-Type: application/json`，或页面能找到 `$.data.list` 这类结构 | **JSON 接口型** | `responseType: json`，端点 `jsonpath`，`selectors` 用 `$.` 路径 | `assets/templates/anime-json-api.json` |
| 直连能拿到完整 HTML，正文密度正常 | **服务端渲染型** | `hybrid` + 端点 `builtin` + CSS/XPath | `assets/templates/anime-html.json` / `manga-html.json` |
| 403/503、`Just a moment`、`cf-chl`、`人机验证` | **强反爬型** | `useWebview: true` + 列表详情 `webview-html` + 播放 `webview`+script | `assets/templates/manga-webview.json` |
| 正文密度极低 + `__NEXT_DATA__` / `window.__NUXT__` / `<div id="app">` | **前端渲染型** | 先找内联 JSON（脚本直接读），否则 `webview-html` | `anime-html.json`（改 overrides） |
| 图片地址是 base64 块 / 需要解密 / 需要拼 referer | **加密图型** | 脚本 + `context.crypto`，配合 `imageTransform` | 在 manga 模板上加 images 脚本 |
| `bookSourceUrl` / `ruleSearch` 结构 | **小说书源** | 直接写 Legado 书源 JSON | `assets/templates/novel-legado.json` |

## 常见站点形态的取数套路

### 1. MacCMS 系影视站（`/vodshow/…`、`/voddetail/…`）

- 列表页：`ul.vod-list li`，封面 `img@data-original, img@src`。
- 详情页选集：`ul.play-list li a`，或 `div.play-list a`。
- 播放页：地址常藏在 `player_aaaa={...}` 这类变量里 → 用 `script` 端点正则取出 JSON 再解出 `url`。
- 分类页 URL 常带 `--------1---.html` 这种占位串，page 占位符要按站点规律放（如 `{page}` 在第几位）。
- 导航只有一个类型 ≠ 分类维度只有一种：完整浏览维度（年份/地区/排序）常在分类页筛选面板，走与搜索共用路由的查询串 → 用 `filters` 块 + `{param?}` 可选占位接入，见 `duanju-patterns.md` §15。

### 1.5 聚合资源站（详情页挂多家第三方「线路」的影视站）

特征：详情页有若干线路页签（tab/playlist 分块），每个线路一版选集列表；播放页从 `var now=` 这类变量取直链。本质是**聚合器**：每条线路对应一家第三方资源站家族，直链落在各家自己的 CDN 上。

关键规律（站点无关）：

1. **线路 ≠ 站点自己的服务器**。第三方 CDN 寿命不一，死法有四：500、域名消失（DNS 不存在）、连接挂起、被墙。站点「默认/激活」线路常先死——别把首线路当好线路。
2. **播放页 URL 三段式 `{id}-{line}-{ep}`**：换 line 段即同集数换线路，无需解析选集 DOM 就能构造兄弟线路地址；播放页上通常也把全部线路的同集数链接都列出来。
3. **线路存活只能探测**：对候选直链各拉一次 m3u8 文本，`#EXTM3U`/`#EXTINF` 即存活。解析式样见 `troubleshoot.md` §6.1（`__meta` 两跳批量探活）。
4. **单线路影片上游死了就是死了**：站点网页端同样播不了，不要在这类条目上反复调解析。
5. 搜索接口若已停用，可用站方 RSS/最新列表做标题过滤兜底（只覆盖最新内容、无封面，`description` 里向用户说明口径）。

### 2. 采集 API 系（`/api.php/provide/vod/?ac=list`）

- 直接 `responseType: json`，列表 `$.list`，字段 `vod_id` / `vod_name` / `vod_pic`。
- 选集在 `vod_play_url` 里是 `名称$地址#名称$地址` 的字符串 → 用脚本 split，或直接交给内置采集解析器（端点 `builtin` + 不写 selectors 时部分端点会自动识别）。
- POST 型接口：`"method": "post"` + `"body": "{\"ac\":\"list\",\"pg\":\"{page}\"}"`。

### 2.5 搜索地址的四种形态（先测再写）

不要凭经验猜，按下面顺序确认：

0. **站方联想接口（免验证，优先试）**：MacCMS 系 `/index.php/ajax/suggest?mid=1&wd={keyword}&limit=50` 返回 `{list:[{id,name,pic}]}`——站内搜索框的自动补全数据源，通常不挂验证墙。搜索路由写 `responseType: json` + override `builtin`，选择器 `$.list/$.id/$.name/$.pic`。HTML 搜索页被验证墙拦时这是首选。
1. **读首页表单**（最可靠）：`<form action="/search/-------------.html">` + `<input name="wd">` → `"/search/-------------.html?wd={keyword}"`。`probe_site.py` 会直接打印 action 与字段名。
2. **路径式**：`/index.php/vod/search/page/1/wd/{keyword}.html`（MacCMS 常见，参考实现同款）。
3. **查询式**：`/index.php/vod/search.html?wd={keyword}`、`/search.html?wd=`。
4. **站内路由式**：`/search/{keyword}----------1---.html`（部分模板）、`/search/{keyword}----------1---.html` 的第 N 页换数字。

排除法要点：

- `?s=` 在自定义模板上常返回 `System Error`（不是 WordPress 原生搜索）。
- 同一站可能只有 `/search/` 被验证墙拦住，其它页面正常 → 只给 `search` 配 `webview-html`。
- 搜索结果页通常复用列表模板（同一套卡片 class），选择器可直接照抄 `latest`；先用 lxml 在列表页验证。

### 3. 漫画站

- 章节列表常在详情页里：`chapters` 路由 = `{detailUrl}`。
- 阅读页图片懒加载：`div.reader img@data-src`，加逗号兜底 `, div.reader img@src`。
- 一话分多页：脚本循环拼页 + `__fetchUrls` 批量取。

### 4. Cloudflare 站

- `useWebview: true` + `stealthMode: true` + `webviewConfig.timeoutSeconds` 给足渲染时间。
- 列表/详情/目录/图片全部 `webview-html`（渲染后交回声明式引擎，**不写 script**）。
- 播放页 `webview` + IIFE 脚本抽 `<video>` / 内嵌 iframe。
- 首次访问会弹一次人机验证，App 有验证 UI，验证通过后短期生效。

### 5. 小说站

- 直接写 Legado 书源格式（`bookSourceName` / `bookSourceUrl` / `ruleSearch` / `ruleBookInfo` / `ruleToc` / `ruleContent`），应用会自动识别并转换。
- 规则语法：CSS 选择器 + `@text` / `@href` / `@html` / `@textNodes`，`##正则` 替换，`&&` / `||` 组合，`@js:` 内嵌脚本。
- 正文清洗异常（夹广告/推荐）时，用 `##正则` 去掉，或加 `parser.overrides.content` 脚本。

## 选骨架的三个原则

1. **能直连就别开 WebView**：WebView 慢、易崩、要用户点验证。
2. **能用声明式就别写脚本**：脚本难调、超时 10 秒、换站就得改。
3. **先做 1 条链路**：`search` + `detail` 通了再加目录、图片、播放。一次写完整个源，出错时无法定位。
