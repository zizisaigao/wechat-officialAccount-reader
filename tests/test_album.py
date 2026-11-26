import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import album

SOURCE='https://mp.weixin.qq.com/mp/appmsgalbum?__biz=AAA==&album_id=123&action=getalbum'
PAGE='''<span class="album__author-name">目标账号</span><span class="album__label-title">研究合集</span><script>var c={article_count:'46'};</script><li data-title="A &amp; B" data-link="http://mp.weixin.qq.com/s?__biz=AAA==&amp;mid=1&amp;idx=2&amp;sn=abc&amp;scene=1"><span class="js_article_create_time">1794903566</span></li>'''
class AlbumTests(unittest.TestCase):
    def test_seed(self):
        self.assertEqual(album.album_url('https://mp.weixin.qq.com/s?__biz=AAA==&cur_album_id=123&mid=1'),album.album_url(SOURCE))
    def test_public_page(self):
        rows,r=album.parse_album(PAGE,'目标账号',SOURCE)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['title'],'A & B')
        self.assertNotIn('scene=',rows[0]['url'])
        self.assertEqual(r['source_total_count'],46)
        self.assertFalse(r['album_complete'])
        self.assertFalse(r['complete_history'])
    def test_account_mismatch(self):
        with self.assertRaises(album.AlbumError):album.parse_album(PAGE,'其他账号',SOURCE)
    def test_biz_mismatch(self):
        with self.assertRaises(album.AlbumError):album.parse_album(PAGE.replace('__biz=AAA','__biz=BBB'),'目标账号',SOURCE)
    def test_duplicate(self):
        rows,_=album.parse_album(PAGE+PAGE,'目标账号',SOURCE)
        self.assertEqual(len(rows),1)
    def test_captcha(self):
        with self.assertRaises(album.AlbumError):album.parse_album('<html>验证码</html>','目标账号',SOURCE)
    def test_missing_album(self):
        with self.assertRaises(album.AlbumError):album.album_url('https://mp.weixin.qq.com/s?__biz=AAA==&mid=1')
    def test_unsafe(self):
        for link in ['https://mp.weixin.qq.com.evil.test/mp/appmsgalbum?__biz=A&album_id=1', SOURCE+'&token=secret']:
            with self.assertRaises(album.AlbumError):album.album_url(link)
    def test_limit(self):
        second=PAGE.replace('mid=1','mid=2')
        rows,r=album.parse_album(PAGE+second,'目标账号',SOURCE,1)
        self.assertEqual(len(rows),1);self.assertEqual(r['page_loaded_articles'],2)
if __name__=='__main__':unittest.main()
