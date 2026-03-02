"""Shared formatting helpers for xtop display layers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, MutableMapping, Optional, Sequence, Set
import math

STATE_DESCRIPTIONS = {
    "R": "Running (ON CPU)",
    "D": "Disk (Uninterruptible)",
    "S": "Sleeping",
    "T": "Stopped",
    "Z": "Zombie",
    "I": "Idle",
    "X": "Dead",
    "W": "Paging",
}

_NUMERIC_COLUMN_NAMES = {
    "est_sc_cnt",
    "min_lat_us",
    "avg_lat_us",
    "max_lat_us",
    "p50_us",
    "p95_us",
    "p99_us",
    "p999_us",
    "samples",
    "total_samples",
    "avg_threads",
    "est_iorq_cnt",
    "avg_lat_ms",
    "est_iorq_time_s",
    "est_evt_time_s",
}

_NUMERIC_SUFFIXES = ("_us", "_ms", "_cnt", "_s")

_HISTOGRAM_VIZ_COLUMNS = {
    "histogram_viz",
    "sclat_histogram_viz",
    "iolat_histogram_viz",
}

BLOCK_CHARACTERS = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")

@dataclass
class ColumnLayout:
    """Container for column layout information."""

    widths: Dict[str, int]
    numeric_columns: Set[str]


_chart_generator = None  # Lazy-initialised ChartGenerator instance


def _format_latency_bucket(microseconds: Any) -> str:
    try:
        us_val = int(microseconds)
    except Exception:
        return str(microseconds)

    if us_val >= 1_000_000:
        return f"{us_val / 1_000_000:.0f}s"
    if us_val >= 1_000:
        return f"{us_val / 1_000:.0f}ms"
    return f"{us_val}μs"


def _format_number_with_commas(value: float) -> str:
    return f"{int(value):,}"


def format_value(column: str, value: Any) -> str:
    """Format a single value based on column context."""
    if value is None:
        return "-"

    column_lower = (column or "").lower()

    if column_lower == "state":
        return STATE_DESCRIPTIONS.get(str(value), str(value))

    if column_lower == "syscall" and str(value) == "NULL":
        return "[running]"

    if column_lower in {"io_lat_bkt_us", "lat_bucket_us"} and value not in (None, "-"):
        return _format_latency_bucket(value)

    if "histogram" in column_lower and column_lower not in _HISTOGRAM_VIZ_COLUMNS:
        if value and str(value) != "-":
            global _chart_generator
            if _chart_generator is None:
                from core.visualizers import ChartGenerator  # Local import to avoid cycles

                _chart_generator = ChartGenerator()
            hist_str = str(value)
            if ":" in hist_str:
                first_item = hist_str.split(",", 1)[0]
                if len(first_item.split(":")) >= 4:
                    return _chart_generator.make_histogram_with_embedded_max(hist_str, width=26)
                return _chart_generator.make_histogram(hist_str, width=26)
            return " " * 26
        return " " * 26

    if isinstance(value, (int, float, Decimal)):
        if column_lower == "avg_threads":
            return f"{float(value):.2f}"

        if (
            column_lower in _NUMERIC_COLUMN_NAMES
            or column_lower.endswith(".min_lat_us")
            or column_lower.endswith(".avg_lat_us")
            or column_lower.endswith(".max_lat_us")
            or column_lower.endswith(".p50_us")
            or column_lower.endswith(".p95_us")
            or column_lower.endswith(".p99_us")
            or column_lower.endswith(".p999_us")
            or "_us" in column_lower
        ):
            return _format_number_with_commas(value)

        if column_lower in {"avg_lat_ms", "est_iorq_time_s", "est_evt_time_s"}:
            number = float(value)
            if number >= 1000:
                return f"{number:,.0f}"
            return f"{number:.0f}"

        if column_lower in {"samples", "total_samples", "est_sc_cnt", "count", "est_iorq_cnt", "est_evt_cnt", "tid", "pid", "tgid"}:
            return _format_number_with_commas(value)

        if isinstance(value, float):
            if value >= 1000:
                return f"{value:,.0f}"
            return f"{value:.0f}"

    return str(value)


def _looks_numeric(column_lower: str) -> bool:
    if not column_lower:
        return False
    if column_lower in _NUMERIC_COLUMN_NAMES:
        return True
    return column_lower.endswith(_NUMERIC_SUFFIXES)


def _has_numeric_values(column: str, rows: Sequence[MutableMapping[str, Any]], sample_limit: int) -> bool:
    for row in rows[:sample_limit]:
        value = row.get(column)
        if isinstance(value, (int, float, Decimal)):
            return True
    return False


def compute_column_layout(
    columns: Sequence[str],
    data: Sequence[MutableMapping[str, Any]],
    headers: Optional[Dict[str, str]] = None,
    *,
    sample_limit: int = 100,
    text_cap: int = 50,
    extra_info_cap: int = 60,
    numeric_min_width: int = 8,
) -> ColumnLayout:
    """Compute column widths and numeric alignment info for display layers."""

    resolved_headers = headers or {}
    widths: Dict[str, int] = {}
    numeric_columns: Set[str] = set()

    for col in columns:
        col_lower = (col or "").lower()
        if _looks_numeric(col_lower) or _has_numeric_values(col, data, sample_limit=10):
            numeric_columns.add(col)

        header = resolved_headers.get(col, col)
        max_width = len(header)

        for row in data[:sample_limit]:
            formatted = format_value(col, row.get(col))
            max_width = max(max_width, len(formatted))

        width_base = max(len(header), max_width + 1)

        if col in numeric_columns:
            widths[col] = max(width_base, numeric_min_width)
        else:
            cap = extra_info_cap if col_lower == "extra_info" else text_cap
            widths[col] = max(len(header), min(width_base, cap))

    return ColumnLayout(widths=widths, numeric_columns=numeric_columns)


def render_block_sparkline(values: Sequence[float], *, max_chars: int = 60) -> str:
    """Render a unicode sparkline using vertical block characters."""

    if not values:
        return ""

    filtered: List[float] = [float(v) for v in values if v is not None]
    if not filtered:
        return ""

    if max_chars and len(filtered) > max_chars:
        stride = math.ceil(len(filtered) / max_chars)
        reduced: List[float] = []
        for index in range(0, len(filtered), stride):
            chunk = filtered[index:index + stride]
            reduced.append(sum(chunk) / len(chunk))
        filtered = reduced

    max_value = max(filtered)
    if max_value <= 0:
        return ""

    scale = len(BLOCK_CHARACTERS) - 1
    blocks: List[str] = []

    for value in filtered:
        if value <= 0:
            blocks.append(BLOCK_CHARACTERS[0])
            continue
        ratio = min(1.0, value / max_value)
        idx = min(scale, max(0, int(round(ratio * scale))))
        blocks.append(BLOCK_CHARACTERS[idx])

    return "".join(blocks)
