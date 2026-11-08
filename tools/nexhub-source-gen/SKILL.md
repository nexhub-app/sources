---
name: nexhub-source-gen
description: 在 NexHub 里生成或修好一个源（动漫/漫画/小说）。既能产出「覆盖评论/登录/网络/收藏/公告/周表/筛选」的全功能 TODO 骨架，也能按「源即插件」写真实可用的源、排查抓不到/播不了。含 17 条硬规则、五步工作流、站点探测与自检脚本、8 套模板、选择器与 JS 沙箱协议、排障手册，以及不会编程的人让 AI 代做源的对话剧本。当用户说「生成/写一个源」「按教程出完整源」「加个源」「适配某个网站」「源不能用了」「抓不到封面」「播不了」「搜索没结果」时使用。
type: skill
agent_created: true
---

# NexHub 源生成与修复

源的唯一形态是一个 JSON 文件（**源即插件**）。**绝不为了让某个站能用而去改 Dart**。

## 0. 先分流：用户要哪一种

| 信号 | 走哪条路 |
|---|---|
| 「帮我做个源 / 我不会编程 / 这个站能不能看」 | **小白模式**：读 `references/nontech-mode.md`，只问网址 + 类型，技术判断全由你做 |
| 「生成一份完整源 / 覆盖所有功能 / 按教程出骨架」 | **全功能骨架**：复制 `assets/templates/anime-full.json` 或 `novel-legado-full.json`，逐块填 `TODO_` |
| 「写个新源 / 适配这个站」 | **开发者模式**：进 §2 五步工作流，按 §3 选路线 |
| 「源报错了 / 某功能空」 | **排障模式**：读 `references/troubleshoot.md`，先判生死再改一处 |

小白模式三条纪律：不问技术细节；一次只推进一段（搜索→详情→目录→图片/播放）；每段都给可验证的交付物。

## 1. 铁律

1. **解析规则只写在 JSON 里**。若需要改 Dart 才能支持某站，方案就错了。
2. **能直连就不开 WebView，能用选择器就不写脚本**。WebView 慢且易崩；脚本 10 秒超时且难调。
3. **先探测再写**，判断基于真实响应。
4. **沙箱结论 ≠ 真机结论**：网络、防盗链、验证流程只有真机能验。

## 2. 五步工作流

命令都在本技能目录下执行（`scripts/`、`assets/` 相对于 SKILL.md）。

```bash
# ① 探测（接口 / 直连 / 需渲染 / 强反爬 / 域名已弃用）
python scripts/probe_site.py https://站点首页 --save page.html

# ② 选模板填字段；③ 自检（必须 0 ERROR）
python scripts/validate_source.py 源.json
```

④ 交付 + 让用户按清单真机验收（`references/nontech-mode.md` §7）。

⑤ 改完的源 `version` +1 再交付，否则覆盖不了已装副本。

> 两个脚本由你（AI）运行，用户无需装 Python。没有 python 时用 node 做等价检查，或让 App 导入时校验。

## 3. 解析路线选择

| 站点特征 | 配置 |
|---|---|
| 服务端渲染、直连拿得到内容 | `parser.type: hybrid`，端点 `builtin`，写 `selectors` |
| 站点自带 JSON 接口 | `responseType: json`，端点 `jsonpath`，`selectors` 用 `$.` 路径 |
| 403 / Cloudflare / 滑块验证 | **被拦的那个端点** `overrides.<端点>.type: webview-html`，用户手动过一次；播放用 `webview`+script |
| 200 小页面「请稍候」拦截、内联 JS 写 cookie 后自跳转（**无**人工要素） | 该端点 `script` 覆盖：现取挑战令牌 + `__meta` 二跳带 Cookie（见 `references/troubleshoot.md` §0.4），不开 webview |
| 内容靠 JS 渲染 | 优先脚本读内联 JSON（`__NEXT_DATA__` 等），否则 `webview-html` |
| 需要签名 / 解密 / 二次请求 | 端点 `script`，用 `__meta` 两步协议 |
| 小说 | 直接写 Legado 书源 JSON，应用自动识别 |

## 4. 最小可用骨架

先用最小源跑通「搜索 + 详情」，再加目录/图片/播放。可复制 `assets/templates/minimal.json`，或内联：

```json
{
  "id": "manga_example",
  "version": 1,
  "name": "示例漫画",
  "type": "mangaSource",
  "responseType": "html",
  "site": { "domain": "example.com", "baseUrl": "https://example.com" },
  "parser": { "type": "hybrid", "overrides": { "search": { "type": "builtin" } } },
  "routes": {
    "search": { "url": "/search?q={keyword}", "method": "get", "responseType": "html" },
    "detail": { "url": "{detailUrl}", "method": "get", "responseType": "html" }
  },
  "selectors": {
    "search": { "list": "div.item", "title": "h3", "cover": "img@src", "detailUrl": "a@href" },
    "detail": { "title": "h1", "description": "div.intro" }
  },
  "enabled": true, "enabledExplore": true
}
```

## 5. 全功能骨架（要「覆盖全部功能」时）

复制 `assets/templates/anime-full.json`（影视）/ `novel-legado-full.json`（小说）：评论、登录、网络、网络收藏、公告、周更表、猜你喜欢、筛选、发布页镜像全部在位，`TODO_` 待填。

落地规则：

1. 逐块决定「填真实值 / 整块删掉」，**不要留 TODO 上线**。
2. 需要哪些块、每个块的关键字段 → `references/full-feature-blocks.md`（含 comments.login 三种登录、network 生效顺序、schedule/recommend/filters 写法）。
3. 字段真值仍以 `references/field-spec.md` 为准。

## 6. 十七条硬规则（踩过的坑）

1. `selectors.<端点>` 必须有 `list`；不写默认 `div.item`，基本抓空。
2. 多分支兜底用**逗号**：`"img@data-src, img@src"`。`||` 只在书源规则里有效。
3. 相对链接靠透传补全：列表 `id`/`detailUrl` 取 `a@href`，`detail` 路由写 `{detailUrl}`，`video` 路由写 `{url}`。
4. 漫画章节把 `id` 取成章节链接，`images` 路由写 `{chapterId}` 即可直通该章。
5. `webview-html` 端点**不要**写 `script`：渲染后的 HTML 只交给声明式引擎。
6. 要嗅探播放地址才用 `webview` + IIFE 脚本，脚本必须自己 `return` 字符串。
7. JS 里对象叫 `context`（不是 `ctx`）；拿二次请求的数据用 `__meta` 两步。**入口函数（parseVideo/parseList 等）一律写同步**：签名/哈希用脚本内嵌纯 JS 实现现算（`references/duanju-patterns.md` §2.5），不依赖 `context.crypto` 的异步桥——async 入口在引擎层只有三档降级兜底（Dart-Future 识别 + handlePromise，桌面端已实证可落地，真机/鸿蒙桥未验），签名站不要赌。`context.crypto` 仅限脚本内部 `await` 与 `__processor`。单条 meta 的处理器首参是 `[data, headers]` 数组，需归一化。加密/签名站先读 `references/duanju-patterns.md`；聚合多线路影视站的探活式样见 `references/troubleshoot.md` §6.1。
8. `animeSource` 必须有 `routes.latest`，否则校验直接拒绝。
9. 图片 403 / 全是占位图 → 先补 `antiHotlinking.referer`；脚本源封面全挂且图片直开 200 → 脚本返回了相对路径，须在脚本内补全绝对地址（图片层把非 http(s) 当本地文件，永不发请求；列表与详情两处都要）。
10. 改内置源（`plugins/builtin/`）必须 `version` +1；该目录被 gitignore、需重编译才进包。
11. 未经 `validate_source.py` 与真机验收，不说「做好了」。
12. 站点专属逻辑只写在该站的 JSON 里，不进共享代码。
13. **「抓不到」先判生死**：整站返回 `Welcome to nginx` / Apache 默认页 / 200 但只有几百字节 → 域名已弃用，改解析毫无意义（先找新域名，无解就标 `deprecated` + `migrationMessage`）。
14. **人机验证（滑块/图形码/Cloudflare）只走 `webview-html`**：用户在应用内手动过一次，同 (源,路由,URL) 复用。不写自动过验证的脚本；只拦某端点就只给那个端点配，不要顺手开 `useWebview`。但**无人工要素**的 JS 自动挑战（200 小页面、内联写 cookie 自跳转）不走 webview：脚本两步现取令牌即可（§3 表与 `references/troubleshoot.md` §0.4）。
15. **搜索地址不要猜**：读首页 `<form action>` + `input name`（probe 会打印），再决定路径式还是 `?wd=` 查询式。搜索页挂人机验证墙时，**先找站方免验证的联想 JSON 接口**（MacCMS `/index.php/ajax/suggest` 形态），webview-html 是最后手段——自制验证页不在 App 检测特征库里，会被当正常内容解析、永远不弹验证入口（`references/duanju-patterns.md` §11）。
16. **XPath 谓词只写属性函数形态**：`[contains(@k,'x')]` / `[starts-with(@k,'v')]` / `[@k='v']` / 多段串联 `[c1][c2]`。**节点集谓词（谓词里写路径：`li[.//a[...]]`、`li[a]`、`li[contains(.,'x')]`）与 `and`/`or` 组合一律静默返回 0 条**——页面肉眼有内容、日志 elements=0 时先怀疑这个。修法=把条目定成叶子锚点（`//容器//a[卡片类]`，字段写 `@title`/`@href` 截取）；lxml 自测通过不算数，拿不准用引擎能力探针（`references/selectors.md` 能力边界表 + `references/troubleshoot.md` §0）。
17. **「分类不全」先查筛选面板再猜 type id**：nav 常只有一个类型，完整浏览维度（年份/地区/排序）藏在分类页筛选面板、走与搜索共用的查询串。用 `filters` 块 + `{param?}` 可选占位接入（空值整段移除），别把年份做成十几个分类 Tab；「视频不清晰」按三分法排查（路径标签≠码率 → 签名对照 → 素材上限），见 `references/duanju-patterns.md` §15/§16 与 `scripts/probe_play_quality.py`。

## 7. 交付与提交

- 交付物是「**一个 .json 文件 + 3 步验收**」，不要贴一屏代码。
- 源 JSON 里的站点字段是功能必需；但提交说明、文档、聊天回复与**本技能的所有沉淀（references/新增文档）里不点名具体源站**——不写站名、域名、密钥/设备串等可识别常量，只沉淀源无关的本质规律；站点专属细节以各站基准实现与源 JSON 为准。
- 内置源不走常规发版：`plugins/builtin/*.json` 被 gitignore，改完需重编译重装；分享靠导入 json。

## 8. 资源地图

| 文件 | 什么时候读 |
|---|---|
| `references/field-spec.md` | 字段名、占位符、version/导入规则、校验口径 |
| `references/selectors.md` | CSS/XPath/JSONPath、图片/视频/周期表选择器、两套语法别混用 |
| `references/script-protocol.md` | 写脚本、`context.*` API、`__meta` 批量/渲染、坑表 |
| `references/site-patterns.md` | 站点类型判定、搜索地址四形态、各类站点套路 |
| `references/duanju-patterns.md` | 短剧 API 站：签名/加密/登录token、大整数ID精度、POST中文转义、_ROUTER_DATA 抽取、#ep= 模式 |
| `references/troubleshoot.md` | 任何「抓不到/播不了/空白」；§0 生死判定与 lxml 自测 |
| `references/full-feature-blocks.md` | 要全功能源时逐块填法与高级块写法 |
| `references/nontech-mode.md` | 用户不会编程，或要交付给人验收 |
| `assets/templates/*.json` | 8 套模板：minimal / anime-html / anime-json-api / anime-full / manga-html / manga-webview / novel-legado / novel-legado-full |
| `scripts/probe_site.py` | 动手前判路线（含域名弃用判定） |
| `scripts/validate_source.py` | 每次改完必跑（结构+脚本入口+占位符+未知键） |

## 9. 官方教程与参考实现

- 在线教程：<https://nexhub-app.github.io/website/docs-tutorial.html>
- 仓库文档：`docs/developer-guide.md`（含 `.en.md`）
- 同类型内置源就是最好的参照：`ls plugins/builtin/`（pms_* 影视 / manga_* 漫画 / novel_* 小说）

教程与代码冲突时**以 `lib/core/models/plugin_config.dart` 的解析为准**，并在答复里说明这个口径。
