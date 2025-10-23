#!/usr/bin/env python3
"""Unit tests for core.display.formatting helpers."""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.display import (
    compute_column_layout,
    format_value,
    render_block_sparkline,
    BLOCK_CHARACTERS,
)


class TestDisplayFormatting(unittest.TestCase):
    def test_format_value_state_mapping(self):
        self.assertEqual(format_value('state', 'R'), 'Running (ON CPU)')

    def test_format_value_syscall_running(self):
        self.assertEqual(format_value('syscall', 'NULL'), '[running]')

    def test_format_value_numeric(self):
        self.assertEqual(format_value('samples', 12345), '12,345')

    def test_format_value_latency_bucket(self):
        self.assertEqual(format_value('lat_bucket_us', 1000), '1ms')

    def test_format_value_none(self):
        self.assertEqual(format_value('connection', None), '-')

    def test_compute_column_layout_caps_and_numeric(self):
        columns = ['connection', 'samples']
        data = [{
            'connection': 'a' * 60,
            'samples': 1234,
        }]
        headers = {'connection': 'connection', 'samples': 'samples'}

        layout = compute_column_layout(columns, data, headers)

        self.assertEqual(layout.widths['connection'], 50)
        self.assertIn('samples', layout.numeric_columns)
        self.assertGreaterEqual(layout.widths['samples'], 8)

    def test_render_block_sparkline_basic(self):
        spark = render_block_sparkline([0, 2, 4, 8], max_chars=10)
        self.assertEqual(spark, '▁▃▅█')

    def test_render_block_sparkline_downsample(self):
        spark = render_block_sparkline(list(range(20)), max_chars=5)
        self.assertLessEqual(len(spark), 5)
        allowed = set(BLOCK_CHARACTERS)
        self.assertTrue(all(char in allowed for char in spark))


if __name__ == '__main__':
    unittest.main()
