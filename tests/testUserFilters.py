#!/usr/bin/python

import logging
import os
import tempfile
import unittest

from flask import Flask

from mcritweb.db import UserFilters, init_db

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


# the fields UserFilters actually persists; the remainder are request-scoped only
PERSISTED_FIELDS = [
    "filter_direct_min_score",
    "filter_direct_nonlib_min_score",
    "filter_frequency_min_score",
    "filter_frequency_nonlib_min_score",
    "filter_unique_only",
    "filter_exclude_own_family",
    "filter_function_min_score",
    "filter_function_max_score",
    "filter_max_num_families",
    "filter_exclude_library",
    "filter_exclude_pic",
]

FILTERS_A = {
    "filter_direct_min_score": 11,
    "filter_direct_nonlib_min_score": 12,
    "filter_frequency_min_score": 13,
    "filter_frequency_nonlib_min_score": 14,
    "filter_unique_only": True,
    "filter_exclude_own_family": True,
    "filter_function_min_score": 15,
    "filter_function_max_score": 16,
    "filter_max_num_families": 17,
    "filter_exclude_library": True,
    "filter_exclude_pic": True,
}

FILTERS_B = {
    "filter_direct_min_score": 81,
    "filter_direct_nonlib_min_score": 82,
    "filter_frequency_min_score": 83,
    "filter_frequency_nonlib_min_score": 84,
    "filter_unique_only": False,
    "filter_exclude_own_family": False,
    "filter_function_min_score": 85,
    "filter_function_max_score": 86,
    "filter_max_num_families": 87,
    "filter_exclude_library": False,
    "filter_exclude_pic": False,
}


class UserFiltersTestSuite(unittest.TestCase):
    """Persistence behaviour of UserFilters against a throwaway SQLite database."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        # Flask("mcritweb") so current_app.open_resource() resolves the package's sql/ folder
        self.app = Flask("mcritweb")
        self.app.config["DATABASE"] = os.path.join(self._tmpdir.name, "mcritweb.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _persisted(self, user_filters):
        return {name: getattr(user_filters, name) for name in PERSISTED_FIELDS}

    def testSaveIsScopedToTheOwningUser(self):
        """Saving one user's filters must not overwrite another user's (issue #81)."""
        with self.app.app_context():
            init_db()
            UserFilters.fromDict(1, FILTERS_A).saveToDb()
            UserFilters.fromDict(2, FILTERS_B).saveToDb()
            before = self._persisted(UserFilters.fromDb(1))

            # re-saving user 2 takes the UPDATE branch, which is where the bug lived
            filters_b = UserFilters.fromDb(2)
            filters_b.filter_direct_min_score = 99
            filters_b.saveToDb()

            self.assertEqual(before, self._persisted(UserFilters.fromDb(1)),
                             "saving user 2's filters modified user 1's")
            # guard against the test passing because the UPDATE did nothing at all
            self.assertEqual(UserFilters.fromDb(2).filter_direct_min_score, 99)

    def testRoundTripPreservesValues(self):
        """An inserted row reads back with the values it was given."""
        with self.app.app_context():
            init_db()
            UserFilters.fromDict(1, FILTERS_A).saveToDb()
            expected = self._persisted(UserFilters.fromDict(1, FILTERS_A))
            self.assertEqual(expected, self._persisted(UserFilters.fromDb(1)))

    def testScoresAreClampedToValidRange(self):
        """Out-of-range scores are clamped rather than stored verbatim."""
        with self.app.app_context():
            init_db()
            out_of_range = dict(FILTERS_A)
            out_of_range["filter_direct_min_score"] = 5000
            out_of_range["filter_function_min_score"] = -5000
            UserFilters.fromDict(1, out_of_range).saveToDb()

            stored = UserFilters.fromDb(1)
            self.assertEqual(stored.filter_direct_min_score, 100)
            self.assertEqual(stored.filter_function_min_score, 0)


if __name__ == "__main__":
    unittest.main()
