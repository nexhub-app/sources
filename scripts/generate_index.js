#!/usr/bin/env node
"use strict";

/*
 * generate_index.js
 * ----------------------------------------------------------------------------
 * 扫描 sources/<分类>/*.json，生成 index.json（源库清单）。
 * 网页 (nexhub-app/website) 只读取 index.json，因此新增/修改源后无需改网页代码。
 *
 * 判定规则：
 *   category : 取文件相对 sources/ 的第一级文件夹名（manga / anime / novel）。
 *   format   : JSON 顶层有 type: "xxxSource" -> "nexhub"（NexHub 原生格式）；
 *              有 bookSourceName 无顶层 type -> "legado"（阅读/书源格式）。
 *              两种格式 App 都支持导入，所以 builtin 一律为 true。
 *   id       : "<分类>/<文件名(去扩展名)>"，如 "manga/manga_goda"。
 *              网页用 RAW_BASE + id + ".json" 拼导入链接，天然落到正确子目录。
 *
 * 运行：node scripts/generate_index.js
 * 可选环境变量 RAW_BASE 覆盖原始文件根地址（默认 nexhub-app/sources@main）。
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const SOURCES_DIR = path.join(ROOT, "sources");
const OUT_FILE = path.join(ROOT, "index.json");
const RAW_BASE =
  process.env.RAW_BASE || "https://cdn.jsdelivr.net/gh/nexhub-app/sources@main";

const ALLOWED_CATEGORIES = ["manga", "anime", "novel"];

function detectFormat(obj) {
  if (obj && typeof obj.type === "string" && obj.type.endsWith("Source")) return "nexhub";
  if (obj && typeof obj.bookSourceName === "string") return "legado";
  return "unknown";
}

function walk(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (entry.isFile() && entry.name.toLowerCase().endsWith(".json")) out.push(full);
  }
  return out;
}

function main() {
  const files = walk(SOURCES_DIR);
  const sources = [];
  const seen = new Set();

  for (const file of files) {
    const rel = path.relative(SOURCES_DIR, file).split(path.sep);
    const category = rel[0];
    const fileName = rel[rel.length - 1];
    const base = fileName.replace(/\.json$/i, "");

    let raw;
    try {
      raw = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch (e) {
      console.warn(`[skip] 解析失败: ${file} -> ${e.message}`);
      continue;
    }

    if (!ALLOWED_CATEGORIES.includes(category)) {
      console.warn(`[skip] 未知分类文件夹: ${category} (文件 ${file})`);
      continue;
    }

    const format = detectFormat(raw);
    const id = `${category}/${base}`;
    if (seen.has(id)) {
      console.warn(`[skip] 重复 id: ${id}`);
      continue;
    }
    seen.add(id);

    const name = format === "legado" ? raw.bookSourceName : raw.name || base;
    const version = raw.version != null ? raw.version : 1;
    const baseUrl =
      format === "nexhub"
        ? (raw.site && raw.site.baseUrl) || ""
        : raw.bookSourceUrl || "";
    const disp = raw.display || {};
    const desc = {
      zh: disp.descZh || "",
      en: disp.descEn || ""
    };
    const ageRating = raw.ageRating || "general";
    const rawUrl = `${RAW_BASE}/sources/${category}/${fileName}`;

    sources.push({
      id,
      category,
      type: category, // 供网页筛选标签使用（manga/anime/novel）
      format,
      name,
      version,
      baseUrl,
      rawUrl,
      builtin: true, // 源库中的源均可导入
      desc,
      ageRating
    });
  }

  sources.sort(
    (a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name)
  );

  const index = {
    generatedAt: new Date().toISOString(),
    count: sources.length,
    sources
  };

  fs.writeFileSync(OUT_FILE, JSON.stringify(index, null, 2) + "\n", "utf8");
  console.log(`[ok] 生成 index.json：${sources.length} 个源`);
  const byCat = {};
  for (const s of sources) byCat[s.category] = (byCat[s.category] || 0) + 1;
  console.log(
    "  分类统计:",
    JSON.stringify(byCat),
    " | 格式:",
    Array.from(new Set(sources.map((s) => s.format))).join(",")
  );
}

main();
