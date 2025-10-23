#!/usr/bin/env python3
"""Unit tests for navigation state management."""

import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import NavigationState  # noqa: E402


def _make_nav(group_cols=None) -> NavigationState:
    nav = NavigationState()
    nav.reset(group_cols or ["state", "username"])
    return nav


def test_apply_value_filters_store_lists_and_labels():
    nav = _make_nav()

    changed = nav.apply_value_filters("USERNAME", ["postgres"], [])
    assert changed

    assert nav.current_frame.filters == {"username": ["postgres"]}
    assert nav.current_frame.exclude_filters == {}
    assert nav.current_frame.labels["username"] == "USERNAME"
    assert nav.get_current_where_clause() == "username = 'postgres'"
    assert nav.get_filter_display() == "USERNAME=postgres"
    assert nav.get_breadcrumb_path().endswith("Included USERNAME=postgres")


def test_apply_value_filters_toggle_to_exclude():
    nav = _make_nav()
    nav.apply_value_filters("username", ["postgres"], [])

    changed = nav.apply_value_filters("USERNAME", [], ["postgres"])
    assert changed
    assert nav.current_frame.filters == {}
    assert nav.current_frame.exclude_filters == {"username": ["postgres"]}
    assert nav.get_current_where_clause() == "username != 'postgres'"
    assert nav.get_filter_display() == "USERNAME!=postgres"


def test_apply_value_filters_multiple_values_and_null():
    nav = _make_nav()

    nav.apply_value_filters("username", ["postgres", "root"], [])
    assert nav.current_frame.filters == {"username": ["postgres", "root"]}
    assert nav.get_current_where_clause() == "username IN ('postgres', 'root')"

    nav.apply_value_filters("username", [None], [])
    assert nav.current_frame.filters == {"username": [None]}
    assert nav.get_current_where_clause() == "username IS NULL"

    nav.apply_value_filters("username", [], [None])
    assert nav.current_frame.exclude_filters == {"username": [None]}
    assert nav.get_current_where_clause() == "username IS NOT NULL"


def test_apply_value_filters_modal_path_replaces_existing_filters():
    nav = _make_nav()
    nav.apply_value_filters("username", ["postgres"], [])

    # Value filter modal returns both include/exclude lists; exclude wins
    nav.apply_value_filters("username", ["postgres"], ["postgres"])
    assert nav.current_frame.filters == {}
    assert nav.current_frame.exclude_filters == {"username": ["postgres"]}

    # Clearing both lists removes the filter entirely
    nav.apply_value_filters("username", [], [])
    assert nav.current_frame.filters == {}
    assert nav.current_frame.exclude_filters == {}
    assert nav.get_current_where_clause() == "1=1"


def test_drill_down_and_back_out_sequence():
    nav = _make_nav(["state", "username", "exe"])

    frame = nav.drill_down("STATE", "RUN")
    assert frame.filters == {"state": ["RUN"]}
    assert nav.get_current_where_clause() == "state = 'RUN'"

    nav.drill_down("username", "postgres")
    assert nav.get_current_where_clause() == "state = 'RUN' AND username = 'postgres'"
    assert nav.get_filter_display() == "STATE=RUN AND username=postgres"

    back = nav.back_out()
    assert back is not None
    assert nav.get_current_where_clause() == "state = 'RUN'"

    back = nav.back_out()
    assert back is not None
    assert nav.get_current_where_clause() == "1=1"
    assert nav.get_filter_display() == "No filters applied"


def test_remove_last_filter_prefers_most_recent():
    nav = _make_nav(["state", "username"])
    nav.drill_down("state", "RUN")
    nav.drill_down("username", "postgres")
    assert nav.get_current_where_clause() == "state = 'RUN' AND username = 'postgres'"

    assert nav.remove_last_filter() is True
    assert nav.get_current_where_clause() == "state = 'RUN'"

    assert nav.remove_last_filter() is True
    assert nav.get_current_where_clause() == "1=1"

    assert nav.remove_last_filter() is False


if __name__ == "__main__":
    # Allow running the tests directly for quick checks
    import pytest  # type: ignore

    raise SystemExit(pytest.main([__file__]))
