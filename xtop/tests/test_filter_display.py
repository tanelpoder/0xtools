#!/usr/bin/env python3
"""Tests for human-readable filter display helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import NavigationState  # noqa: E402


def test_filter_display_formats_single_and_multiple_values():
    nav = NavigationState()
    nav.reset(["state", "username"])

    assert nav.get_filter_display() == "No filters applied"

    nav.drill_down("STATE", "RUN")
    assert nav.get_filter_display() == "STATE=RUN"

    nav.apply_value_filters("username", ["postgres", "root"], [])
    assert nav.get_filter_display() == "STATE=RUN AND username in [postgres, root]"

    nav.apply_value_filters("username", [], ["daemon"])
    assert nav.get_filter_display() == "STATE=RUN AND username!=daemon"

    nav.remove_last_filter()
    assert nav.get_filter_display() == "STATE=RUN"


def test_latency_columns_use_human_readable_labels():
    nav = NavigationState()
    nav.reset(["sc.p95_us"])

    nav.drill_down("sc.p95_us", 128)
    assert "SC P95 (us)=128" in nav.get_breadcrumb_path()
    assert nav.get_filter_display() == "SC P95 (us)=128"


def test_latency_labels_in_value_filters():
    nav = NavigationState()
    nav.reset(["io.avg_lat_us"])

    assert nav.apply_value_filters("io.avg_lat_us", [250], []) is True
    assert nav.get_filter_display() == "IO Avg Lat (us)=250"
    assert nav.current_frame.description.startswith("Included IO Avg Lat (us)=")


def test_value_filter_summary_for_many_values():
    nav = NavigationState()
    nav.reset(["username"])

    values = ["postgres", "root", "daemon", "nobody", "redis"]
    assert nav.apply_value_filters("username", values, [])

    summary = "[postgres, root, daemon, ... +2 more]"
    assert nav.get_filter_display() == f"username in {summary}"
    assert nav.current_frame.description == f"Included username={summary}"


if __name__ == "__main__":
    import pytest  # type: ignore

    raise SystemExit(pytest.main([__file__]))
