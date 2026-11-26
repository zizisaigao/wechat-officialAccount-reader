#!/usr/bin/env python3
"""Personal, provenance-preserving WeChat article metadata collector (Python 3.10+)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse as up
import urllib.request as ur
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 4_000_000
UA = "wechat-officialAccount-reader/0.1 (+https://github.com/zizisaigao/wechat-officialAccount-reader)"
HOSTS = {"reportify.cn", "www.reportify.cn", "www.jintiankansha.com", "www.jintiankansha.me", "mp.weixin.qq.com"}
PUBLIC_PARAMS = ("__biz", "mid", "idx", "sn", "chksm")
FIELDS = ("account", "title", "url", "published_at", "biz", "source_url", "verification", "fetched_at")


class ReaderError(Exception):
    """Recoverable source, parsing, or identity error; never silently treated as success."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    return " ".join(html.unescape(str(value or "")).split())


def canonical_wechat(value: str) -> str:
    value = html.unescape(value.strip()).replace("\\u0026", "&").replace("\\/", "/")
    p = up.urlsplit(value)
    if p.scheme not in {"http", "https"} or p.hostname != "mp.weixin.qq.com" or p.username or p.port:
        raise ReaderError("不是合法的微信文章链接")
    if re.fullmatch(r"/s/[A-Za-z0-9_-]+", p.path):
        return "https://mp.weixin.qq.com" + p.path
    q = up.parse_qs(p.query)
    if p.path != "/s" or not all(q.get(k) for k in ("__biz", "mid", "idx", "sn")):
        raise ReaderError("微信链接缺少文章标识；不能用公众号主页或二维码代替文章")
    if not q["mid"][0].isdigit() or not q["idx"][0].isdigit():
        raise ReaderError("无效的文章 mid/idx")
    return "https://mp.weixin.qq.com/s?" + up.urlencode([(k, q[k][0]) for k in PUBLIC_PARAMS if q.get(k)])


def article_key(row: dict) -> str:
    p = up.urlsplit(row["url"])
    q = up.parse_qs(p.query)
    if all(q.get(k) for k in ("__biz", "mid", "idx")):
        return "|".join(q[k][0] for k in ("__biz", "mid", "idx"))
    return row["url"]


def allowed_url(url: str) -> str:
    p = up.urlsplit(url)
    if p.scheme not in {"http", "https"} or p.hostname not in HOSTS or p.username or p.port:
        raise ReaderError("仅支持已实现来源的公开 HTTPS 页面")
    if any(k.lower() in {"key", "uin", "pass_ticket", "token", "cookie", "authorization"} for k in up.parse_qs(p.query)):
        raise ReaderError("拒绝包含登录凭证的 URL；请使用公开文章地址")
    return up.urlunsplit(("https", p.hostname, p.path, p.query, ""))


class SafeRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = allowed_url(newurl)
        if re.search(r"/(?:signin|login|account/signin|captcha)(?:[/?]|$)", newurl):
            raise ReaderError("来源要求登录或验证，停止访问")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, delay: float = 1.5):
        self.delay = max(1.0, delay)
        self.last = 0.0
        self.opener = ur.build_opener(SafeRedirect())
        self.blocked: set[str] = set()

    def get(self, url: str) -> str:
        url = allowed_url(url)
        host = up.urlsplit(url).hostname
        if host in self.blocked:
            raise ReaderError("该来源本次已被限流或拒绝，未继续请求")
        time.sleep(max(0, self.last + self.delay - time.monotonic()))
        self.last = time.monotonic()
        try:
            req = ur.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
            with self.opener.open(req, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ReaderError("页面超过大小上限")
                text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        except ur.HTTPError as e:
            if e.code in {401, 403, 429}:
                self.blocked.add(host)
            raise ReaderError(f"HTTP {e.code}；不重试认证失败或限流") from None
        except (ur.URLError, TimeoutError, OSError) as e:
            raise ReaderError(f"网络访问失败：{type(e).__name__}") from None
        if not text.strip():
            raise ReaderError("HTTP 成功但响应为空")
        title = BeautifulSoup(text, "html.parser").title
        if title and re.search(r"登录|验证码|Access denied|Just a moment|安全验证", title.get_text(), re.I):
            self.blocked.add(host)
            raise ReaderError("来源返回登录/验证页面，不是文章数据")
        return text


def walk_objects(value: Any, depth: int = 0) -> Iterator[dict]:
    if depth > 30:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child, depth + 1)
    elif isinstance(value, str) and value[:1] in {"{", "["}:
        try:
            decoded = json.loads(value)
        except ValueError:
            return
        yield from walk_objects(decoded, depth + 1)


def embedded_objects(text: str) -> Iterator[dict]:
    """Decode JSON, including split Next.js flight chunks; never execute page scripts."""
    try:
        yield from walk_objects(json.loads(text))
        return
    except ValueError:
        pass
    soup = BeautifulSoup(text, "html.parser")
    chunks: list[str] = []
    decoder = json.JSONDecoder()
    for script in soup.find_all("script"):
        body = script.string or script.get_text()
        if script.get("type") in {"application/json", "application/ld+json"}:
            try:
                yield from walk_objects(json.loads(body))
            except ValueError:
                pass
        for m in re.finditer(r"self\.__next_f\.push\(", body):
            try:
                data, _ = decoder.raw_decode(body[m.end():].lstrip())
                if isinstance(data, list) and len(data) > 1 and isinstance(data[1], str):
                    chunks.append(data[1])
            except ValueError:
                pass
    flight = "".join(chunks)
    # Flight records can carry React tags. Named props remain ordinary JSON.
    patterns = [r'(?:^|\n)[0-9a-f]+:[A-Z]*([\[{])', r'"(?:main|defaultData|reportData)"\s*:\s*(\{)']
    seen: set[int] = set()
    for pattern in patterns:
        for m in re.finditer(pattern, flight):
            start = m.start(1)
            if start in seen:
                continue
            seen.add(start)
            try:
                value, _ = decoder.raw_decode(flight[start:])
                yield from walk_objects(value)
            except ValueError:
                pass


def published(value: Any) -> str:
    if value in {None, ""}:
        return ""
    if isinstance(value, (int, float)):
        if value > 100_000_000_000:
            value /= 1000
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
        except (ValueError, OverflowError, OSError):
            return ""
    return clean_text(value)


def row_from_metadata(obj: dict, account: str, biz: str, source_url: str) -> dict | None:
    original = obj.get("original_url") or obj.get("content_url")
    title = clean_text(obj.get("title") or obj.get("report_title"))
    if not isinstance(original, str) or not title:
        return None
    try:
        url = canonical_wechat(original)
    except (ReaderError, ValueError):
        return None
    found_biz = up.parse_qs(up.urlsplit(url).query).get("__biz", [""])[0]
    names = {clean_text(obj.get(k)) for k in ("wechat_mp_name", "channel_name", "original_site", "account", "nickname")} - {""}
    if names and account not in names:
        return None
    if biz and found_biz and found_biz != biz:
        return None
    if not ((biz and found_biz == biz) or account in names):
        return None
    return {"account": account, "title": title, "url": url,
            "published_at": published(obj.get("publish_at") or obj.get("datetime") or obj.get("published_at")),
            "biz": found_biz, "source_url": source_url,
            "verification": "biz_match" if biz and found_biz == biz else "source_name_match",
            "fetched_at": now()}


def parse_reportify(text: str, account: str, biz: str, source_url: str) -> list[dict]:
    rows = {}
    for obj in embedded_objects(text):
        row = row_from_metadata(obj, account, biz, source_url)
        if row:
            rows[article_key(row)] = row
    return list(rows.values())


def parse_index(text: str, account: str, source_url: str) -> tuple[list[dict], str]:
    soup = BeautifulSoup(text, "html.parser")
    if not soup.title or account not in soup.title.get_text():
        raise ReaderError("索引页账号名称不匹配")
    rows = []
    for node in soup.select(".item_title"):
        title = clean_text(node.get_text(" ", strip=True))
        if title:
            rows.append({"account": account, "title": title, "source_url": source_url, "status": "title_only", "observed_at": now()})
    nxt = soup.select_one("a#p_next[href]")
    next_url = up.urljoin(source_url, nxt["href"]) if nxt else ""
    if next_url and up.urlsplit(next_url).netloc != up.urlsplit(source_url).netloc:
        raise ReaderError("拒绝跨站分页")
    if not rows:
        raise ReaderError("索引没有标题；可能是页面结构变化或访问受限")
    return rows, next_url


def collect_index(client: Client, account: str, url: str, pages: int) -> list[dict]:
    result, seen_pages = [], set()
    for _ in range(pages):
        if not url or url in seen_pages:
            break
        seen_pages.add(url)
        rows, nxt = parse_index(client.get(url), account, url)
        signature = tuple(r["title"] for r in rows)
        if signature in seen_pages:
            break
        seen_pages.add(signature)
        result.extend(rows)
        url = nxt
    return result


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def export(out: Path, rows: list[dict], report: dict, titles: list[dict]) -> None:
    atomic_text(out / "articles.json", json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {k: ("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v) for k, v in row.items()}
        writer.writerow(safe)
    atomic_text(out / "articles.csv", "\ufeff" + stream.getvalue())
    atomic_text(out / "run.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_text(out / "titles.json", json.dumps(titles, ensure_ascii=False, indent=2) + "\n")
    esc = html.escape
    tr = "\n".join(f'<tr><td>{esc(r["published_at"])}</td><td><a href="{esc(r["url"], quote=True)}" rel="noreferrer">{esc(r["title"])}</a></td><td>{esc(r["verification"])}</td></tr>' for r in rows)
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>公众号文章索引</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto;padding:0 20px}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}table{border-collapse:collapse;width:100%}</style>'
            '<h1>' + esc(report["account"]) + '</h1><p>公开来源发现的部分文章；不保证全量历史或微信原文当前可打开。时间为 UTC。</p>'
            f'<p>本次核验 {report["fetched_articles"]} 篇；本地累计 {len(rows)} 篇。</p>'
            '<table><thead><tr><th>发布时间</th><th>文章（微信链接）</th><th>账号核验</th></tr></thead><tbody>' + tr + '</tbody></table></html>')
    atomic_text(out / "index.html", page)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按公众号名称收集有来源依据的文章标题和微信链接；AI Skill 负责持续发现新候选 URL。")
    parser.add_argument("account", help="公众号名称")
    parser.add_argument("--registry", type=Path, default=ROOT / "accounts.json")
    parser.add_argument("--biz", default="", help="可选的已核实 __biz")
    parser.add_argument("--seeds", type=Path, help="候选公开文章 URL 文件，每行一条；与内置样例合并")
    parser.add_argument("--url", action="append", default=[], help="额外 Reportify 公开文章 URL，可重复")
    parser.add_argument("--pages", type=int, default=1, help="公开标题索引页数，0 为不请求，最多5页")
    parser.add_argument("--limit", type=int, default=20, help="最多请求候选文章数（1—100）")
    parser.add_argument("--out", type=Path, default=ROOT / "output")
    parser.add_argument("--no-bundled", action="store_true", help="不读取内置样例文章种子")
    parser.add_argument("--strict", action="store_true", help="任何来源失败则退出码3；已有结果仍保存")
    args = parser.parse_args(argv)
    if not 0 <= args.pages <= 5 or not 1 <= args.limit <= 100:
        parser.error("pages 必须为0—5，limit 必须为1—100")
    registry = json.loads(args.registry.read_text(encoding="utf-8")) if args.registry.exists() else {}
    cfg = registry.get(args.account, {})
    biz = args.biz or cfg.get("biz", "")
    urls = [] if args.no_bundled else list(cfg.get("seed_urls", []))
    if args.seeds:
        urls += [s.strip() for s in args.seeds.read_text(encoding="utf-8").splitlines() if s.strip() and not s.lstrip().startswith("#")]
    urls += args.url
    urls = list(dict.fromkeys(urls))[:args.limit]
    report = {"account": args.account, "started_at": now(), "coverage": "partial_public_discovery", "complete_history": False,
              "url_liveness_checked": False, "seed_count": len(urls), "errors": [], "notes": [], "fetched_articles": 0}
    if not urls:
        report["notes"].append("没有文章候选 URL。请运行 skills/wechat-reader/SKILL.md 中的名称检索流程，再通过 --seeds 导入。")
    client, rows, titles = Client(), [], []
    if args.pages and cfg.get("index_url"):
        try:
            titles = collect_index(client, args.account, cfg["index_url"], args.pages)
        except ReaderError as e:
            report["errors"].append({"source": "title_index", "error": str(e)})
    for url in urls:
        try:
            p = up.urlsplit(allowed_url(url))
            if p.hostname not in {"reportify.cn", "www.reportify.cn"} or not re.fullmatch(r"/social-media/\d+", p.path):
                raise ReaderError("候选应为 Reportify 公开文章页 /social-media/数字ID")
            found = parse_reportify(client.get(url), args.account, biz, allowed_url(url))
            if not found:
                raise ReaderError("页面未返回与目标账号匹配的文章元数据")
            rows.extend(found)
        except (ReaderError, ValueError) as e:
            report["errors"].append({"source": "candidate", "error": str(e)})
    fresh = {article_key(r): r for r in rows}
    report["fetched_articles"] = len(fresh)
    previous_file = args.out / "articles.json"
    archive = {}
    if previous_file.exists():
        previous = json.loads(previous_file.read_text(encoding="utf-8"))
        for row in previous:
            if row.get("account") != args.account:
                raise ReaderError("输出目录已有其他公众号的数据，请指定不同 --out")
            row["url"] = canonical_wechat(row["url"])
            archive[article_key(row)] = row
    report["new_articles"] = len(fresh.keys() - archive.keys())
    archive.update(fresh)
    rows = sorted(archive.values(), key=lambda r: (r.get("published_at", ""), r["url"]), reverse=True)
    matched_titles = {clean_text(r["title"]) for r in rows}
    for t in titles:
        if t["title"] in matched_titles:
            t["status"] = "title_matches_archive"  # Not a unique identity proof.
    report.update({"finished_at": now(), "archive_articles": len(rows), "observed_titles": len(titles),
                   "unresolved_titles": sum(t["status"] == "title_only" for t in titles)})
    export(args.out, rows, report, titles)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not fresh:
        return 2
    return 3 if args.strict and report["errors"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReaderError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
