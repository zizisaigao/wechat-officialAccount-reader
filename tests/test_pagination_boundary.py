import unittest
from unittest.mock import Mock

import crawl as c
from test_crawl import ACCOUNT, BIZ, CHANNEL, item, page


class PaginationBoundaryTest(unittest.TestCase):
    def test_zero_total_after_nonempty_page_is_not_completion(self):
        client = Mock()
        client.get.side_effect = [page(1, [item(1)]), page(2, [], total=0, pages=0)]
        rows, stats = c.collect(client, ACCOUNT, BIZ, CHANNEL, 25)
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats['source_total_count'], 2)
        self.assertTrue(stats['errors'])
        self.assertFalse(stats['source_listing_exhausted'])
