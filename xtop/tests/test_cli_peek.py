#!/usr/bin/env python3
"""Unit tests for CLI peek integration helpers."""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.peek_providers import HistogramTableData, HistogramTableRow


def _load_xtop_test_module():
    repo_root = Path(__file__).parent.parent
    module_path = repo_root / "xtop-test.py"
    spec = importlib.util.spec_from_file_location("xtop_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


xtop_test_module = _load_xtop_test_module()
XtopTester = xtop_test_module.XtopTester


def test_format_histogram_result_handles_empty_table():
    table = HistogramTableData(rows=[], total_count=0, total_time_s=0.0, max_time_s=0.0)
    result = XtopTester._format_histogram_result("sclat_histogram", table)

    assert result["histogram_type"] == "syscall"
    assert result["row_count"] == 0
    assert result["message"] == "No histogram data for current filters."


def test_format_histogram_result_serializes_rows():
    table = HistogramTableData(
        rows=[
            HistogramTableRow(
                bucket_us=64,
                count=10,
                est_time_s=0.125,
                est_events_per_s=80.0,
                time_pct=50.0,
                relative_time_ratio=1.0,
            )
        ],
        total_count=10,
        total_time_s=0.125,
        max_time_s=0.125,
    )

    result = XtopTester._format_histogram_result("iolat_histogram", table)

    assert result["histogram_type"] == "io"
    assert result["row_count"] == 1
    assert "message" not in result
    row = result["data"][0]
    assert row == {
        "bucket_us": 64,
        "count": 10,
        "est_time_s": 0.125,
        "est_events_per_s": 80.0,
        "time_pct": 50.0,
        "relative_time_ratio": 1.0,
    }
