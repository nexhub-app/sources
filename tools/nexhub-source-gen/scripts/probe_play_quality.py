# -*- coding: utf-8 -*-
"""播放页画质探针：判定「视频不清晰」是取址漏了高码率，还是素材本身上限。

用法（duanju-patterns.md §16 三分法的配套工具）：

    python scripts/probe_play_quality.py <播放页URL> [更多播放页URL...] [--sibling-labels 720,1080,4k]

对每个播放页：
1. 带完整浏览器头抓页，列出全部 m3u8/mp4 明文直链（数量多=存在多线路/多档，少=站方单地址）；
2. 逐条拉 playlist，报真相：media playlist 看分片子目录码率名（如 `904kb/`），
   master playlist 看 `RESOLUTION=`/`BANDWIDTH=` —— 路径里的 `/1080/` 标签只是目录名，不作数；
3. `--sibling-labels` 可选：把直链倒数第二段路径换成各档位标签探测兄弟档（验证
   站点是否埋了更高码率目录），只报存在且分片码率更高的兄弟档。

安全约束：仅 https；允许的主机 = 命令行 URL 的主机本身；不跟随重定向。
"""
import argparse
import gzip
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
VIDEO_RE = re.compile(r'https?://[^"\'\s,]+?\.(?:m3u8|mp4)[^"\'\s,]*')
CTX = ssl.create_default_context()


def fetch(url, referer, timeout=25):
    """仅 https、仅命令行出现过的主机，不跟随重定向；返回 (status, text)。"""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        return -1, "blocked-host"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip",
        "Referer": referer,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return r.status, data.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return -1, "fetch-failed"


def playlist_truth(url, referer):
    """拉一次 playlist，返回 {kind, kb_tiers, resolutions, bandwidths}。"""
    st, body = fetch(url, referer)
    if st != 200 or not body.startswith("#EXTM3U"):
        return {"error": f"HTTP {st}"}
    truth = {"kind": "master" if "#EXT-X-STREAM-INF" in body else "media"}
    truth["kb_tiers"] = sorted({int(k) for k in re.findall(r"(\d+)kb/", body)})
    truth["resolutions"] = sorted(set(re.findall(r"RESOLUTION=(\d+x\d+)", body)))
    truth["bandwidths"] = sorted({int(b) for b in re.findall(
        r"BANDWIDTH=(\d+)", body)})
    return truth


def sibling_labels(url, labels, referer):
    """把倒数第二段路径换成各档位标签探测兄弟档，返回更优档列表。"""
    parts = urllib.parse.urlsplit(url)
    segs = parts.path.split("/")
    if len(segs) < 3:
        return []
    base_truth = playlist_truth(url, referer)
    base_kb = max(base_truth.get("kb_tiers") or [0]) if "kb_tiers" in base_truth else 0
    found = []
    for lb in labels:
        trial = segs[:-2] + [lb, segs[-1]]
        t_url = parts._replace(path="/".join(trial)).geturl()
        st, body = fetch(t_url, referer)
        if st != 200 or not body.startswith("#EXTM3U"):
            continue
        kb = [int(k) for k in re.findall(r"(\d+)kb/", body)]
        res = sorted(set(re.findall(r"RESOLUTION=(\d+x\d+)", body)))
        if max(kb or [0]) > base_kb or res:
            found.append({"label": lb, "kb_tiers": sorted(set(kb)),
                          "resolutions": res, "url": t_url[:120]})
        time.sleep(1)
    return found


def probe(page_url, labels):
    referer = urllib.parse.urlsplit(page_url)
    origin = f"{referer.scheme}://{referer.netloc}/"
    st, html = fetch(page_url, origin)
    out = {"page": page_url, "status": st}
    if st != 200:
        out["error"] = f"HTTP {st}（502 多为限流，隔 3~5s 重试；对照普通页判断）"
        return out
    urls = []
    for u in VIDEO_RE.findall(html):
        if "/player/" in u:
            continue  # 播放器壳路径不是直链
        if u not in urls:
            urls.append(u)
    # 第二跳主机（直链所在 CDN）来自已抓页面内容，动态入白名单
    for u in urls:
        h = urllib.parse.urlsplit(u).hostname
        if h:
            ALLOWED_HOSTS.add(h)
    out["video_urls"] = urls
    if not urls:
        out["note"] = "无明文直链：地址可能在 player_aaaa/加密配置里，另行解析后再探"
        return out
    out["playlists"] = []
    for u in urls[:3]:
        item = {"url": u[:120], "truth": playlist_truth(u, origin)}
        if labels:
            sib = sibling_labels(u, labels, origin)
            if sib:
                item["higher_siblings"] = sib
        out["playlists"].append(item)
        time.sleep(2)
    return out


def main():
    global ALLOWED_HOSTS
    ap = argparse.ArgumentParser(description="播放页画质探针（§16 三分法配套）")
    ap.add_argument("urls", nargs="+", help="播放页 URL（其主机即允许抓取的白名单）")
    ap.add_argument("--sibling-labels", default="",
                    help="逗号分隔的兄弟档标签，如 720,1080,4k（可选）")
    args = ap.parse_args()
    ALLOWED_HOSTS = {urllib.parse.urlsplit(u).hostname for u in args.urls
                     if urllib.parse.urlsplit(u).hostname}
    labels = [x.strip() for x in args.sibling_labels.split(",") if x.strip()]
    results = []
    for i, u in enumerate(args.urls):
        results.append(probe(u, labels))
        if i < len(args.urls) - 1:
            time.sleep(4)  # 探测节奏：同站连发会吃 502 限流页
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
