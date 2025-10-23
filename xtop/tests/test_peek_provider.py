#!/usr/bin/env python3
"""Unit tests for histogram/stack peek provider utilities."""

import math

import pytest

from core.peek_providers import (
    HistogramPeekProvider,
    parse_histogram_string,
    parse_stack_trace,
)
from core.histogram_formatter import HistogramFormatter
from core.unified_formatter import UnifiedFormatter
from core.heatmap import LatencyHeatmap, HeatmapConfig
from core.time_utils import TimeUtils


def test_records_to_table_computes_totals_and_ratios():
    records = [
        {"bucket_us": 1000, "count": 10, "est_time_s": 0.010},
        {"bucket_us": 2000, "count": 5, "est_time_s": 0.005},
    ]

    table = HistogramPeekProvider._records_to_table(records)

    assert table.total_count == 15
    assert math.isclose(table.total_time_s, 0.015)
    assert math.isclose(table.max_time_s, 0.010)
    assert len(table.rows) == 2

    first, second = table.rows
    assert first.bucket_us == 1000
    assert math.isclose(first.est_events_per_s, 1000.0)
    assert math.isclose(first.time_pct, (0.010 / 0.015) * 100.0)
    assert math.isclose(first.relative_time_ratio, 1.0)

    assert second.bucket_us == 2000
    assert second.count == 5
    assert math.isclose(second.est_events_per_s, 1000.0)
    assert second.relative_time_ratio == pytest.approx(0.5)


def test_normalize_timeseries_records_inserts_defaults():
    rows = [
        {"HH": "04", "lat_bucket_us": 1000, "cnt": 3},
        {"HH": "04", "MI": "10", "lat_bucket_us": 2000, "cnt": 5},
    ]

    hourly = HistogramPeekProvider._normalize_timeseries_records(rows[:1], TimeUtils.GRANULARITY_HOUR)
    assert hourly[0]["MI"] == "00"

    ten_second = HistogramPeekProvider._normalize_timeseries_records(
        [{"HH": "04", "MI": "10", "S10": "20", "lat_bucket_us": 1000, "cnt": 1}],
        TimeUtils.GRANULARITY_SECOND,
    )
    assert ten_second[0]["S10"] == "20"


def test_histogram_and_stack_parsers():
    parsed_hist = parse_histogram_string("1000:5:0.01:10,2000:2:0.01:10")
    assert len(parsed_hist) == 2
    assert parsed_hist[0][0] == 1000

    parsed_stack = parse_stack_trace("main;foo;bar")
    assert parsed_stack == ["main", "foo", "bar"]

    assert parse_histogram_string("invalid") == []
    assert parse_stack_trace(None) == []


def test_latency_range_uses_half_bucket_as_lower_bound():
    formatter = HistogramFormatter()
    unified = UnifiedFormatter()
    heatmap = LatencyHeatmap(HeatmapConfig(width=10, height=4))

    assert formatter.format_latency_range(128) == "64-128μs"
    assert unified.format_latency_range(128) == "64-128μs"
    assert heatmap._format_latency(128) == "64-128μs"

    assert formatter.format_latency_range(2048) == "1.0-2.0ms"
    assert unified.format_latency_range(2048) == "1.0-2.0ms"
    assert heatmap._format_latency(2048) == "1.0-2.0ms"

    assert formatter.format_latency_range(2_000_000) == "1.0-2.0s"
    assert unified.format_latency_range(2_000_000) == "1.0-2.0s"
    assert heatmap._format_latency(2_000_000) == "1.0-2.0s"


def test_heatmap_labels_align_with_variable_lengths():
    config = HeatmapConfig(width=5, height=4, use_color=False, use_rich_markup=False)
    heatmap = LatencyHeatmap(config)

    data = [
        {'HH': '00', 'MI': '00', 'lat_bucket_us': 64, 'count': 1},
        {'HH': '00', 'MI': '00', 'lat_bucket_us': 128, 'count': 2},
    ]

    heatmap_str = heatmap.generate_timeseries_heatmap(data)

    label_positions = {
        line.index('│')
        for line in heatmap_str.splitlines()
        if '│' in line
    }

    assert len(label_positions) == 1
