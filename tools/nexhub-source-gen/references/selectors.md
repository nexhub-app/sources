# 选择器语法与字段语义

实现：`lib/core/resolver/builtin_resolver.dart` + `lib/core/utils/html_utils.dart` + `lib/core/utils/json_path.dart`

## 1. 三种选择器引擎

| 写法 | 判定 | 例子 |
|---|---|---|
| CSS | 默认 | `div.item h3` |
| XPath | 以 `//`、`./`、`.//` 开头，或含 `[@` | `//div[@id='list']//a/@href` |
| JSONPath | 以 `$` 开头 | `$.data.list[*].vod_id` |

### ⚠️ 两套语法不要混用

| 场景 | 回退写法 | 按文本筛 | 取干净正文 |
|---|---|---|---|
| 原生 `selectors`（影视 / 漫画 / 原生小说） | **逗号**：`img@data-src, img@src` | XPath `contains()` | 脚本 `context.content.clean` |
| 书源规则 `ruleSearch` / `ruleToc` / `ruleContent` | `||` | `a:contains(文字)` | `@textNodes` |

同理：原生列表字段叫 `list` / `title` / `cover`，书源规则才叫 `bookList` / `bookName` / `bookCoverUrl`。把书源字段名直接写进原生 `selectors` 不会生效。

## 2. HTML 取值写法（最容易写错的地方）

| 写法 | 含义 |
|---|---|
| `div.title` | 取该元素的**文本**（trim 后） |
| `div.title@title` | 取该元素的 `title` 属性 |
| `@href` / `@src` | 取**当前条目元素本身**的属性 |
| `@text` / `@text()` | 取当前条目元素本身的文本 |
| `a@href, img@src` | **逗号分隔多分支**，从左到右，第一个非空结果胜出 |
| `//ul/li/a/@href` | XPath 属性 |
| `./@href` / `./text()` | 相对 XPath，可用于条目内部 |

要点：

- **兜底用逗号，不是 `||`**。`||` 是阅读器书源语法的写法，写进内置 `selectors` 会被当成 CSS 的一部分，结果为空。
- 逗号只在**括号/引号外**才算分支分隔，`div:not(.a, .b)` 不会误拆。
- CSS 引擎是标准 csslib：支持 `:nth-child(2)`、`:not(...)`、`[data-x="1"]`；**不支持** jQuery 扩展 `:contains(...)`、`:eq(...)`。要按文本筛内容请改用 XPath 的 `contains()`。
- `@textNodes` 只有书源（Legado）规则支持，内置选择器不支持。
- 属性名区分大小写，`@data-Src` 取不到值。
- 选择器命中多个节点时：单值字段取第一个；`director` / `actors` / `tags` 这类多值字段会取全部并用「, 」连接。

## 3. 列表类端点（latest / search / explore / category / recommend / related）

```json
"selectors": {
  "search": {
    "list": "ul.list li",
    "id": "a@href",
    "title": "a.title",
    "cover": "img@data-src, img@src",
    "detailUrl": "a@href",
    "description": "p.intro",
    "author": "span.author",
    "status": "span.note",
    "tags": "div.tags a",
    "updatedAt": "span.time",
    "episodeCount": "span.ep",
    "wordCount": "span.words"
  }
}
```

- `list` 缺省为 `div.item`，绝大多数站点抓不到，**必须显式写**。
- `id` 与 `title` 同时为空的条目会被丢弃（广告卡自动过滤）。
- `detailUrl` 没写时退化用 `detail`；两者都没写时，引擎会用 `id`（以 `/` 开头时）拼 `baseUrl` 得到绝对地址，或退化为当前请求 URL —— 所以 `id` 取 `a@href` 是稳妥做法。
- `tags` 支持逗号字符串，也支持多节点。

## 4. 详情端点（detail）

同名字段：`title` / `cover` / `description`（别名 `intro`）/ `author` / `director` / `actors` / `status` / `tags` / `updatedAt` / `wordCount`，另有 `authorUrl` / `tagUrls`（点作者/标签直接检索）。

```json
"detail": {
  "title": "h1.title, //meta[@property='og:title']/@content",
  "cover": "div.pic img@src, //meta[@property='og:image']/@content",
  "description": "div.desc",
  "tags": "div.tags a"
}
```

用 meta 兜底是常用技巧：站点改版时 OG 标签通常还在。

## 5. 剧集 / 章节（episodes / chapters / toc）

```json
"chapters": {
  "list": "ul#chapter-list li",
  "id": "a@href",
  "title": "a",
  "url": "a@href",
  "number": "span.num",
  "updatedAt": "span.time"
}
```

- `episodes` 与 `chapters` 共用实现，写哪个都会互相兜底。
- 条目元素本身是 `<a>` 或内含 `<a>` 时，`url` 不写会自动取 `<a href>`，`title` 不写取链接文本。
- `id` 不写时 = `url`（没有则用 `title`）。
- **漫画章节建议把 `id` 取成章节链接**：图片端点用 `{chapterId}` 就能直通该章页面。

## 6. 漫画图片（images）

三种写法：

```json
"images": { "images": "div.reader img@data-src" }
```

```json
"images": { "images": { "list": "$.data.images", "url": "$.url" } }
```

```json
"images": {
  "images": {
    "config": { "mode": "list", "item": "div.reader img", "src": "data-src" }
  }
}
```

- 字符串写法：`css@attr`；不写 `@attr` 时依次尝试 `data-src` → `data-original` → `src`。
- 结果会做绝对化、去重、广告/占位图过滤。
- 分页型阅读页（一话多页）`config.mode` 可写 `scroll` / `clickMore`，但当前页抽取逻辑一致，翻页需配合脚本。

## 7. 视频（video）

```json
"video": { "video": "video#player@src" }
```

```json
"video": { "video": { "url": "$.data.url", "type": "m3u8" } }
```

- 选择器为 `css@attr` 时优先；没命中会回退内置 `VideoExtractor` 扫 `<video>` / `<source>` / `<iframe>`。
- 播放页地址是加密变量、或真实地址在 JS 里 → 用 `webview` + `script`（见 `references/script-protocol.md`）。
- 需要带 Referer/UA 才能播 → 在 `antiHotlinking` 里声明，或脚本返回 `{url, headers}`。

## 8. 周期表（week）

```json
"week": {
  "dayBlocks": "ul.week-content",
  "dayIndexAttr": "data-key",
  "item": "li",
  "title": "a",
  "detailUrl": "a@href"
}
```

`dayIndexAttr` 的值 0..6 对应周一..周日，引擎据此把条目分到正确的星期。

## 9. JSON 源（JSONPath）

支持的形态（**必须以 `$` 开头**，否则直接返回 null）：

```
$.data.list
$.data.list[0].name
$.data.list[*].name
$..name                递归下降
$.data.list[1:3]       切片，支持 [::2] / [-1]
$.data.list[?(@.type==1)]   条件过滤
```

- key 作用在数组上时自动对每个元素取值（`$.list.id` ≡ `$.list[*].id`）。
- 列表端点先取 `list` 得到数组，再对每个元素用其余字段求值。
- 数字/布尔会自动转字符串，不用额外处理。
