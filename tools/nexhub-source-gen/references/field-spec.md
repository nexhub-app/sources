# 源配置字段规范（权威实现：`lib/core/models/plugin_config.dart`）

源的唯一形态是 **一个 JSON 文件**。应用里没有任何针对某个站点的 Dart 代码，所以只要 JSON 描述对了，站点就能用。

## 0. 文件去处

| 场景 | 做法 |
|---|---|
| 给用户自己用 | 存成 `xxx.json`，App「源管理 → 导入」选文件 |
| 随包发布的内置源 | 放 `plugins/builtin/`（该目录被 .gitignore 忽略，改完必须重编译才会进包） |
| 覆盖已装源 | 同 `id` + `version` ≥ 已装版本才覆盖；`version` 小于已装版本会被拒绝（防误装旧版） |

改内置源**必须**把 `version` +1，否则用户机器上被改过的旧副本不会被覆盖。

## 1. 顶层字段

| 字段 | 必填 | 取值 / 说明 |
|---|---|---|
| `id` | ✅ | 唯一标识，只用字母数字下划线连字符，建议 `pms_xxx` / `manga_xxx` / `novel_xxx` |
| `name` | ✅ | 展示名 |
| `type` | ✅ | `animeSource` / `mangaSource` / `novelSource` |
| `site` | ✅ | 见下 |
| `version` | 建议 | 整数，默认 1 |
| `responseType` | 建议 | 顶层默认响应类型 `html` / `json`；可被路由级覆盖 |
| `useWebview` | 可选 | 只影响 **video 路由**的内嵌浏览器行为；列表/详情要渲染请用路由级 `overrides.<端点>.type = webview-html`，它不依赖这个开关 |
| `stealthMode` | 可选 | 反检测，配合 WebView 用 |
| `parser` | ✅ | 见 §3 |
| `routes` | ✅ | 见 §4，animeSource 必须有 `latest` |
| `selectors` | 声明式必填 | 见 §5 |
| `category` | 可选 | 分类入口，见 §6 |
| `homeSections` | 可选 | 首页板块；不写则自动用 latest + 各分类 |
| `filters` | 可选 | 发现页筛选按钮（标签/年份等），复杂源的加分项 |
| `antiHotlinking` | 建议 | `{referer, userAgent, headers}`，图片/视频防盗链 |
| `network` | 可选 | 源级网络覆盖（hosts / sni / dns / 代理） |
| `webviewConfig` | 可选 | `{adblock, timeoutSeconds, extraUserAgent}` |
| `cdn` | 可选 | 声明式图床发现 |
| `imageTransform` | 可选 | 图片字节变换（解密/切片） |
| `comments` / `webFavorite` / `announcement` | 可选 | 评论、源站书架、公告；不用就不写 |
| `ageRating` | 可选 | `general`（默认）/ `teen` / `mature`；`mature` 在开启年龄限制时隐藏 |
| `enabled` / `enabledExplore` / `isHidden` | 可选 | 默认 `true` / `true` / `false` |
| `author` / `description` / `deprecated` / `migrationMessage` | 可选 | 展示与迁移提示 |

## 2. `site`

```json
"site": {
  "domain": "example.com",
  "baseUrl": "https://example.com",
  "userAgent": "可选，覆盖默认 UA",
  "cookies": "可选，string",
  "headers": { "可选": "附加请求头" },
  "mirrors": [{ "name": "主站", "domain": "example.com", "baseUrl": "https://example.com" }]
}
```

- `baseUrl` 是所有相对链接的拼接根，**不要以 `/` 结尾**。
- `mirrors` 让用户可切镜像；切换后路由里的相对路径自动跟着换 host。

## 3. `parser`

```json
"parser": {
  "type": "hybrid",                       // builtin | hybrid | script
  "engine": "css",                        // 保留字段，可不写
  "overrides": {                          // 按端点覆盖解析方式
    "latest":   { "type": "builtin" },
    "search":   { "type": "builtin" },
    "detail":   { "type": "builtin" },
    "episodes": { "type": "builtin" },
    "video":    { "type": "webview", "script": "(function(){ ... return 直链; })()" }
  }
}
```

端点覆盖类型：

| `type` | 引擎行为 | 什么时候用 |
|---|---|---|
| `builtin` / `css` / `xpath` / `jsonpath` | 直连 HTTP，按 `selectors` 解析 | 首选；服务端渲染或 JSON 接口 |
| `script` | 跑 JS 脚本（脚本自己抓数据） | 需要计算签名、拼接二次请求、解密 |
| `webview-html` | 内嵌浏览器渲染整页 → 交回声明式引擎按 `selectors` 解析 | 过 Cloudflare / 内容靠 JS 渲染。**不要配 script** |
| `webview` | 内嵌浏览器里执行 `script` 表达式，返回字符串 | 抽播放直链（`<video>` / 加密变量 / 嗅探） |

路由判定顺序（`resolver_registry.dart`）：`parser.type` 命中声明式集合 + `useWebview` + 视频端点 → `webview`；否则按 override 的 `type`；`hybrid` 里没有 script/webview 覆盖的端点一律走声明式直连。

## 4. `routes`

```json
"routes": {
  "search": { "url": "/search?q={keyword}&page={page}", "method": "get", "responseType": "html" },
  "detail": { "url": "{detailUrl}", "method": "get" }
}
```

| 键 | 说明 |
|---|---|
| `url` | 支持占位符，见下表；相对路径按 `site.baseUrl` 补全 |
| `method` | `get`（默认）/ `post`；写了 `body` 也隐含 POST |
| `headers` / `params` | 路由级请求头 / 参数 |
| `body` | POST 体模板，支持 `{名字}` 占位符（JSON 接口用） |
| `responseType` | 路由级响应类型 `html` / `json`；不写时：`parser.type` 为 xpath/css/html → `html`，其余默认 `json` |

**占位符**（左到右代入）：

| 占位符 | 值来源 |
|---|---|
| `{page}` | 页码，从 1 开始 |
| `{keyword}` | 搜索词（已 URL 编码） |
| `{id}` | 作品/条目 id |
| `{detailUrl}` | 详情页绝对地址 |
| `{url}` | 当前要打开的页面地址（video 端点专用） |
| `{category}` | 分类 id |
| `{chapterId}` / `{cid}` / `{mid}` | 漫画章节标识（`mid@cid` 形式会自动拆分） |
| `{名字-1}` / `{名字*30-30}` | 数值运算，支持 `+ - * /`，从左到右、负值夹到 0 |
| `{名字?}` | 可选参数：值为空时整段 `&x={名字?}` 移除 |

> 不认识的占位符会被清理成空串，不会报错 —— 抓空多半是这里写错了。

端点名约定：`latest`（首页最新）、`explore`、`category`、`search`、`detail`、`episodes`（影视选集）/ `chapters`（漫画章节） / `toc`（小说目录）、`images`（漫画图片）、`video`（播放地址）、`content`（小说正文）、`week`（周期表）、`related` / `recommend`。

## 5. `selectors`

两种写法都支持：

```json
"selectors": {
  "latest": { "list": "div.item", "title": "h3", "cover": "img@src" },
  "search": { "list": "div.item", "title": "h3", "cover": "img@src" }
}
```

```json
"selectors": { "list": "div.item", "title": "h3", "cover": "img@src" }
```

分组写法优先；没找到对应分组时回退到顶层扁平写法。`searchByAuthor` / `searchByTag` 这类字段搜索端点没单独写选择器时自动复用 `search` 分组。

字段语义详见 `references/selectors.md`。

## 6. `category` / `homeSections` / `filters`

```json
"category": {
  "categories": [ { "id": "rexue", "name": "热血" } ],
  "dynamicCategories": false
}
```

```json
"homeSections": [
  { "id": "latest", "title": "最新更新", "route": "latest",
    "style": "grid", "limit": 18, "more": true },
  { "id": "week", "title": "周表", "route": "week", "style": "schedule" }
]
```

- `style`：`grid` / `list` 只是外观；`schedule` 有语义（周期表按开播日分组）。
- `route` 必须存在于 `routes`，`params` 可带固定参数（如 `{"category":"rexue"}`）。
- 分类 id 为 `all` / `0` / 标题含"全部"的会被跳过，不会生成板块。
- `dynamicCategories: true` 用于采集 API 型站点（分类从接口动态取）。

## 7. 反盗链与网络

```json
"antiHotlinking": {
  "referer": "https://example.com/",
  "userAgent": "可选",
  "headers": { "可选": "附加头" }
}
```

源未写 `referer` 时，取图会兜底用源站 origin。图片 403 / 拿到 5KB 占位图 → 先补这一项。

`network` 仅在上游有特殊网络要求时用（hosts 钉 IP、SNI、DoH、源级代理）；字段定义见 `lib/core/network/model/`，不确定时不要写，继承全局配置更稳。

## 8. 校验与拒绝

应用启动/导入时会跑 `PluginConfig.validate()`，只有四个硬错误：

1. `missing: id`
2. `missing: name`
3. `missing: site.baseUrl`
4. `animeSource requires route "latest"`

其余问题不会报错，只会「抓不到东西」。所以导入成功 ≠ 能用，必须按 `references/troubleshoot.md` 逐段验收。

本地自检：

```bash
python scripts/validate_source.py 源.json
```
