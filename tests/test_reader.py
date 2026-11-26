import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reader as r

ACCOUNT = '郭磊宏观茶座'
BIZ = 'MzI1NzAwODc3Nw=='
URL = f'https://mp.weixin.qq.com/s?__biz={BIZ}&mid=123&idx=1&sn=abc&scene=1&key=private#rd'
SOURCE = 'https://reportify.cn/social-media/123'


def obj(**kwargs):
    return {'title': '中文标题“宏观”', 'original_url': URL,
            'wechat_mp_name': ACCOUNT, 'publish_at': 1795345039000, **kwargs}


def flight(value, split=False):
    body = 'abcd:D' + json.dumps({'main': value}, ensure_ascii=False) + '\n'
    chunks = [body[:27], body[27:]] if split else [body]
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, part], ensure_ascii=False) + ')</script>' for part in chunks)


class ParsingTests(unittest.TestCase):
    def test_canonical_strips_credentials(self):
        url = r.canonical_wechat(URL.replace('&', '&amp;'))
        self.assertNotIn('key=', url)
        self.assertNotIn('scene=', url)
        self.assertNotIn('#', url)
        self.assertIn('mid=123', url)

    def test_rejects_non_article(self):
        for url in ['javascript:alert(1)', 'https://mp.weixin.qq.com.evil/s/abc',
                    'https://mp.weixin.qq.com/mp/qrcode?__biz=abc', 'https://mp.weixin.qq.com/s?__biz=abc']:
            with self.subTest(url=url), self.assertRaises(r.ReaderError):
                r.canonical_wechat(url)

    def test_short_link(self):
        self.assertEqual(r.canonical_wechat('http://mp.weixin.qq.com/s/Ab-c_1?scene=1'), 'https://mp.weixin.qq.com/s/Ab-c_1')

    def test_rejects_private_and_credential_fetch(self):
        for url in ['http://127.0.0.1/', 'https://reportify.cn.evil/social-media/1',
                    'https://reportify.cn/social-media/1?token=abc', 'https://u:p@reportify.cn/']:
            with self.subTest(url=url), self.assertRaises(r.ReaderError):
                r.allowed_url(url)

    def test_json_nested(self):
        text = json.dumps({'data': json.dumps({'main': obj()})})
        rows = r.parse_reportify(text, ACCOUNT, BIZ, SOURCE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], obj()['title'])

    def test_react_tagged_and_split_flight(self):
        rows = r.parse_reportify(flight(obj(), True), ACCOUNT, BIZ, SOURCE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['verification'], 'biz_match')

    def test_duplicate_serialization(self):
        text = flight(obj()) * 2
        self.assertEqual(len(r.parse_reportify(text, ACCOUNT, BIZ, SOURCE)), 1)

    def test_same_title_different_articles(self):
        text = json.dumps([obj(), obj(original_url=URL.replace('mid=123', 'mid=124'))])
        self.assertEqual(len(r.parse_reportify(text, ACCOUNT, BIZ, SOURCE)), 2)

    def test_wrong_account_and_wrong_biz(self):
        self.assertFalse(r.parse_reportify(flight(obj(wechat_mp_name='其他账号')), ACCOUNT, BIZ, SOURCE))
        self.assertFalse(r.parse_reportify(flight(obj(original_url=URL.replace(BIZ, 'other'))), ACCOUNT, BIZ, SOURCE))

    def test_unknown_account_requires_matching_name(self):
        self.assertTrue(r.parse_reportify(flight(obj()), ACCOUNT, '', SOURCE))
        self.assertFalse(r.parse_reportify(flight(obj(wechat_mp_name='')), ACCOUNT, '', SOURCE))

    def test_missing_link_or_title(self):
        for data in [obj(original_url=''), obj(title=''), obj(original_url='https://example.org/')]:
            self.assertFalse(r.parse_reportify(flight(data), ACCOUNT, BIZ, SOURCE))

    def test_malformed_or_login_is_not_success(self):
        for text in ['', '<title>登录</title>', '<script>self.__next_f.push(not JSON)</script>']:
            self.assertFalse(r.parse_reportify(text, ACCOUNT, BIZ, SOURCE))

    def test_index_does_not_invent_links(self):
        text = '<title>' + ACCOUNT + '</title><span class="item_title"><span class="hide-content">标题</span></span><a id="p_next" href="?page=2">下一页</a>'
        rows, next_url = r.parse_index(text, ACCOUNT, 'https://www.jintiankansha.com/column/abc')
        self.assertEqual(rows[0]['status'], 'title_only')
        self.assertNotIn('url', rows[0])
        self.assertTrue(next_url.endswith('?page=2'))

    def test_export_escapes_html_and_csv(self):
        row = r.row_from_metadata(obj(title='=bad <script>alert(1)</script>'), ACCOUNT, BIZ, SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            r.export(out, [row], {'account': ACCOUNT, 'fetched_articles': 1}, [])
            self.assertNotIn('<script>', (out / 'index.html').read_text())
            self.assertIn("'=bad", (out / 'articles.csv').read_text())
            self.assertEqual(json.loads((out / 'articles.json').read_text())[0]['title'], row['title'])

    def test_epoch_milliseconds(self):
        self.assertEqual(r.published(1795345039000), '2026-11-22T10:57:19+00:00')

    def test_empty_run_exit_2(self):
        with tempfile.TemporaryDirectory() as folder:
            code = r.main(['未配置账号', '--pages', '0', '--out', folder])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads((Path(folder)/'run.json').read_text())['fetched_articles'], 0)

    def test_incremental_run_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r.Client, 'get', return_value=flight(obj())):
            args = [ACCOUNT, '--pages', '0', '--no-bundled', '--url', SOURCE, '--out', folder]
            self.assertEqual(r.main(args), 0)
            self.assertEqual(r.main(args), 0)
            report = json.loads((Path(folder)/'run.json').read_text())
            self.assertEqual(report['archive_articles'], 1)
            self.assertEqual(report['new_articles'], 0)

    def test_mixed_account_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'articles.json').write_text(json.dumps([{'account': '其他账号', 'url': URL}]))
            with self.assertRaises(r.ReaderError):
                r.main([ACCOUNT, '--pages', '0', '--no-bundled', '--out', folder])


if __name__ == '__main__':
    unittest.main()
