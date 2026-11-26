#!/usr/bin/env python3
"""Read the first public WeChat album page; never equate an album with an account's history."""
from __future__ import annotations
import argparse
import csv
import html
import io
import json
import re
import urllib.error
import urllib.parse as up
import urllib.request as ur
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

MAX_BYTES = 4_000_000
PUBLIC = ('__biz', 'mid', 'idx', 'sn', 'chksm')

class AlbumError(ValueError):
    pass

def album_url(seed: str) -> str:
    p = up.urlsplit(html.unescape(seed.strip()).replace('\\&', '&'))
    if p.scheme not in {'http', 'https'} or p.hostname != 'mp.weixin.qq.com' or p.username or p.port:
        raise AlbumError('仅接受微信公开文章或合集链接')
    q = up.parse_qs(p.query)
    if any(k.lower() in {'key', 'uin', 'pass_ticket', 'token', 'appmsg_token', 'cookie'} for k in q):
        raise AlbumError('请勿提供含登录凭证的链接')
    biz = q.get('__biz', [''])[0]
    aid = q.get('album_id' if p.path == '/mp/appmsgalbum' else 'cur_album_id', [''])[0]
    if p.path not in {'/s', '/mp/appmsgalbum'} or not re.fullmatch(r'[A-Za-z0-9+/=]+', biz) or not aid.isdigit():
        raise AlbumError('链接必须带 __biz 和 album_id / cur_album_id；不能凭空发现合集')
    return 'https://mp.weixin.qq.com/mp/appmsgalbum?' + up.urlencode({'__biz': biz, 'action': 'getalbum', 'album_id': aid})

def canonical_article(value: str, biz: str) -> str:
    p = up.urlsplit(html.unescape(value))
    q = up.parse_qs(p.query)
    if p.scheme not in {'http', 'https'} or p.hostname != 'mp.weixin.qq.com' or p.username or p.port or p.path != '/s':
        raise AlbumError('合集返回了非微信长文章链接')
    if q.get('__biz') != [biz] or not all(len(q.get(k, [])) == 1 and q[k][0] for k in PUBLIC[:4]):
        raise AlbumError('文章账号标识不一致或文章参数缺失')
    if not q['mid'][0].isdigit() or not q['idx'][0].isdigit():
        raise AlbumError('无效的文章 mid/idx')
    return 'https://mp.weixin.qq.com/s?' + up.urlencode([(k, q[k][0]) for k in PUBLIC if q.get(k)])

class SafeRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = up.urlsplit(newurl)
        if p.hostname != 'mp.weixin.qq.com' or re.search(r'captcha|login|signin', p.path, re.I):
            raise AlbumError('来源跳转至验证/登录或外部站点，停止，不重试')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch_album(url: str) -> str:
    req = ur.Request(album_url(url), headers={'User-Agent': 'wechat-officialAccount-reader/0.1'})
    try:
        with ur.build_opener(SafeRedirect()).open(req, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AlbumError(f'请求失败：{type(exc).__name__}；没有自动重试') from exc
    if len(raw) > MAX_BYTES:
        raise AlbumError('页面超过大小限制')
    return raw.decode('utf-8', 'replace')

def parse_album(text: str, account: str, source: str, limit: int = 10) -> tuple[list[dict], dict]:
    if not 1 <= limit <= 100:
        raise AlbumError('limit 必须为1—100，仅限制输出，不表示已实现分页')
    source = album_url(source)
    q = up.parse_qs(up.urlsplit(source).query)
    biz = q['__biz'][0]
    soup = BeautifulSoup(text, 'html.parser')
    author = soup.select_one('.album__author-name')
    label = soup.select_one('.album__label-title')
    if not author or author.get_text(' ', strip=True) != account:
        raise AlbumError('合集页账号名称未通过核验；可能返回了验证码页')
    if not label:
        raise AlbumError('未找到合集名称，页面结构可能变化')
    name = label.get_text(' ', strip=True)
    count = re.search(r'\barticle_count\s*:\s*[\x22\x27]?(\d+)', text)
    total = int(count[1]) if count else None
    rows = {}
    for node in soup.select('li[data-link][data-title]'):
        title = html.unescape(node['data-title']).strip()
        url = canonical_article(node['data-link'], biz)
        aq = up.parse_qs(up.urlsplit(url).query)
        key = (biz, aq['mid'][0], aq['idx'][0])
        stamp = node.select_one('.js_article_create_time')
        published = ''
        if stamp and stamp.get_text(strip=True).isdigit():
            try:
                published = datetime.fromtimestamp(int(stamp.get_text(strip=True)), timezone.utc).isoformat(timespec='seconds')
            except (ValueError, OverflowError, OSError):
                pass
        if not title:
            raise AlbumError('文章缺少标题')
        rows[key] = {'account': account, 'title': title, 'url': url, 'published_at': published,
                     'biz': biz, 'album_id': q['album_id'][0], 'album_name': name, 'source_url': source,
                     'verification': 'official_album_name_and_biz_match'}
    if not rows:
        raise AlbumError('未取得任何文章，不能将空页标记为成功')
    ordered = sorted(rows.values(), key=lambda row: row['published_at'], reverse=True)
    report = {'account': account, 'provider': 'wechat_official_album', 'album_name': name,
              'biz': biz, 'album_id': q['album_id'][0], 'source_url': source,
              'source_total_count': total, 'page_loaded_articles': len(ordered),
              'requested_limit': limit, 'returned_articles': min(limit, len(ordered)),
              'complete_history': False, 'url_liveness_checked': False,
              'album_complete': total is not None and total == len(ordered) and total <= limit,
              'coverage': 'album_first_page_only', 'errors': []}
    return ordered[:limit], report

def export(out: Path, rows: list[dict], report: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [('articles.json', rows), ('run.json', report)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: "'"+str(v) if str(v).lstrip().startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    (out/'articles.csv').write_text('\ufeff'+stream.getvalue(), encoding='utf-8')
    esc = html.escape
    table = ''.join(f'<tr><td>{i}</td><td>{esc(r["published_at"])}</td><td><a target="_blank" rel="noopener noreferrer" href="{esc(r["url"],quote=True)}">{esc(r["title"])}</a></td></tr>' for i,r in enumerate(rows,1))
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>公众号合集文章</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:40px auto;padding:0 20px}table{width:100%;border-collapse:collapse}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}</style>'
            f'<h1>{esc(report["account"])}</h1><h2>{esc(report["album_name"])}</h2>'
            f'<p>合集页面显示共 {report["source_total_count"]} 篇；本次输出 {len(rows)} 篇。仅代表该合集，不是整个公众号最新文章或完整历史。日期为 UTC；未逐篇检查正文可访问性。</p>'
            '<table><thead><tr><th>#</th><th>发布时间（UTC）</th><th>文章标题</th></tr></thead><tbody>'+table+'</tbody></table></html>')
    (out/'index.html').write_text(page, encoding='utf-8')

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('account')
    parser.add_argument('--seed', help='带cur_album_id的文章链接或合集链接')
    parser.add_argument('--registry', type=Path, default=Path(__file__).with_name('accounts.json'))
    parser.add_argument('--html', type=Path, help='离线解析保存的合集HTML；不访问网络')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--out', type=Path, default=Path('output-album'))
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 100:
        parser.error('limit 必须为1—100')
    try:
        cfg = json.loads(args.registry.read_text(encoding='utf-8')).get(args.account, {}) if args.registry.exists() else {}
        seeds = cfg.get('album_urls', [])
        seed = args.seed or (seeds[0] if seeds else '')
        source = album_url(seed)
        if args.html and args.html.stat().st_size > MAX_BYTES:
            raise AlbumError('离线文件超过大小限制')
        text = args.html.read_text(encoding='utf-8') if args.html else fetch_album(source)
        rows, report = parse_album(text, args.account, source, args.limit)
        report.update({'offline_replay': bool(args.html), 'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
        export(args.out, rows, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (AlbumError, ValueError, OSError) as exc:
        print(f'ERROR: {exc}')
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
