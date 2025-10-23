#!/usr/bin/env python3
"""Tests for QueryBuilder schema-aware behaviour."""

import unittest
from pathlib import Path

from core.query_builder import QueryBuilder


class TestQueryBuilderSchema(unittest.TestCase):
    def setUp(self):
        self.qb = QueryBuilder(Path('.'), Path('sql/fragments'))

    def test_column_expr_uses_null_when_missing(self):
        self.qb.set_schema_info({'syscend': [('duration_ns', 'BIGINT')]})
        present = self.qb._column_expr('syscend', 'sc', 'duration_ns', 'sc_duration_ns')
        missing = self.qb._column_expr('syscend', 'sc', 'type', 'sc_type')
        self.assertEqual(present, 'sc.duration_ns AS sc_duration_ns')
        self.assertEqual(missing, 'NULL AS sc_type')

    def test_join_skipped_when_keys_missing(self):
        self.qb.set_schema_info({'syscend': [('duration_ns', 'BIGINT')]})
        sql = self.qb._build_base_samples_cte({'syscend'}, '1=1', None, None, False, False)
        self.assertIn('NULL AS sc_duration_ns', sql)
        self.assertNotIn('LEFT OUTER JOIN', sql)


if __name__ == '__main__':
    unittest.main()
