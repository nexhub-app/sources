#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NexHub 源 JSON 自检（零依赖，Windows/macOS/Linux 通用）。

用法：
  python validate_source.py <源.json> [更多.json ...]
  python validate_source.py <源.json> --strict        # 警告也算失败
  python validate_source.py <源.json> --json          # 机器可读输出

检查口径对齐 App 端实现：
  lib/core/models/plugin_config.dart   (字段解析 / validate / 占位符)
  lib/core/resolver/resolver_registry.dart (解析器路由)
  lib/core/resolver/builtin_resolver.dart  (声明式选择器消费)
  lib/core/resolver/script_resolver.dart   (脚本入口 / 返回值)

退出码：0 = 通过（可能有警告），1 = 有错误，2 = 文件读不了。
"""

from __future__ import annotations

import json
import os
import re
import sys

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"

TYPES = {"animeSource", "mangaSource", "novelSource"}
PARSER_TYPES = {"builtin", "hybrid", "script", "xpath", "jsonpath", "css"}
OVERRIDE_TYPES = {
    "builtin", "css", "xpath", "jsonpath", "html",
    "script", "webview", "webview-html", "hybrid",
}
AGE_RATINGS = {"general", "teen", "mature",
               "all", "g", "safe", "0", "13", "13+", "16", "16+", "t",
               "m", "adult", "18", "18+", "r18", "nsfw", "restricted", "2"}

# resolveRouteUrl 认识的内置变量（其余占位符会被清理成空串）
KNOWN_VARS = {
    "page", "keyword", "id", "url", "detailUrl", "category", "mid", "cid",
    "chapterId", "title", "cover", "author", "season_id", "tab", "sort",
}
# 这些别名在引擎内做了映射，容许出现在 route 里
ALIAS_VARS = {"season_id", "seasonId", "book_id", "vod_id", "manga_id"}

# 声明式解析下，列表类端点的必填选择器
LIST_FIELDS = ("title",)
RE_LIST_CLASS = "list"

PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
ARITH_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:[*/+-]\d+)+)\??$")
PLAIN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\??$")


class Finding:
    def __init__(self, level: str, code: str, msg: str, path: str = "") -> None:
        self.level = level
        self.code = code
        self.msg = msg
        self.path = path

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code,
                "message": self.msg, "path": self.path}


def _dup_key_hook(pairs):
    """检测重复键（JSON 解析器默认静默保留最后一个，是高频踩坑点）。"""
    seen = {}
    dups = []
    for k, v in pairs:
        if k in seen:
            dups.append(k)
        seen[k] = v
    if dups:
        seen["__dup_keys__"] = dups
    return seen


def load(path: str, out: list[Finding]):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
    except OSError as e:
        out.append(Finding(ERROR, "io", f"读不到文件：{e}", path))
        return None
    try:
        data = json.loads(raw, object_pairs_hook=_dup_key_hook)
    except json.JSONDecodeError as e:
        out.append(Finding(
            ERROR, "json",
            f"JSON 语法错误：第 {e.lineno} 行第 {e.colno} 列 —— {e.msg}。"
            "常见原因：尾逗号、少引号、字符串里有未转义的换行、注释。", path))
        return None
    if isinstance(data, dict) and "__dup_keys__" in data:
        dups = data.pop("__dup_keys__")
        out.append(Finding(ERROR, "dup-key",
                           f"同一对象里重复的键（后面的会覆盖前面的）：{dups}", path))
    return data


def check_script_entries(data: dict, out: list[Finding]) -> None:
    """脚本 override 的入口函数必须在 script 源码里真实存在。"""
    parser = data.get("parser") or {}
    overrides = parser.get("overrides") or {}
    shared = parser.get("script") or ""
    for api, ov in overrides.items():
        if not isinstance(ov, dict):
            continue
        if ov.get("type") != "script":
            continue
        src = ov.get("script") or shared
        fn = (ov.get("function")
              or (ov.get("entrypoints") or {}).get(api)
              or ((data.get("parser") or {}).get("entrypoints") or {}).get(api)
              or api)
        if not src:
            out.append(Finding(ERROR, "script-missing",
                               f"overrides.{api} 声明 type=script 但没有 script 源码。"))
            continue
        pat = re.compile(
            r"(?:function\s+" + re.escape(fn) + r"\s*\()"
            r"|(?:" + re.escape(fn) + r"\s*=\s*(?:function|\())"
            r"|(?:(?:var|let|const)\s+" + re.escape(fn) + r"\s*=\s*\()")
        if not pat.search(src):
            if shared and shared != src and pat.search(shared):
                out.append(Finding(
                    INFO, "script-entry",
                    f"overrides.{api} 自带 script 里没有 {fn}，它只存在于 parser.script。"
                    f"override 自带 script 时引擎只会执行 override 的脚本，请删掉多余的 script 让共用脚本生效。"))
            else:
                out.append(Finding(
                    ERROR, "script-entry",
                    f"overrides.{api}.function='{fn}'，但脚本里找不到 function {fn}(...)。"
                    f"入口名优先级 override.function > entrypoints > 端点名，写错名字会直接返回空。"))
        if re.search(r"\bawait\b", src):
            out.append(Finding(
                INFO, "script-await",
                f"overrides.{api} 脚本里出现 await：JS 引擎对 Promise 返回值支持不稳定，"
                f"要拿二次请求的数据请改用 __meta 两步协议（见 references/script-protocol.md）。"))
        if re.search(r"\bctx\.", src) and not re.search(
                r"(?:var|let|const)\s+ctx\s*=|ctx\s*=\s*context", src):
            out.append(Finding(
                INFO, "script-ctx",
                f"overrides.{api} 脚本用了 ctx.xxx 却没有定义 ctx："
                f"本应用注入的全局对象名是 context。照抄其它阅读器的脚本时要么整体替换，"
                f"要么在脚本开头写 var ctx = context;"))


def check_placeholders(data: dict, out: list[Finding]) -> None:
    routes = data.get("routes") or {}
    for api, route in routes.items():
        url = route.get("url") if isinstance(route, dict) else route
        if not isinstance(url, str):
            continue
        for m in PLACEHOLDER_RE.finditer(url):
            token = m.group(1)
            if token.endswith("?"):
                base = token[:-1]
            else:
                base = token
            am = ARITH_RE.match(token)
            if am:
                base = am.group(1)
            elif not PLAIN_RE.match(token):
                out.append(Finding(ERROR, "placeholder",
                                   f"routes.{api}.url 里的占位符 {{{token}}} 不合法："
                                   f"只支持 {{名字}} / {{名字?}} / {{名字-1}} / {{名字*30-30}}。"))
                continue
            if base not in KNOWN_VARS and base not in ALIAS_VARS:
                out.append(Finding(
                    INFO, "placeholder-var",
                    f"routes.{api}.url 用了 {{{base}}}：引擎未内置该变量，"
                    f"只有调用方显式传入时才有值，否则会被清理成空串。"))

        if api == "video" and url.strip() != "{url}":
            out.append(Finding(
                INFO, "video-url",
                "routes.video.url 通常应写成 {url}（播放页绝对地址直通）。"
                "写成别的模板可能拼出双 host 坏链。"))
        if api in ("detail", "episodes", "chapters", "toc", "images", "content"):
            id_vars = ("detailUrl", "id", "url", "chapterId", "cid", "mid")
            if not any("{" + v in url for v in id_vars):
                out.append(Finding(
                    WARN, "route-no-id",
                    f"routes.{api}.url 里没有任何作品/章节标识（{{id}} / {{detailUrl}} / "
                    f"{{chapterId}} 等）：每次都会请求同一个地址，多部作品会互相串页。"))


KNOWN_TOP_KEYS = {
    "id", "name", "author", "type", "version", "description", "responseType",
    "useWebview", "stealthMode", "site", "parser", "routes", "selectors",
    "category", "homeSections", "filters", "antiHotlinking", "webviewConfig",
    "comments", "webFavorite", "announcement", "network", "cdn",
    "imageTransform", "ageRating", "enabled", "enabledExplore", "isHidden",
    "deprecated", "migrationMessage", "engine", "_note",
}
KNOWN_WEBVIEW_KEYS = {"adblock", "timeoutSeconds", "extraUserAgent"}


def check_unknown_keys(data: dict, out: list[Finding]) -> None:
    """未知键不会报错但也不会生效——AI 生成的源最容易在这里翻车。"""
    unknown = [k for k in data if k not in KNOWN_TOP_KEYS]
    if unknown:
        out.append(Finding(
            INFO, "unknown-key",
            f"以下顶层键不会被引擎读取（写错名字就等于没写）：{unknown}。"
            f"常见误写：coverUrl→cover、list→selectors.list、timeoutMs→timeoutSeconds。"))
    wv = data.get("webviewConfig")
    if isinstance(wv, dict):
        bad = [k for k in wv if k not in KNOWN_WEBVIEW_KEYS]
        if bad:
            out.append(Finding(
                INFO, "webview-key",
                f"webviewConfig 里的 {bad} 不会被读取（旧 schema 残留）："
                f"当前只认 adblock / timeoutSeconds / extraUserAgent。"))


def check_routes_vs_overrides(data: dict, out: list[Finding]) -> None:
    routes = data.get("routes") or {}
    parser = data.get("parser") or {}
    overrides = parser.get("overrides") or {}
    selectors = data.get("selectors") or {}

    for api in overrides:
        if api not in routes:
            out.append(Finding(
                INFO, "override-orphan",
                f"parser.overrides.{api} 存在但 routes 里没有同名端点 —— 这份覆盖不会被用到。"))

    for api, route in routes.items():
        ov = overrides.get(api) or {}
        otype = ov.get("type") if isinstance(ov, dict) else None
        if otype in ("script", "webview"):
            continue
        if otype == "webview-html":
            if isinstance(ov, dict) and ov.get("script"):
                out.append(Finding(
                    ERROR, "webview-html-script",
                    f"overrides.{api} 是 webview-html：该模式只把渲染后的 HTML 交回声明式引擎，"
                    f"script 永远不会被调用。要么删掉 script 改用 selectors，要么改成 webview。"))
            continue
        # 声明式端点：应当有 selectors.<api>
        if api in selectors:
            sel = selectors[api]
            if isinstance(sel, dict) and "list" not in sel and api in (
                    "latest", "search", "explore", "category", "recommend", "related"):
                out.append(Finding(
                    WARN, "selector-no-list",
                    f"selectors.{api} 没写 list（列表容器）：默认会退回 div.item，多数站点抓不到。"))
            continue
        # 扁平写法（selectors 顶层直接放 list/title/...）也算声明
        flat = "list" in selectors or "title" in selectors
        if not flat and api not in ("video", "content", "images", "mirrors", "folders"):
            out.append(Finding(
                WARN, "selector-missing",
                f"routes.{api} 既没有 overrides 也没有 selectors —— 该端点会按默认规则猜，通常抓空。"))


def check_webview(data: dict, out: list[Finding]) -> None:
    use_wv = bool(data.get("useWebview"))
    overrides = ((data.get("parser") or {}).get("overrides") or {})
    has_wv = any(isinstance(o, dict) and o.get("type") in ("webview", "webview-html")
                 for o in overrides.values())
    if use_wv and not has_wv:
        out.append(Finding(
            INFO, "webview-inert",
            "useWebview=true 但没有任何 webview / webview-html 覆盖："
            "除 video 路由外该开关不生效，列表仍是直连 HTTP。"))

def check_native(data: dict, out: list[Finding], path: str) -> None:
    for key in ("id", "name", "type"):
        if not data.get(key):
            out.append(Finding(ERROR, "required", f"缺少必填字段 {key}。"))
    t = data.get("type")
    if t and t not in TYPES:
        out.append(Finding(ERROR, "type",
                           f"type='{t}' 不合法，只能是 animeSource / mangaSource / novelSource。"))

    site = data.get("site") or {}
    if not isinstance(site, dict):
        out.append(Finding(ERROR, "site", "site 必须是对象。"))
    else:
        if not site.get("baseUrl"):
            out.append(Finding(ERROR, "site", "缺少 site.baseUrl（拼接相对链接的根地址）。"))
        elif not str(site["baseUrl"]).startswith(("http://", "https://")):
            out.append(Finding(ERROR, "site", "site.baseUrl 必须以 http:// 或 https:// 开头。"))
        if not site.get("domain"):
            out.append(Finding(WARN, "site", "建议补 site.domain（如 example.com）。"))
        if site.get("baseUrl", "").endswith("/"):
            out.append(Finding(INFO, "site", "site.baseUrl 结尾多了一个 /，建议去掉。"))

    if t == "animeSource" and "latest" not in (data.get("routes") or {}):
        out.append(Finding(ERROR, "route-latest",
                           "animeSource 必须声明 routes.latest（应用校验会因此直接拒绝该源）。"))

    sid = str(data.get("id") or "")
    if sid and not re.fullmatch(r"[A-Za-z0-9_.\-]+", sid):
        out.append(Finding(WARN, "id-charset",
                           "id 建议只用字母、数字、下划线、连字符（避免空格与中文）。"))

    ver = data.get("version", 1)
    if isinstance(ver, bool) or not isinstance(ver, (int, float, str)):
        out.append(Finding(ERROR, "version",
                           "version 只能是整数，或 \"1.0.4\" 这种以数字开头的字符串。"))
    elif isinstance(ver, str) and not re.match(r"^\d+", ver.strip()):
        out.append(Finding(ERROR, "version",
                           f"version='{ver}' 取不到数字：引擎取第一段转整数，"
                           f"否则回退 1，会导致升级覆盖判定失效。"))
    elif isinstance(ver, (int, float)) and int(ver) < 1:
        out.append(Finding(WARN, "version", "version 建议从 1 开始。"))

    rating = str(data.get("ageRating", "general")).lower()
    if rating not in AGE_RATINGS:
        out.append(Finding(WARN, "ageRating",
                           f"ageRating='{rating}' 无法识别，会回退 general。"))

    parser = data.get("parser") or {}
    if not isinstance(parser, dict):
        out.append(Finding(ERROR, "parser", "parser 必须是对象。"))
    else:
        pt = parser.get("type", "builtin")
        if pt not in PARSER_TYPES:
            out.append(Finding(ERROR, "parser-type",
                               f"parser.type='{pt}' 不合法（builtin / hybrid / script）。"))
        for api, ov in (parser.get("overrides") or {}).items():
            if not isinstance(ov, dict):
                continue
            ot = ov.get("type")
            if ot is not None and ot not in OVERRIDE_TYPES:
                out.append(Finding(ERROR, "override-type",
                                   f"overrides.{api}.type='{ot}' 不合法。"))

    if not (data.get("routes") or {}):
        out.append(Finding(ERROR, "routes", "routes 为空：源至少要有 latest 或 search 端点。"))

    if not data.get("homeSections") and t in ("animeSource", "mangaSource"):
        out.append(Finding(INFO, "home",
                           "未声明 homeSections：应用会自动用 latest + 各分类生成首页板块，可接受。"))

    if t in ("animeSource", "mangaSource") and not (data.get("antiHotlinking") or {}).get("referer"):
        out.append(Finding(INFO, "referer",
                           "未声明 antiHotlinking.referer：图片/视频 CDN 防盗链时可能 403。"))

    check_unknown_keys(data, out)
    check_placeholders(data, out)
    check_routes_vs_overrides(data, out)
    check_webview(data, out)
    check_script_entries(data, out)

    if "/plugins/builtin/" in path.replace("\\", "/") and "version" not in data:
        out.append(Finding(WARN, "builtin-version",
                           "内置源升级必须提升 version，否则不会覆盖用户机器上的旧副本。"))


def check_legado(data: dict, out: list[Finding]) -> None:
    for key in ("bookSourceName", "bookSourceUrl"):
        if not data.get(key):
            out.append(Finding(ERROR, "legado", f"书源缺少 {key}。"))

    forbidden = [k for k in ("id", "name", "type", "site") if k in data]
    if forbidden:
        out.append(Finding(
            WARN, "legado-mixed",
            f"书源里出现了 NexHub 原生字段 {forbidden}：书源模式不读这些键，写了也会被忽略。"))

    rs = data.get("ruleSearch")
    if isinstance(rs, dict) and rs:
        for k in ("bookList", "bookName", "bookUrl"):
            if not rs.get(k):
                out.append(Finding(WARN, "legado-search", f"ruleSearch 缺少 {k}，搜索会空。"))
    elif rs is None:
        out.append(Finding(INFO, "legado-search",
                           "未声明 ruleSearch：该源不支持搜索，只能从发现页进入。"))
    rt = data.get("ruleToc") or {}
    for k in ("chapterList", "chapterName", "chapterUrl"):
        if not rt.get(k):
            out.append(Finding(WARN, "legado-toc", f"ruleToc 缺少 {k}，目录会空。"))
    rc = data.get("ruleContent") or {}
    if not rc.get("content"):
        out.append(Finding(WARN, "legado-content", "ruleContent.content 为空，正文抓不到。"))
    if not data.get("exploreUrl"):
        out.append(Finding(INFO, "legado-explore",
                           "未写 exploreUrl：发现页没有分类入口，只能靠搜索。"))
    check_script_entries(data, out)


def validate(path: str) -> list[Finding]:
    out: list[Finding] = []
    data = load(path, out)
    if data is None:
        return out
    if not isinstance(data, dict):
        out.append(Finding(ERROR, "root", "源文件顶层必须是对象 {}。", path))
        return out
    if "bookSourceUrl" in data or "bookSourceName" in data:
        check_legado(data, out)
    else:
        check_native(data, out, path)
    if not out:
        out.append(Finding("OK", "ok", "结构与字段自检通过。", path))
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    strict = "--strict" in argv
    as_json = "--json" in argv
    files = [a for a in argv if not a.startswith("--")]
    all_results = {}
    failed = False
    for f in files:
        findings = validate(f)
        all_results[f] = [x.as_dict() for x in findings]
        has_error = any(x.level == ERROR or (strict and x.level == WARN) for x in findings)
        failed = failed or has_error
        if as_json:
            continue
        print(f"\n=== {os.path.basename(f)} ===")
        for x in findings:
            tag = {"OK": "[ OK ]", ERROR: "[ERROR]", WARN: "[WARN] ", INFO: "[INFO] "}[x.level]
            print(f"{tag} {x.code}: {x.msg}")
        if has_error:
            print("=> 不通过，先修 ERROR。")
        else:
            print("=> 通过。")
    if as_json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
