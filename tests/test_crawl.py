import json
import unittest
from unittest.mock import Mock

import crawl as c
import reader as r

ACCOUNT = '郭磊宏观茶座'
BIZ = 'MzI1NzAwODc3Nw=='
CHANNEL = 'S10740353838202886'


def item(mid, **extra):
    return {'report_id': str(mid), 'title': '测试标题', 'channel_id': CHANNEL,
            'wechat_mp_name': ACCOUNT,
            'original_url': f'https://mp.weixin.qq.com/s?__biz={BIZ}&mid={mid}&idx=1&sn=abc', **extra}


def page(n, items, total=2, pages=2):
    return json.dumps({'page_num': n, 'items': items, 'total_count': total, 'total_page': pages})


class CrawlTests(unittest.TestCase):
    def test_pagination_and_complete_source_not_complete_wechat(self):
        client = Mock()
        client.get.side_effect = [page(1, [item(1)]), page(2, [item(2)])]
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 25)
        self.assertEqual(len(rows), 2)
        self.assertTrue(stats['verified_source_listing_complete'])
        self.assertEqual(client.get.call_count, 2)

    def test_page_budget_is_not_full_source(self):
        client = Mock()
        client.get.return_value = page(1, [item(1)])
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 1)
        self.assertEqual(len(rows), 1)
        self.assertFalse(stats['source_listing_exhausted'])

    def test_partial_results_survive_failure(self):
        client = Mock()
        client.get.side_effect = [page(1, [item(1)]), r.ReaderError('HTTP 429')]
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(stats['errors']), 1)
        self.assertEqual(client.get.call_count, 2)

    def test_changed_source_count_detected(self):
        client = Mock()
        client.get.side_effect = [page(1, [item(1)]), page(2, [item(2)], total=3)]
        _, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 2)
        self.assertTrue(stats['source_count_changed'])
        self.assertFalse(stats['verified_source_listing_complete'])

    def test_wrong_identity_rejected(self):
        client = Mock()
        client.get.return_value = page(1, [item(1, channel_id='S123')], total=1, pages=1)
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 1)
        self.assertFalse(rows)
        self.assertEqual(stats['rejected_records'], 1)

    def test_empty_page_with_positive_count_is_error(self):
        client = Mock()
        client.get.return_value = page(1, [])
        _, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 2)
        self.assertTrue(stats['errors'])

    def test_unknown_account_exact_name_resolution(self):
        client = Mock()
        client.get.return_value = json.dumps({'items': [{'chinese_name': ACCOUNT, 'channel_id': CHANNEL}]})
        self.assertEqual(c.resolve_channel(client, ACCOUNT, {}), CHANNEL)
        with self.assertRaises(r.ReaderError):
            c.resolve_channel(client, '其他账号', {})

    def test_duplicate_pagination_stops(self):
        client = Mock()
        client.get.side_effect = [page(1, [item(1)]), page(2, [item(1)])]
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 5)
        self.assertEqual(len(rows), 1)
        self.assertTrue(stats['errors'])


if __name__ == '__main__':
    unittest.main()
