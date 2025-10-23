#!/usr/bin/env python3
"""
Tests for time_utils module.
"""

import sys
import os
import unittest
from typing import Dict, List
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.time_utils import TimeUtils, parse_time_spec, resolve_time_range


class TestTimeUtils(unittest.TestCase):
    """Test cases for TimeUtils class"""
    
    def test_parse_s10_value(self):
        """Test S10 value parsing with various input types"""
        # Test normal cases
        self.assertEqual(TimeUtils.parse_s10_value('00'), 0)
        self.assertEqual(TimeUtils.parse_s10_value('10'), 10)
        self.assertEqual(TimeUtils.parse_s10_value('30'), 30)
        
        # Test float string cases (the bug we fixed)
        self.assertEqual(TimeUtils.parse_s10_value('0.'), 0)
        self.assertEqual(TimeUtils.parse_s10_value('10.0'), 10)
        self.assertEqual(TimeUtils.parse_s10_value('30.5'), 30)
        
        # Test numeric types
        self.assertEqual(TimeUtils.parse_s10_value(0), 0)
        self.assertEqual(TimeUtils.parse_s10_value(10), 10)
        self.assertEqual(TimeUtils.parse_s10_value(30.7), 30)
        
        # Test edge cases
        self.assertEqual(TimeUtils.parse_s10_value(None), 0)
        self.assertEqual(TimeUtils.parse_s10_value(''), 0)
        self.assertEqual(TimeUtils.parse_s10_value('invalid'), 0)
    
    def test_extract_time_buckets(self):
        """Test time bucket extraction for different granularities"""
        # Test data row
        row = {'HH': '14', 'MI': '35', 'S10': '20'}
        
        # Test hour granularity
        self.assertEqual(
            TimeUtils.extract_time_buckets(row, TimeUtils.GRANULARITY_HOUR),
            '14'
        )
        
        # Test minute granularity
        self.assertEqual(
            TimeUtils.extract_time_buckets(row, TimeUtils.GRANULARITY_MINUTE),
            '14:35'
        )
        
        # Test second granularity
        self.assertEqual(
            TimeUtils.extract_time_buckets(row, TimeUtils.GRANULARITY_SECOND),
            '14:35:20'
        )
        
        # Test with missing values
        empty_row = {}
        self.assertEqual(
            TimeUtils.extract_time_buckets(empty_row, TimeUtils.GRANULARITY_MINUTE),
            '00:00'
        )
    
    def test_sort_by_time(self):
        """Test sorting data by time buckets"""
        # Test data
        data = [
            {'HH': '14', 'MI': '35', 'S10': '20'},
            {'HH': '13', 'MI': '45', 'S10': '10'},
            {'HH': '14', 'MI': '30', 'S10': '50'},
            {'HH': '14', 'MI': '35', 'S10': '10'},
        ]
        
        # Test hour sorting
        sorted_hh = TimeUtils.sort_by_time(data, TimeUtils.GRANULARITY_HOUR)
        self.assertEqual(sorted_hh[0]['HH'], '13')
        self.assertEqual(sorted_hh[-1]['HH'], '14')
        
        # Test minute sorting
        sorted_mi = TimeUtils.sort_by_time(data, TimeUtils.GRANULARITY_MINUTE)
        self.assertEqual((sorted_mi[0]['HH'], sorted_mi[0]['MI']), ('13', '45'))
        self.assertEqual((sorted_mi[-1]['HH'], sorted_mi[-1]['MI']), ('14', '35'))
        
        # Test second sorting
        sorted_s10 = TimeUtils.sort_by_time(data, TimeUtils.GRANULARITY_SECOND)
        self.assertEqual(
            (sorted_s10[0]['HH'], sorted_s10[0]['MI'], sorted_s10[0]['S10']),
            ('13', '45', '10')
        )
    
    def test_get_missing_buckets_hour(self):
        """Test detection of missing hour buckets"""
        prev = {'HH': '10', 'MI': '00'}
        curr = {'HH': '13', 'MI': '00'}
        
        missing = TimeUtils.get_missing_buckets(prev, curr, TimeUtils.GRANULARITY_HOUR)
        
        self.assertEqual(len(missing), 2)
        self.assertEqual(missing[0]['HH'], '11')
        self.assertEqual(missing[1]['HH'], '12')
    
    def test_get_missing_buckets_minute(self):
        """Test detection of missing minute buckets"""
        prev = {'HH': '10', 'MI': '58'}
        curr = {'HH': '11', 'MI': '02'}
        
        missing = TimeUtils.get_missing_buckets(prev, curr, TimeUtils.GRANULARITY_MINUTE)
        
        self.assertEqual(len(missing), 3)
        self.assertEqual(missing[0], {'HH': '10', 'MI': '59'})
        self.assertEqual(missing[1], {'HH': '11', 'MI': '00'})
        self.assertEqual(missing[2], {'HH': '11', 'MI': '01'})
    
    def test_get_missing_buckets_s10(self):
        """Test detection of missing 10-second buckets"""
        prev = {'HH': '10', 'MI': '00', 'S10': '40'}
        curr = {'HH': '10', 'MI': '01', 'S10': '10'}
        
        missing = TimeUtils.get_missing_buckets(prev, curr, TimeUtils.GRANULARITY_SECOND)
        
        # Should have 50 and 00, but not 10 (which is curr)
        self.assertEqual(len(missing), 2)
        self.assertEqual(missing[0], {'HH': '10', 'MI': '00', 'S10': '50'})
        self.assertEqual(missing[1], {'HH': '10', 'MI': '01', 'S10': '00'})
    
    def test_fill_missing_buckets(self):
        """Test filling missing time buckets with zeros"""
        # Test data with gaps
        data = [
            {'HH': '10', 'MI': '00', 'lat_bucket_us': 1000, 'cnt': 5},
            {'HH': '10', 'MI': '00', 'lat_bucket_us': 2000, 'cnt': 3},
            {'HH': '10', 'MI': '02', 'lat_bucket_us': 1000, 'cnt': 7},
            {'HH': '10', 'MI': '02', 'lat_bucket_us': 2000, 'cnt': 2},
        ]
        
        filled = TimeUtils.fill_missing_buckets(data, TimeUtils.GRANULARITY_MINUTE)
        
        # Should have original 4 entries plus 1 missing minute * 2 latency buckets = 6 total
        # (10:00 -> 10:02 has one missing minute: 10:01)
        self.assertEqual(len(filled), 6)
        
        # Check that missing entries have zero counts
        missing_entries = [e for e in filled if e.get('MI') == '01']
        self.assertEqual(len(missing_entries), 2)  # Two latency buckets
        for entry in missing_entries:
            self.assertEqual(entry['cnt'], 0)

    def test_parse_time_spec_relative(self):
        """Relative specifications subtract from the reference time by default."""
        reference = datetime(2025, 1, 2, 12, 0, 0)

        result = parse_time_spec('5min', now=reference)
        self.assertEqual(result.timestamp, reference - timedelta(minutes=5))
        self.assertTrue(result.is_relative)

        result_explicit = parse_time_spec('-30s', now=reference)
        self.assertEqual(result_explicit.timestamp, reference - timedelta(seconds=30))
        self.assertTrue(result_explicit.is_relative)

        result_ago = parse_time_spec('10min ago', now=reference)
        self.assertEqual(result_ago.timestamp, reference - timedelta(minutes=10))
        self.assertTrue(result_ago.is_relative)

    def test_parse_time_spec_explicit_positive_and_keywords(self):
        reference = datetime(2025, 1, 2, 12, 0, 0)

        result = parse_time_spec('+5min', now=reference)
        self.assertEqual(result.timestamp, reference + timedelta(minutes=5))
        self.assertTrue(result.is_relative)
        self.assertTrue(result.has_explicit_sign)

        today = parse_time_spec('today', now=reference)
        self.assertEqual(today.timestamp, datetime(2025, 1, 2, 0, 0, 0))
        self.assertTrue(today.is_relative)

        yesterday = parse_time_spec('yesterday', now=reference)
        self.assertEqual(yesterday.timestamp, datetime(2025, 1, 1, 0, 0, 0))
        self.assertTrue(yesterday.is_relative)

    def test_parse_time_spec_absolute(self):
        """Absolute specifications should ignore the relative heuristics."""
        reference = datetime(2025, 1, 2, 12, 0, 0)

        absolute = parse_time_spec('2024-12-31 23:59:00', now=reference)
        self.assertEqual(absolute.timestamp, datetime(2024, 12, 31, 23, 59, 0))
        self.assertFalse(absolute.is_relative)

        time_only = parse_time_spec('08:15', now=reference)
        self.assertEqual(time_only.timestamp, datetime(2025, 1, 2, 8, 15, 0))
        self.assertFalse(time_only.is_relative)

        with self.assertRaises(ValueError):
            parse_time_spec('notatime', now=reference)

    def test_resolve_time_range_defaults_to_now(self):
        reference = datetime(2025, 1, 2, 12, 0, 0)
        low, high, meta = resolve_time_range('5min', None, now=reference)
        self.assertEqual(low, reference - timedelta(minutes=5))
        self.assertEqual(high, reference)
        self.assertTrue(meta['default_to_now'])

    def test_resolve_time_range_relative_window(self):
        reference = datetime(2025, 1, 2, 12, 0, 0)
        low, high, meta = resolve_time_range('15min', '5min', now=reference)
        self.assertEqual(low, reference - timedelta(minutes=15))
        self.assertEqual(high, reference - timedelta(minutes=5))
        self.assertFalse(meta['default_to_now'])

    def test_resolve_time_range_absolute(self):
        reference = datetime(2025, 1, 2, 12, 0, 0)
        low, high, meta = resolve_time_range(
            '2025-01-01T00:00:00',
            '2025-01-01T01:00:00',
            now=reference,
        )
        self.assertEqual(low, datetime(2025, 1, 1, 0, 0, 0))
        self.assertEqual(high, datetime(2025, 1, 1, 1, 0, 0))
        self.assertFalse(meta['default_to_now'])

    def test_format_time_range(self):
        """Test time range formatting"""
        self.assertEqual(
            TimeUtils.format_time_range('2025-01-01', '2025-01-02'),
            '2025-01-01 to 2025-01-02'
        )
        self.assertEqual(
            TimeUtils.format_time_range('2025-01-01', None),
            'from 2025-01-01'
        )
        self.assertEqual(
            TimeUtils.format_time_range(None, '2025-01-02'),
            'until 2025-01-02'
        )
        self.assertEqual(
            TimeUtils.format_time_range(None, None),
            'all time'
        )
    
    def test_get_time_select_sql(self):
        """Test SQL fragment generation for time buckets"""
        # Test hour granularity
        select_h, group_h, order_h = TimeUtils.get_time_select_sql(TimeUtils.GRANULARITY_HOUR)
        self.assertIn('EXTRACT(HOUR', select_h)
        self.assertEqual(group_h, 'HH')
        self.assertEqual(order_h, 'HH')
        
        # Test minute granularity
        select_m, group_m, order_m = TimeUtils.get_time_select_sql(TimeUtils.GRANULARITY_MINUTE)
        self.assertIn('EXTRACT(HOUR', select_m)
        self.assertIn('EXTRACT(MINUTE', select_m)
        self.assertEqual(group_m, 'HH, MI')
        self.assertEqual(order_m, 'HH, MI')
        
        # Test second granularity
        select_s, group_s, order_s = TimeUtils.get_time_select_sql(TimeUtils.GRANULARITY_SECOND)
        self.assertIn('EXTRACT(SECOND', select_s)
        self.assertEqual(group_s, 'HH, MI, S10')
        self.assertEqual(order_s, 'HH, MI, S10')
    
    def test_build_time_constraints(self):
        """Test SQL time constraint building"""
        # Test both constraints
        sql = TimeUtils.build_time_constraints('2025-01-01', '2025-01-02')
        self.assertIn("timestamp >= TIMESTAMP '2025-01-01'", sql)
        self.assertIn("timestamp < TIMESTAMP '2025-01-02'", sql)
        
        # Test only start
        sql = TimeUtils.build_time_constraints('2025-01-01', None)
        self.assertIn("timestamp >= TIMESTAMP '2025-01-01'", sql)
        self.assertNotIn("timestamp <", sql)
        
        # Test only end
        sql = TimeUtils.build_time_constraints(None, '2025-01-02')
        self.assertNotIn("timestamp >=", sql)
        self.assertIn("timestamp < TIMESTAMP '2025-01-02'", sql)
        
        # Test no constraints
        sql = TimeUtils.build_time_constraints(None, None)
        self.assertEqual(sql, "")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
