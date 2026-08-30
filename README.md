# NexHub 源库（Sources）

NexHub 的**公共源仓库**。这里集中存放所有可导入的源（漫画 / 影视动漫 / 小说），
官方网站 [nexhub-app/website](https://github.com/nexhub-app/website) 的「源仓库」页面
会**动态读取本仓库的 `index.json`**，因此：

> **新增 / 修改一个源，只需要往对应分类文件夹放（或改）一个 JSON 文件，网页会自动更新，不用改网页代码。**

---

## 目录结构

```
.
├─ sources/                  # 源文件（按媒体类型分类）
│  ├─ manga/                 # 漫画源（NexHub 格式）
│  ├─ anime/                 # 影视 / 动漫源（NexHub 格式）
│  └─ novel/                 # 小说源（阅读 / Legado 格式）
├─ scripts/
│  └─ generate_index.js      # 扫描 sources/**/*.json → 生成 index.json
├─ .github/workflows/
│  └─ update-index.yml       # 推送后自动重新生成并提交 index.json
├─ index.json               # 自动生成的清单（网页读取它）
└─ README.md
```

---

## 如何添加一个新源（"上传到源库"）

两种方式任选其一，本质都是**往 `sources/<分类>/` 放一个 JSON**：

1. **GitHub 网页直接传**：在对应分类文件夹点 `Add file → Upload files`，把 JSON 传上去，写个提交说明，提交即可。
2. **提 Pull Request**：Fork 本仓库，把 JSON 放进对应文件夹，提 PR 合并。

提交后，GitHub Action 会自动：
- 运行 `scripts/generate_index.js` 重新生成 `index.json`；
- 把新的 `index.json` 提交回仓库。

网站下次打开就会自动显示这个新源，并带上「导入」按钮。

> ⚠️ 分类文件夹只能是 `manga` / `anime` / `novel` 之一，文件名建议用 `类型_站点标识.json`（如 `manga_goda.json`）。

---

## 源的格式

源库同时支持两种格式，App 都能导入：

| 格式 | 识别方式 | 说明 |
|------|----------|------|
| **NexHub 格式** | JSON 顶层有 `"type": "mangaSource" / "animeSource" / "novelSource"` | App 原生插件源，含 `site` / `parser` / `routes` / `selectors` |
| **Legado（阅读）格式** | JSON 顶层有 `"bookSourceName"`，无 `type` | 小说书源，App 通过书源（shuyuan）通道导入 |

生成器会自动识别格式并写进 `index.json` 的 `format` 字段（仅用于网页显示标签）。

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

## 本地预览 / 手动生成

把本仓库克隆到本地后：

```bash
node scripts/generate_index.js
```

会立刻生成（或更新）`index.json`。想换原始文件根地址（比如自托管镜像）可设置环境变量：

```bash
RAW_BASE=https://你的镜像地址/main node scripts/generate_index.js
```

---

## 网页如何读取

网站 `sources.js` 改为 `fetch` 本仓库的 `index.json`，把每条映射成网页需要的字段后渲染。
`index.json` 中每条 `id` 已带分类路径（如 `manga/manga_goda`），配合导入链接前缀
`https://cdn.jsdelivr.net/gh/nexhub-app/sources@main/sources/`，网页的「导入」按钮
能直接拼出正确的原始文件地址（走 jsDelivr CDN，国内可访问）。详见 `website-patch/` 目录里的网页改造补丁。
