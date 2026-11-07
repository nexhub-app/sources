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

### 2. 采集 API 系（`/api.php/provide/vod/?ac=list`）

- 直接 `responseType: json`，列表 `$.list`，字段 `vod_id` / `vod_name` / `vod_pic`。
- 选集在 `vod_play_url` 里是 `名称$地址#名称$地址` 的字符串 → 用脚本 split，或直接交给内置采集解析器（端点 `builtin` + 不写 selectors 时部分端点会自动识别）。
- POST 型接口：`"method": "post"` + `"body": "{\"ac\":\"list\",\"pg\":\"{page}\"}"`。

### 2.5 搜索地址的四种形态（先测再写）

不要凭经验猜，按下面顺序确认：

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
