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

### 2.6 聚合前端站（SPA 壳 + 站方聚合接口 + 上游采集 API 扇出）

特征：首页正文密度极低（`<div id="app">`）但内嵌 `ul.xxx-list` 等 SEO 服务端渲染列表；详情/搜索路由返回纯壳（几 KB，只有 `<script src="/assets/index-*.js">`）；noscript 提示「搜索和播放需启用 JS」。本质是**元聚合器**：自家服务器只做聚合索引（搜索联想/最新），真实数据平面在前端 bundle 里硬编码的一批上游采集 API（`api.php/provide/vod` 家族）。

识别与拆解（站点无关）：

1. **bundle 挖矿**：壳 HTML 里只有一个应用 JS → 下载它，`grep -oE '"/api/[a-z0-9/_-]+'` 列同源接口，`grep -oE 'fetch\([^)]{0,120}'` 列数据流。上游映射表是形如 `"key":{name:…,api:"https://…",detail:"https://…",alive:!0,search:!0,playable:!0,adult:!1}` 的对象——用平衡括号逐条解析（正则 `\{.*?\}` 会被嵌套截断）。`adult:!0` 的条目按 ageRating 诉求剔除。
2. **双平面接入**：搜索用站方聚合接口（服务端已聚合去重、元数据最全，但**有条数上限**——先探 limit 递增值，超限返回 `{"error":"invalid limit"}` 这类错误体）；列表/分类/详情/选集用上游采集 API 扇出。详情 URL 编码 `(sourceKey~vodId)` 复合 id，详情/选集脚本从 `context.id` 拆 key→查映射→`?ac=videolist&ids=` 直查上游。
3. **扇出用 `__fetchUrls` 批量预取**：并发默认 6，失败项为 null（按序对齐扇出清单，处理器里跳过即可），整批不会因单源死而失败。入口函数把路由预取回来的站方聚合数据存模块级变量，处理器再合并——meta 链内模块变量共享。
4. **分类判定用构建期类型表**：上游 videolist 条目**不带类型名**（只有 `type_id`/`vod_class`），且 `type_id_1` 各源不统一（有的 1=电影/2=剧，有的完全自定）。正解：构建期抓各源 `ac=list` 的 `class` 树（`type_id/type_pid/type_name`），沿 pid 链走到根，把根名归一到四大类，蒸馏成 `{type_id: 分类}` 静态表内嵌进脚本——运行时零额外请求。未知 type_id 走 `vod_class` 文本正则兜底；仍判不出就过滤（顺带把理论片/伦理片等成人根挡在外面）。
5. **采集站三段式选集合并**：`vod_play_from` 与 `vod_play_url` 都是三段式——`$$$` 分线路、`#` 分集、`$` 分标题与地址。脚本端点选集按「首集是直连媒体（.m3u8/.mp4）的线路优先」稳定排序，跨线路按集号（标题里的数字）去重先到先得；引擎脚本端点选集不支持 lineName 分组，只能合并扁平化。**集 URL 里的非 ASCII 字符（中文路径）必须 percent-encode**，否则引擎预取与播放器都会挂。
6. **播放中转页判定树**（预取体=集 URL 的响应）：`#EXTM3U` 开头→是播放列表文本，直接回 `context.url`；`var main = "/path/index.m3u8?sign=…"`→根相对路径按中转页 origin 补全；`player_aaaa={url,encrypt}`→按 encrypt 解码（1=URL 解码，2=base64+URL 解码）；最后正则兜底取第一个 m3u8/mp4 直链。直链集无需任何请求（预取即是校验）。
7. **哑路由预取最小化**：script 端点也会先预取路由 URL。latest/category 这类数据全靠 `__meta` 扇出的端点，路由 URL 指向站内极轻量且保证 200 的文件（如 robots.txt，约 90 字节），别指首页（数百 KB）；search 若站方聚合接口本身就是数据源之一，直接把路由 URL 写成它（预取即取数，`responseType: json` 时 raw 已是解析对象）。
8. **体积预算**：一页扇出 15 源 × 20 条 ≈ 全链路 40-60 秒内（真机网络会更慢）。扇出清单按实测延迟排序，砍掉 >3s 的源；聚合搜索条数上限决定第 1 页质量，翻页靠上游 `pg={page}`。

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
