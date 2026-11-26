#!/usr/bin/env python3
"""Extract article outlinks, not account history. Never click articles or solve CAPTCHAs."""
from __future__ import annotations
import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = 'https://mp.weixin.qq.com/s/VYm28mkGTaoyX2wqByMmrQ'


def article_url(value: str, base: str) -> str | None:
    value = html.unescape(html.unescape(value.strip())).replace('\\/', '/')
    value = re.sub(r'\\u0026|\\x26', '&', value, flags=re.I)
    url = urljoin(base, value)
    p = urlsplit(url)
    if p.scheme not in {'https', 'http'} or p.hostname != 'mp.weixin.qq.com':
        return None
    if p.username or p.password or p.port not in {None, 80, 443}:
        return None
    q = dict(parse_qsl(p.query))
    if not (re.fullmatch(r'/s/[A-Za-z0-9_-]+', p.path) or
            (p.path in {'/s', '/s/'} and all(q.get(k) for k in ('__biz', 'mid', 'idx', 'sn')))):
        return None
    return url


def identity(url: str) -> str:
    p = urlsplit(url)
    q = dict(parse_qsl(p.query))
    if all(q.get(k) for k in ('__biz', 'mid', 'idx', 'sn')):
        return urlunsplit(('https', 'mp.weixin.qq.com', '/s',
                          urlencode([(k, q[k]) for k in ('__biz', 'mid', 'idx', 'sn')]), ''))
    return urlunsplit(('https', 'mp.weixin.qq.com', p.path, '', ''))


def extract(markup: str, source: str) -> dict:
    soup = BeautifulSoup(markup, 'html.parser')
    body = soup.select_one('#js_content')
    heading = soup.select_one('#activity-name')
    result = {
        'source_url': source,
        'page_title': heading.get_text(' ', strip=True) if heading else '',
        'content_present': body is not None,
        'status': 'ok' if body is not None else 'no_article_body',
        'url_liveness_checked': False,
        'links': [],
    }
    if body is None:
        visible = soup.get_text(' ', strip=True)
        result['page_excerpt'] = visible[:500]
        if any(s in visible for s in ('环境异常', '访问过于频繁', '请完成验证', '去验证', '验证码')):
            result['status'] = 'verification_required'
        return result
    records = {}
    for node in body.select('a, [data-href], [data-url], [data-link]'):
        title = (node.get('textvalue') or node.get('data-title') or node.get('title')
                 or node.get_text(' ', strip=True))
        title = re.sub(r'\s+', ' ', str(title)).strip()
        for attr in ('href', 'data-href', 'data-url', 'data-link'):
            raw = node.get(attr)
            if not isinstance(raw, str):
                continue
            try:
                url = article_url(raw, source)
            except ValueError:
                continue
            if not url or identity(url) == identity(source):
                continue
            key = identity(url)
            if key not in records:
                records[key] = {'title': title, 'url': url, 'canonical_url': key,
                                'attribute': attr, 'raw_value': raw,
                                'provenance': 'entry_page_dom'}
            elif title and not records[key]['title']:
                records[key]['title'] = title
    result['links'] = list(records.values())
    result['anchor_count'] = len(body.select('a'))
    result['article_link_count'] = len(records)
    if not records:
        result['status'] = 'no_links_extracted'
        result['candidate_elements'] = [str(n)[:1000] for n in body.select('a, [data-href], [data-url], [data-link]')[:20]]
    return result


def fetch(url: str) -> dict:
    if not article_url(url, url):
        raise ValueError('Only public mp.weixin.qq.com article URLs are accepted')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
               'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'}
    # Follow redirects only on the same public article host. No cookies or credentials supplied.
    with requests.Session() as session:
        current = url
        for _ in range(5):
            response = session.get(current, headers=headers, timeout=(10, 35), allow_redirects=False)
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            current = urljoin(current, response.headers.get('Location', ''))
            p = urlsplit(current)
            if p.scheme != 'https' or p.hostname != 'mp.weixin.qq.com' or p.username or p.password:
                raise ValueError('Refusing an unexpected redirect')
        else:
            raise ValueError('Too many redirects')
    response.raise_for_status()
    response.encoding = 'utf-8'
    result = extract(response.text, current)
    result.update({'requested_url': url, 'http_status': response.status_code,
                   'html_bytes': len(response.content)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?', default=DEFAULT_URL)
    parser.add_argument('--html', type=Path, help='Parse a locally saved page without network')
    parser.add_argument('--out', type=Path, default=Path('output/outlinks.json'))
    args = parser.parse_args()
    try:
        result = extract(args.html.read_text(encoding='utf-8'), args.url) if args.html else fetch(args.url)
    except (requests.RequestException, ValueError, OSError) as exc:
        result = {'source_url': args.url, 'status': 'fetch_failed', 'error': str(exc), 'links': []}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('RESULT_JSON ' + json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'ok' and result['links'] else 2


if __name__ == '__main__':
    sys.exit(main())
