#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点探测：在动手写源之前，先判断这个站该怎么抓（零依赖）。

用法：
  python probe_site.py <URL>                 # 直接抓线上页面
  python probe_site.py --file page.html      # 分析本地保存的 HTML/JSON
  python probe_site.py <URL> --save out.html # 顺手存一份，便于细看
  python probe_site.py <URL> --cookie "a=b" --ua "自定义UA" --timeout 25

输出：状态 / 反爬 / 内容类型 / 结构线索 / 建议解析路线。
仅供源作者在本地判断技术路线，不替代 App 内真机验证。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CHALLENGE_MARKS = [
    "just a moment", "checking your browser", "cf-chl", "challenge-platform",
    "attention required", "cf-error-details", "__cf_chl", "captcha",
    "enable javascript and cookies", "ddos protection", "人机验证",
    "安全验证", "访问验证", "请稍候", "正在验证",
]
SPA_MARKS = ["__next_data__", "window.__nuxt__", "window.__initial_state__",
             'id="app"', "id='app'", 'id="root"', "data-reactroot", "/@vite/client"]


def fetch(url: str, ua: str, cookie: str, timeout: int):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        **({"Cookie": cookie} if cookie else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, dict(r.headers), raw, r.geturl(), None
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return e.code, dict(e.headers or {}), body, url, None
    except Exception as e:  # 超时 / DNS / TLS
        return None, {}, b"", url, e


def sniff_charset(headers: dict, raw: bytes) -> str:
    ct = headers.get("Content-Type", "") or headers.get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ct, re.I)
    if m:
        return m.group(1)
    m = re.search(br'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
    if m:
        return m.group(1).decode("ascii", "ignore")
    return "utf-8"


def norm_href(h: str) -> str:
    h = h.strip()
    h = re.sub(r"\d+", "{n}", h)
    h = re.sub(r"/(\w{2,})/{n}(/|$)", r"/\1/{n}\2", h)
    return h[:90]


def analyze_html(html: str, out: list[str]) -> None:
    low = html.lower()
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    out.append(f"标题：{title.group(1).strip()[:80] if title else '（无）'}")

    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ",
                  html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", "", text)
    ratio = len(text) / max(len(html), 1)
    out.append(f"正文密度：{ratio:.2%}（HTML {len(html)/1024:.1f} KB，可见文字 {len(text)} 字）")
    if ratio < 0.02 and len(html) > 30000:
        out.append("  → 密度很低：很可能是前端渲染（SPA），直连只能拿到骨架。")

    for mark in SPA_MARKS:
        if mark in low:
            out.append(f"  → 命中前端框架标记 `{mark}`：内容多半由 JS 渲染。")
            break

    links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.I)
    out.append(f"链接数：{len(links)}")
    if links:
        cnt = Counter(norm_href(h) for h in links if h and not h.startswith(
            ("javascript:", "mailto:", "#")))
        out.append("  高频链接形态（可作列表/详情/翻页线索）：")
        for pat, n in cnt.most_common(8):
            if n >= 2:
                out.append(f"    {n:>3}x  {pat}")

    imgs = re.findall(r"<img[^>]+>", html, re.I)
    lazy = [a for a in ("data-src", "data-original", "data-lazy-src", "data-echo")
            if a in low]
    out.append(f"图片数：{len(imgs)}，懒加载属性：{', '.join(lazy) if lazy else '未发现'}")
    if lazy:
        out.append("  → 封面选择器建议写成 `img@{0}, img@src` 逗号兜底（内置选择器不用 ||）。".format(lazy[0]))

    forms = re.findall(r"<form[^>]*>.*?</form>", html, re.S | re.I)
    for f in forms[:3]:
        names = re.findall(r'<input[^>]+name=["\']([^"\']+)["\']', f, re.I)
        action = re.search(r'action=["\']([^"\']*)["\']', f, re.I)
        if names:
            out.append(f"搜索表单：action={action.group(1) if action else '(空)'} 字段={names}")
            out.append("  → 搜索路由可用 `?{}={{keyword}}` 试探。".format(names[0]))

    # 列表容器候选：ul/ol 里 li 数量 >= 3 的块（最常见的卡片列表形态）
    for m in re.finditer(r'<(ul|ol)([^>]*)>(.*?)</\1>', html, re.S | re.I):
        cls = re.search(r'class=["\']([^"\']+)["\']', m.group(2) or "")
        n = len(re.findall(r'<li[\s>]', m.group(3), re.I))
        if n >= 3:
            sel = f"{m.group(1)}.{cls.group(1).split()[0]}" if cls else m.group(1)
            out.append(f"列表容器候选：{sel}  （内含 {n} 个 li）")

    classes = Counter(re.findall(r'class=["\']([^"\']+)["\']', html, re.I))
    hits = [(c, n) for c, n in classes.most_common(40) if n >= 6]
    if hits:
        out.append("高频 class（候选列表容器）：")
        for c, n in hits[:10]:
            out.append(f"    {n:>3}x  .{c.replace(' ', '.')}")

    if re.search(r"<video|<source|<iframe", low):
        out.append("发现 video/source/iframe 标签：视频源可先试 selectors.video。")


def walk_json(node, path="$.", depth=0, acc=None) -> None:
    if acc is None:
        acc = []
    if depth > 6:
        return
    if isinstance(node, dict):
        for k, v in list(node.items())[:40]:
            walk_json(v, f"{path}{k}.", depth + 1, acc)
    elif isinstance(node, list) and node:
        if isinstance(node[0], dict):
            acc.append((path.rstrip("."), len(node), node[0]))
        else:
            acc.append((path.rstrip("."), len(node), node[:1]))
    return acc


def analyze_json(text: str, out: list[str]) -> None:
    try:
        data = json.loads(text)
    except Exception as e:
        out.append(f"JSON 解析失败：{e}")
        return
    out.append(f"顶层类型：{type(data).__name__}")
    if isinstance(data, dict):
        out.append(f"顶层键：{list(data.keys())[:20]}")
    lists = walk_json(data) or []
    if lists:
        out.append("候选列表路径（挑元素像作品的那条，填进 selectors.list）：")
        for p, n, sample in lists[:6]:
            keys = list(sample.keys())[:10] if isinstance(sample, dict) else "（字符串数组）"
            out.append(f"    {p}   共 {n} 项   首项键：{keys}")
    out.append("→ jsonpath 写法示例：\"list\": \"$.data.list\"，\"title\": \"$.name\"")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("url", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--save")
    ap.add_argument("--ua", default=DEFAULT_UA)
    ap.add_argument("--cookie", default="")
    ap.add_argument("--timeout", type=int, default=20)
    a = ap.parse_args()

    if not a.url and not a.file:
        print(__doc__)
        return 0

    out: list[str] = []
    kind = "html"
    if a.file:
        with open(a.file, "rb") as f:
            raw = f.read()
        out.append(f"本地文件：{a.file}（{len(raw)/1024:.1f} KB）")
        text = raw.decode("utf-8", "replace")
        if text.lstrip().startswith(("{", "[")):
            kind = "json"
        low = text[:200000].lower()
        hit = [m for m in CHALLENGE_MARKS if m in low]
        if hit:
            out.append(f"⚠ 反爬信号：{hit}（本地文件里命中了验证页特征）")
            out.append("  → 该端点被验证墙拦住：overrides.type=webview-html，用户手动过一次验证，同会话复用。")
    else:
        status, headers, raw, final, err = fetch(a.url, a.ua, a.cookie, a.timeout)
        if err is not None:
            print("抓取失败：{0}".format(err))
            print("\n若本机浏览器能打开该站，说明是网络环境（DNS / 代理 / 证书）问题：")
            print("1) 先用浏览器打开目标页，另存为 HTML，再用 --file 分析；")
            print("2) 或在本地仓库配置好网络后，用 App 的「抓取本页渲染内容」验证。")
            return 2
        cs = sniff_charset(headers, raw)
        text = raw.decode(cs, "replace")
        out.append(f"URL：{a.url}")
        out.append(f"最终地址：{final}" + ("（发生了跳转）" if final != a.url else ""))
        out.append(f"状态码：{status}    类型：{headers.get('Content-Type')}    大小：{len(raw)/1024:.1f} KB")
        if a.save:
            with open(a.save, "wb") as f:
                f.write(raw)
            out.append(f"已保存：{a.save}")

        low = text[:200000].lower()
        dead = bool(re.search(
            r"welcome to nginx|apache2? .{0,20}default page|it works!|iis windows server",
            text[:6000], re.I)) and len(raw) < 6000
        if dead:
            out.append("⚠ 站点疑似弃用：返回的是服务器默认页"
                       f"（{len(raw)} 字节），域名上没有站点。")
            out.append("  → 源再怎么改都抓不到内容：先确认站方是否换域名；"
                       "确认无解就给源标 deprecated + migrationMessage。")
        hit = [m for m in CHALLENGE_MARKS if m in low]
        if hit or status in (403, 503, 521, 520):
            out.append(f"⚠ 反爬信号：{hit or 'HTTP ' + str(status)}")
            out.append("  → 走 WebView 路线：该端点 overrides.type=webview-html（用户手动过一次验证，"
                       "同会话复用），播放仍用 webview + script。不要用 useWebview=true 代替路由级声明。")
            out.append("  → 若只有搜索被拦、其它页面正常：只给 search 配 webview-html 即可。")
        if status and status >= 400 and not hit:
            out.append("⚠ 服务端返回错误页：先确认站点是否需要登录 / 是否已改域名。")

        ctype = (headers.get("Content-Type") or "").lower()
        if "json" in ctype or text.lstrip().startswith(("{", "[")):
            kind = "json"

    out.append("")
    if kind == "json":
        analyze_json(text, out)
    else:
        analyze_html(text, out)

    print("\n".join(out))
    print("\n—— 结论建议 ——")
    if any("站点疑似弃用" in line for line in out):
        print('先解决「站还在不在」：换域名 / 标记 deprecated。解析写法此刻无意义。')
    elif kind == "json":
        print("接口型站点：parser.type=hybrid，端点 overrides.type=jsonpath（或省略走 builtin），"
              "responseType=json，selectors 用 $. 路径。")
    elif any("反爬信号" in line for line in out):
        print("强反爬站点：被拦的端点各自配 overrides.type=webview-html（用户手动过一次验证，"
              "同会话复用）；播放用 webview + script。")
        print("只拦一个端点（常见于 /search/）就只给那个端点配，别整站开 useWebview；"
              "滑块/图形验证码不可自动通过，也不该尝试绕过。")
    elif any("密度很低" in line or "前端框架" in line for line in out):
        print("前端渲染站点：先按上面的高频链接形态写选择器，用 webview-html 让 App 渲染后再抽取；"
              "若页面自带 __NEXT_DATA__ 等内联 JSON，也可用 script 直接读它。")
    else:
        print("服务端渲染站点：parser.type=hybrid，overrides 用 builtin，selectors 写 CSS/`css@attr` 即可。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
