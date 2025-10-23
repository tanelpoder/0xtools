#!/usr/bin/env python3
"""Tests for back-out navigation behaviour."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import NavigationState  # noqa: E402


def test_back_out_walks_history_stack():
    nav = NavigationState()
    nav.reset(["state", "username"])

    # Build history
    nav.drill_down("state", "RUN")
    nav.drill_down("username", "postgres")
    nav.apply_value_filters("username", ["postgres", "root"], [])

    # Remove filters one by one using back_out (history frames)
    assert nav.back_out() is not None
    assert nav.get_current_where_clause() == "state = 'RUN' AND username = 'postgres'"

    assert nav.back_out() is not None
    assert nav.get_current_where_clause() == "state = 'RUN'"

    assert nav.back_out() is not None
    assert nav.get_current_where_clause() == "1=1"

    # Nothing left to back out
    assert nav.back_out() is None


if __name__ == "__main__":
    import pytest  # type: ignore

    raise SystemExit(pytest.main([__file__]))
