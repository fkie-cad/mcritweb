#!/usr/bin/python

import json
import logging
 
import unittest

from mcritweb.pagination import Pagination


LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


class MockRequest():

    def __init__(self, params) -> None:
        self.args = params


class PaginationTestSuite(unittest.TestCase):
    """Run a full example on a memory dump"""

    def testInitializations(self):
        test_values = [
            # no page query param
            {"req": {}, "max_value": 1000, "expected_page": 1, "expected_index": 0},
            # expected behavior, default limit
            {"req": {"p": 5}, "max_value": 1000, "expected_page": 5, "expected_index": 200},
            # expected behavior, custom limit
            {"req": {"p": 3}, "max_value": 1000, "limit": 100, "expected_page": 3, "expected_index": 200},
            # faulty query params
            {"req": {"p": 0}, "max_value": 1000, "expected_page": 1, "expected_index": 0},
            {"req": {"p": -1}, "max_value": 1000, "expected_page": 1, "expected_index": 0},
            {"req": {"p": "no_int"}, "max_value": 1000, "expected_page": 1, "expected_index": 0}
        ]
        for test_set in test_values:
            p = Pagination(MockRequest(test_set["req"]), test_set["max_value"])
            if "limit" in test_set:
                p = Pagination(MockRequest(test_set["req"]), test_set["max_value"], limit=test_set["limit"])
            self.assertEqual(p.page, test_set["expected_page"])
            self.assertEqual(p.start_index, test_set["expected_index"])

    def testPaginatedNav(self):
        test_values = [
            # no content
            {"req": {}, "max_value": 0, "expected_max_page": 1, "expected_page_index": 0, "expected_pages": [1]},
            # incomplete first page
            {"req": {"p": 1}, "max_value": 10, "expected_max_page": 1, "expected_page_index": 0, "expected_pages": [1]},
            # less pages than pagination_width
            {"req": {"p": 1}, "max_value": 70, "expected_max_page": 2, "expected_page_index": 0, "expected_pages": [1, 2]},
            # walking over a regular pagination
            {"req": {"p": 1}, "max_value": 251, "expected_max_page": 6, "expected_page_index": 0, "expected_pages": [1, 2, 3]},
            {"req": {"p": 1}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 0, "expected_pages": [1, 2, 3]},
            {"req": {"p": 2}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 1, "expected_pages": [1, 2, 3, 4]},
            {"req": {"p": 3}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 2, "expected_pages": [1, 2, 3, 4, 5]},
            {"req": {"p": 4}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 2, "expected_pages": [2, 3, 4, 5, 6]},
            {"req": {"p": 5}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 2, "expected_pages": [3, 4, 5, 6]},
            {"req": {"p": 6}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 2, "expected_pages": [4, 5, 6]},
            # reaching beyond max page returns last page
            {"req": {"p": 10}, "max_value": 300, "expected_max_page": 6, "expected_page_index": 2, "expected_pages": [4, 5, 6]},
            # expected behavior, custom limit
            {"req": {"p": 5}, "max_value": 1000, "limit": 100, "expected_max_page": 10, "expected_page_index": 2, "expected_pages": [3, 4, 5, 6, 7]},
        ]
        for test_set in test_values:
            p = Pagination(MockRequest(test_set["req"]), test_set["max_value"])
            if "limit" in test_set:
                p = Pagination(MockRequest(test_set["req"]), test_set["max_value"], limit=test_set["limit"])
            print(p)
            self.assertEqual(p.max_page, test_set["expected_max_page"])
            self.assertEqual(p.page_index, test_set["expected_page_index"])
            self.assertEqual(p.pages, test_set["expected_pages"])


if __name__ == "__main__":
    unittest.main()
