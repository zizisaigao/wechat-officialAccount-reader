#!/usr/bin/env python3
"""Name-first public channel collection. No WeChat login or API credentials."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse as up
from pathlib import Path
from typing import Any

import reader as core

API = 'https://api.reportify.cn'
# This public host was verified from Reportify's own browser client and live responses.
core.HOSTS.add('api.reportify.cn')
PAGE_SIZE = 20


def api_json(client: core.Client, path: str, params: dict[str, Any]) -> dict:
    url = API + path + '?' + up.urlencode(params)
    try:
        data = json.loads(client.get(url))
    except ValueError as exc:
        raise core.ReaderError('列表来源没有返回有效 JSON') from exc
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise core.ReaderError('列表响应结构变化或需要授权；停止，不伪造登录身份')
    return data


def resolve_channel(client: core.Client, account: str, config: dict, explicit: str = '') -> str:
    channel = explicit or config.get('reportify_channel', '')
    if channel:
        if not re.fullmatch(r'S\d+', channel):
            raise core.ReaderError('无效的 Reportify channel ID')
        return channel
    data = api_json(client, '/channels', {'query': account, 'page_num': 1, 'page_size': 20})
    matches = set()
    for obj in data['items']:
        if not isinstance(obj, dict):
            continue
        names = {core.clean_text(obj.get(k)) for k in ('channel_name', 'chinese_name', 'chinese_full_name', 'english_name')}
        identifier = str(obj.get('channel_id', ''))
        if account in names and re.fullmatch(r'S\d+', identifier):
            matches.add(identifier)
    if len(matches) != 1:
        raise core.ReaderError('未找到唯一同名专栏；请用 AI Skill 检索身份后传入 --channel，或用 reader.py --seeds 采集候选')
    return matches.pop()


def collect(client: core.Client, account: str, biz: str, channel: str, pages: int) -> tuple[list[dict], dict]:
    found: dict[str, dict] = {}
    signatures: set[tuple[str, ...]] = set()
    stats = {'source_total_count': None, 'source_pages_reported': None, 'source_pages_fetched': 0,
             'source_listing_exhausted': False, 'source_count_changed': False,
             'rejected_records': 0, 'errors': []}
    for page in range(1, pages + 1):
        try:
            data = api_json(client, '/reports', {'page_num': page, 'page_size': PAGE_SIZE,
                                               'channel_id': channel, 'report_types': 12})
            total = data.get('total_count')
            total_pages = data.get('total_page')
            if (type(total) is not int or total < 0 or type(total_pages) is not int
                    or total_pages < 0 or data.get('page_num') != page):
                raise core.ReaderError('分页信息无效或来源忽略页码')
            if stats['source_total_count'] is not None and stats['source_total_count'] != total:
                stats['source_count_changed'] = True
            stats['source_total_count'] = total
            stats['source_pages_reported'] = total_pages
            items = data['items']
            stats['source_pages_fetched'] += 1
            if not items:
                if total and page <= total_pages:
                    raise core.ReaderError('来源声称存在文章，但该页为空')
                stats['source_listing_exhausted'] = True
                break
            signature = tuple(str(o.get('report_id', '')) for o in items if isinstance(o, dict))
            if not signature or signature in signatures:
                raise core.ReaderError('来源返回重复或无效分页，停止以避免死循环')
            signatures.add(signature)
            for obj in items:
                if not isinstance(obj, dict) or obj.get('channel_id') not in {None, '', channel}:
                    stats['rejected_records'] += 1
                    continue
                identifier = str(obj.get('report_id', ''))
                source = ('https://reportify.cn/social-media/' + identifier if identifier.isdigit()
                          else 'https://reportify.cn/channels/' + channel + '/documents')
                row = core.row_from_metadata(obj, account, biz, source)
                if row:
                    found[core.article_key(row)] = row
                else:
                    stats['rejected_records'] += 1
            if page >= total_pages:
                stats['source_listing_exhausted'] = True
                break
        except (core.ReaderError, ValueError, TypeError) as exc:
            stats['errors'].append({'source': 'reportify_list', 'page': page, 'error': str(exc)})
            break  # Preserve previously collected pages; never retry authorization failures.
    stats['verified_source_listing_complete'] = bool(
        stats['source_listing_exhausted'] and not stats['errors'] and not stats['rejected_records']
        and not stats['source_count_changed'] and len(found) == stats['source_total_count'])
    return list(found.values()), stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='按公众号名称分页采集公开收录的文章标题与微信原文链接')
    parser.add_argument('account')
    parser.add_argument('--registry', type=Path, default=core.ROOT / 'accounts.json')
    parser.add_argument('--channel', default='', help='已核验的 Reportify 专栏ID；用于同名歧义或补充新账号')
    parser.add_argument('--biz', default='', help='已核验的微信 __biz，可选')
    parser.add_argument('--pages', type=int, default=1, help='最多请求页数，1—50；每页20条')
    parser.add_argument('--out', type=Path, default=core.ROOT / 'output')
    parser.add_argument('--strict', action='store_true', help='来源错误或身份拒绝时以退出码3返回；保留已有结果')
    args = parser.parse_args(argv)
    if not 1 <= args.pages <= 50:
        parser.error('pages 必须为1—50')
    registry = json.loads(args.registry.read_text(encoding='utf-8')) if args.registry.exists() else {}
    cfg = registry.get(args.account, {})
    archive = {}
    if (args.out / 'articles.json').exists():
        for row in json.loads((args.out / 'articles.json').read_text(encoding='utf-8')):
            if row.get('account') != args.account:
                raise core.ReaderError('输出目录存在其他公众号的数据，请使用不同 --out')
            row['url'] = core.canonical_wechat(row['url'])
            archive[core.article_key(row)] = row
    report = {'account': args.account, 'started_at': core.now(), 'provider': 'reportify_public_list',
              'coverage': 'third_party_index', 'complete_history': False, 'url_liveness_checked': False,
              'requested_pages': args.pages, 'notes': ['第三方收录范围不等于微信完整历史；时间统一为UTC。'],
              'observed_titles': 0, 'unresolved_titles': 0}
    client = core.Client()
    try:
        channel = resolve_channel(client, args.account, cfg, args.channel)
        report['channel_id'] = channel
        fresh, stats = collect(client, args.account, args.biz or cfg.get('biz', ''), channel, args.pages)
        report.update(stats)
    except core.ReaderError as exc:
        fresh = []
        report.update({'errors': [{'source': 'account_resolution', 'error': str(exc)}],
                       'verified_source_listing_complete': False, 'rejected_records': 0})
    unique = {core.article_key(row): row for row in fresh}
    report.update({'fetched_articles': len(unique), 'new_articles': len(unique.keys() - archive.keys())})
    archive.update(unique)
    rows = sorted(archive.values(), key=lambda r: (r.get('published_at', ''), r['url']), reverse=True)
    report.update({'finished_at': core.now(), 'archive_articles': len(rows)})
    core.export(args.out, rows, report, [])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not unique:
        return 2
    return 3 if args.strict and (report['errors'] or report['rejected_records']) else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (core.ReaderError, ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
