from datetime import datetime, timedelta
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from core.query_engine import QueryResult

_XT0P_PATH = Path(__file__).resolve().parent.parent / "xtop"
_loader = SourceFileLoader("_xtop_module", str(_XT0P_PATH))
_spec = importlib.util.spec_from_loader("_xtop_module", _loader)
_xtop_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_xtop_module)  # type: ignore[union-attr]

build_avg_thr_timeline_line = _xtop_module.build_avg_thr_timeline_line
compute_selection_window = _xtop_module.compute_selection_window
resolve_active_time_range = _xtop_module.resolve_active_time_range


class _DummyEngine:
    def __init__(self, rows):
        self._rows = rows

    def execute_with_params(self, params, debug=False, latency_columns=None):  # pragma: no cover - simple stub
        return QueryResult(
            data=self._rows,
            columns=['yyyy', 'mm', 'dd', 'hh', 'mi', 'avg_threads'],
            row_count=len(self._rows),
            execution_time=0.0,
        )


def test_build_avg_thr_timeline_line_renders_sparkline():
    rows = [
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 0, 'avg_threads': 1.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 1, 'avg_threads': 2.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 2, 'avg_threads': 3.0},
    ]
    engine = _DummyEngine(rows)

    line = build_avg_thr_timeline_line(
        engine,
        where_clause='1=1',
        low_time=datetime(2024, 1, 1, 0, 0),
        high_time=datetime(2024, 1, 1, 0, 2, 30),
        max_width=80,
        logger=None,
    )

    assert line.startswith('AvgThreads: ')
    assert line.endswith('▃▆█')


def test_build_avg_thr_timeline_line_without_time_range():
    engine = _DummyEngine([])

    line = build_avg_thr_timeline_line(
        engine,
        where_clause='1=1',
        low_time=None,
        high_time=None,
        max_width=80,
        logger=None,
    )

    assert line == 'AvgThreads: (time range unavailable)'


def test_build_avg_thr_timeline_line_markup_highlight():
    rows = [
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 0, 'avg_threads': 1.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 1, 'avg_threads': 2.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 2, 'avg_threads': 3.0},
    ]
    engine = _DummyEngine(rows)

    line = build_avg_thr_timeline_line(
        engine,
        where_clause='1=1',
        low_time=datetime(2024, 1, 1, 0, 0),
        high_time=datetime(2024, 1, 1, 0, 3, 0),
        max_width=80,
        logger=None,
        highlight_low=datetime(2024, 1, 1, 0, 2, 0),
        highlight_high=datetime(2024, 1, 1, 0, 3, 0),
        render_mode="markup",
    )

    assert '[bold yellow]' in line
    assert '[/bold yellow]' in line
    assert line.endswith('▃▆[bold yellow]█[/bold yellow]')


def test_build_avg_thr_timeline_line_ansi_highlight():
    rows = [
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 0, 'avg_threads': 1.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 1, 'avg_threads': 2.0},
        {'YYYY': 2024, 'MM': 1, 'DD': 1, 'HH': 0, 'MI': 2, 'avg_threads': 3.0},
    ]
    engine = _DummyEngine(rows)

    line = build_avg_thr_timeline_line(
        engine,
        where_clause='1=1',
        low_time=datetime(2024, 1, 1, 0, 0),
        high_time=datetime(2024, 1, 1, 0, 3, 0),
        max_width=80,
        logger=None,
        highlight_low=datetime(2024, 1, 1, 0, 1, 30),
        highlight_high=datetime(2024, 1, 1, 0, 2, 30),
        render_mode="ansi",
    )

    assert '[1;33m' in line
    assert '[0m' in line


def test_compute_selection_window_defaults_to_last_five_minutes():
    loaded_low = datetime(2024, 1, 1, 0, 0)
    loaded_high = datetime(2024, 1, 1, 1, 0)

    sel_low, sel_high = compute_selection_window(loaded_low, loaded_high)

    assert sel_high == loaded_high
    assert sel_low == loaded_high - timedelta(minutes=5)


def test_compute_selection_window_single_override_expands_default():
    loaded_low = datetime(2024, 1, 1, 0, 0)
    loaded_high = datetime(2024, 1, 1, 1, 0)
    override_low = loaded_low + timedelta(minutes=10)

    sel_low, sel_high = compute_selection_window(loaded_low, loaded_high, override_low=override_low)

    assert sel_low == override_low
    assert sel_high == override_low + timedelta(minutes=5)


def test_compute_selection_window_raises_when_outside_loaded_range():
    loaded_low = datetime(2024, 1, 1, 0, 0)
    loaded_high = datetime(2024, 1, 1, 1, 0)

    with pytest.raises(ValueError):
        compute_selection_window(
            loaded_low,
            loaded_high,
            override_low=loaded_low - timedelta(minutes=10),
            override_high=loaded_low - timedelta(minutes=5),
        )


def test_resolve_active_time_range_prefers_selection_when_enabled():
    selection_low = datetime(2024, 1, 1, 0, 55)
    selection_high = datetime(2024, 1, 1, 1, 0)
    loaded_low = datetime(2024, 1, 1, 0, 0)
    loaded_high = datetime(2024, 1, 1, 1, 0)

    active_low, active_high = resolve_active_time_range(
        True,
        selection_low,
        selection_high,
        loaded_low,
        loaded_high,
    )

    assert active_low == selection_low
    assert active_high == selection_high


def test_resolve_active_time_range_returns_loaded_when_disabled():
    selection_low = datetime(2024, 1, 1, 0, 55)
    selection_high = datetime(2024, 1, 1, 1, 0)
    loaded_low = datetime(2024, 1, 1, 0, 0)
    loaded_high = datetime(2024, 1, 1, 1, 0)

    active_low, active_high = resolve_active_time_range(
        False,
        selection_low,
        selection_high,
        loaded_low,
        loaded_high,
    )

    assert active_low == loaded_low
    assert active_high == loaded_high
