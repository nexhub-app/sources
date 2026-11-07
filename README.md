# NexHub 源库（Sources）

NexHub 的**公共源仓库**：漫画 / 影视媒体 / 小说，对应 `sources/` 下的三个分类文件夹。
官方网站 [nexhub-app/website](https://github.com/nexhub-app/website) 的「源仓库」页面会**动态读取本仓库的 `index.json`**，所以：

> **新增 / 修改一个源，只需要往对应分类文件夹放（或改）一个 JSON 文件，网页会自动更新，不用改网页代码。**

**不会写源、也不懂编程？** 让 AI 帮你做：见 [`tools/nexhub-source-gen`](./tools/nexhub-source-gen/README.md)——准备两三个链接，就能拿到一个可导入的 `.json`。

---

## 目录结构

```
.
├─ sources/                       # 源文件（按媒体类型分类，只允许这三个文件夹）
│  ├─ manga/                      # 漫画源（NexHub 格式）
│  ├─ media/                      # 影视 / 短剧 / 媒体源（NexHub 格式，源内 type 仍是 animeSource）
│  └─ novel/                      # 小说源（NexHub 格式或 Legado 书源格式都行）
├─ scripts/
│  └─ generate_index.js           # 扫描 sources/**/*.json → 生成 index.json
├─ tools/
│  └─ nexhub-source-gen/          # 给 AI 用的「源生成 / 修复」技能（新手从这里开始）
│     ├─ README.md                #   小白向：几种让 AI 代做的方式
│     ├─ SKILL.md                 #   给 AI 的规范（分流、铁律、流程）
│     ├─ prompts/                 #   可直接复制的提示词
│     ├─ references/              #   字段 / 选择器 / 脚本 / 排障手册
│     ├─ assets/templates/        #   模板源（含全功能 TODO 骨架）
│     └─ scripts/                 #   probe_site.py / validate_source.py
├─ .github/workflows/
│  └─ update-index.yml            # 推送后自动重新生成并提交 index.json
├─ index.json                     # 自动生成的清单（网页读它，别手改）
└─ README.md
```

> `tools/` 只服务于写源的人，不参与 `index.json` 索引，也不影响 App 导入。

---

## 怎么加一个源

### 方式 A：让 AI 生成（推荐给不写代码的人）

1. 打开 [`tools/nexhub-source-gen/README.md`](./tools/nexhub-source-gen/README.md)，按里面任一种方式把网址交给 AI；
2. 拿到 `.json` 后，先用 NexHub「源管理 → 导入文件」**自己验一遍**（能搜到、能打开详情、能看）；
3. 验过再放进本仓库（走方式 B 或 C）。

### 方式 B：GitHub 网页直接传

在对应分类文件夹点 `Add file → Upload files`，把 JSON 传上去，写个提交说明，提交即可。

### 方式 C：提 Pull Request

Fork 本仓库 → 把 JSON 放进对应文件夹 → 提 PR。

提交后 GitHub Action 会自动跑 `scripts/generate_index.js` 重新生成 `index.json` 并提交回仓库；网站下次打开就会显示这个新源，并带上「导入」按钮。

> ⚠️ 分类文件夹只能是 `manga` / `media` / `novel`；文件名建议 `类型_站点标识.json`（如 `manga_example.json`），**不要带空格与中文**。

---

## Skill 使用说明：让 AI 代写源

本仓库带一个给 AI 用的技能：[`tools/nexhub-source-gen`](./tools/nexhub-source-gen/README.md)。
它不是 App 的功能，而是一套**操作手册 + 检查工具**——AI 读了它就知道源该怎么写、怎么自查；你只需要跟 AI 说话。

### 三种用法

| 用法 | 适合谁 | 怎么做 |
|---|---|---|
| **装成本地技能**（推荐） | 用 WorkBuddy | 建一条目录链接指向 `tools/nexhub-source-gen`，之后一句话就能用；命令见工具 README「方式 1」 |
| **贴提示词** | 用 ChatGPT / Claude / DeepSeek / 豆包 | 把 `SKILL.md` 附给 AI + 复制 `prompts/quick.md` 里的提示词 |
| **给网页源码** | 站点打不开、AI 抓不到 | 浏览器「另存为 → 仅网页 HTML」，把首页/搜索页/详情页丢给 AI，用 `prompts/with-html.md` |

### 对 AI 说什么（照抄）

> 帮我做个 NexHub 源，站点是 `https://xxx.com`，我想看漫画。搜索页是 ……，详情页是 ……
>
> 这个源的搜索不出结果了（附 json），帮我看是哪一步断了。
>
> `https://xxx.com` 能不能做成源？先别写，告诉我判断依据。

### 技能会替你做什么

- **先探测再动手**：判断站点是自带接口、普通网页、靠浏览器渲染、有人机验证，还是域名已经没站了；
- **按规范写**：源即插件，只产出一个 JSON，不改 App、不改网页；
- **自检**：用 `tools/nexhub-source-gen/scripts/validate_source.py` 查字段名、脚本入口、占位符、重复键（0 ERROR 才算过）；
- **给验收步骤**：拿到 JSON 后照 3 步清单在 App 里试。

### 技能的边界

不绕验证码、不碰付费墙、不抓要登录才可见的内容、救不活已关停的站点。遇到这些它会直接告诉你，而不是硬做。

> 维护提示：技能文件就在 `tools/nexhub-source-gen/` 里（`SKILL.md` 主文件、`references/` 细节、`prompts/` 提示词、`scripts/` 工具）。改仓库即生效，不用另外同步副本。

---

## 源的格式

源库同时支持两种格式，App 都能导入：

| 格式 | 识别方式 | 说明 |
|------|----------|------|
| **NexHub 格式** | JSON 顶层有 `"type": "mangaSource" / "animeSource" / "novelSource"` | App 原生插件源，含 `site` / `parser` / `routes` / `selectors` |
| **Legado（阅读）格式** | JSON 顶层有 `"bookSourceName"`，无 `type` | 小说书源，App 通过书源（shuyuan）通道导入 |

生成器会自动识别格式并写进 `index.json` 的 `format` 字段（仅用于网页显示标签）。

> 注意：**文件夹名是 `media`，源内 `type` 仍然是 `animeSource`**。分批改名时只动了目录，没动源格式（历史源继续有效）。

---

## 提交前自检（6 条）

1. **JSON 能解析**：`python -c "import json;json.load(open('你的源.json',encoding='utf-8'))"`。
2. **必填齐全**：NexHub 格式至少 `id` / `name` / `type` / `site.baseUrl`；`animeSource` 还必须有 `routes.latest`。
3. **自查脚本 0 ERROR**（推荐）：
   ```bash
   python tools/nexhub-source-gen/scripts/validate_source.py sources/media/你的源.json
   ```
4. **自己真机验过**：能出卡片、能进详情、能看内容，不是"理论上能用"。
5. **不含私货**：不写死别人的 Cookie / 账号 / 密钥；只抓站点公开可见内容，不绕验证码、不碰付费墙。
6. **站点还活着**：如果主域只剩服务器默认页（`Welcome to nginx` 之类），别提交这个源；已收录的源失效见下文。

---

## 命名与版本

- **文件名**：`类型_站点标识.json`，全小写，只用字母数字下划线连字符。
- **`version`**：整数，新源从 `1` 开始；**更新已收录的源必须 +1**，否则用户机器上的旧副本不会被覆盖（App 按版本号决定升级）。
- **`id`**：源内 `id` 与文件名保持一致更省心；同名源按 `version` 升级 / 跳过。

---

## 给源声明年龄分级（建议）

每个源都应在 JSON 顶层声明 `ageRating`，否则网页与 App 默认按「全年龄」处理。取值三选一：

| 值 | 含义 | 说明 |
| --- | --- | --- |
| `"general"` | 全年龄 | 任何用户均可浏览（默认值） |
| `"teen"` | 青少年 (16+) | 可能含轻度暴力 / 擦边内容 |
| `"mature"` | 成人 (18+) | 明确的成人 / 限制级内容，开启年龄限制时会被隐藏 |

```json
{
  "ageRating": "mature"
}
```

生成器会把它透传到 `index.json` 的 `ageRating` 字段，App 与网页据此展示分级徽章。兼容别名：`general` 还可写 `all/safe` 等，`mature` 还可写 `adult/r18/nsfw` 等（详见 App 端 `SourceAgeRating.parse`）。

---

## 给源加双语描述（可选）

默认网页会显示源的名称和域名。若想显示更友好的简介，在源 JSON 里加一个 `display` 块即可
（App 会忽略不认识的字段，不影响导入）：

```json
{
  "display": {
    "descZh": "漫画源，支持韩漫、国漫、日漫等分类。",
    "descEn": "Manga source with KR/CN/JP sections."
  }
}
```

`descZh` / `descEn` 留空或省略时，网页自动退化为只显示分类和域名。

---

## 已收录的源失效了怎么办

| 情况 | 做法 |
|---|---|
| 站方**换了域名** | 改 `site.baseUrl` 与 `site.mirrors`，`version` +1 |
| 站方**彻底关站** | 加 `"deprecated": true` + `"migrationMessage": "站点已停用：<原因>"`，`version` +1。App 会在源列表标「已失效」并提示用户，而不是让人以为是自己网络问题 |
| 只是**某个功能坏了**（搜索/播放） | 修好后再提，`version` +1；修不动就按上一行处理 |

---

## 本地预览 / 手动生成

把本仓库克隆到本地后：

```bash
node scripts/generate_index.js
```

会立刻生成（或更新）`index.json`。想换原始文件根地址（比如自托管镜像）可设置环境变量：

```bash
RAW_BASE=https://你的镜像地址/main node scripts/generate_index.js
```

> `index.json` 由脚本生成并由 Action 自动提交，**不要手改**。

---

## index.json 字段说明（自动生成）

| 字段 | 说明 |
|---|---|
| `generatedAt` / `count` | 生成时间 / 源总数 |
| `sources[].id` | `<分类>/<文件名去扩展名>`，如 `manga/manga_example` |
| `sources[].category` / `type` | `manga` / `media` / `novel`（`type` 供网页筛选） |
| `sources[].format` | `nexhub` 或 `legado` |
| `sources[].name` / `version` / `baseUrl` | 展示名 / 版本 / 站点根地址 |
| `sources[].rawUrl` | 原始文件地址（`RAW_BASE + sources/分类/文件名`），网页「导入」按钮直接用它 |
| `sources[].builtin` | 源库中的源恒为 `true`（都可导入） |
| `sources[].desc` | `{ zh, en }`，来自源里的 `display` 块 |
| `sources[].ageRating` | `general` / `teen` / `mature`，缺省按 `general` |

网页拿到 `index.json` 后自行映射渲染；新增源不需要改网页代码。

---

## 网页如何读取

网站 `sources.js` 会 `fetch` 本仓库的 `index.json`，把每条映射成网页需要的字段后渲染。
`index.json` 中每条 `id` 已带分类路径（如 `manga/manga_example`），配合导入链接前缀
`https://cdn.jsdelivr.net/gh/nexhub-app/sources@main/sources/`，网页的「导入」按钮能直接拼出正确的原始文件地址（走 jsDelivr CDN，国内可访问）。
