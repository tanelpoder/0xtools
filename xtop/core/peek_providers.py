#!/usr/bin/env python3
"""Data providers for TUI/CLI peek functionality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import logging

from .time_utils import TimeUtils

try:
    from typing import Protocol
except ImportError:  # Python <3.8 fallback (not expected, but keeps lint quiet)
    Protocol = object  # type: ignore[misc]


@dataclass
class HistogramTableRow:
    """Single row for histogram drill-down tables."""

    bucket_us: int
    count: int
    est_time_s: float
    est_events_per_s: float
    time_pct: float
    relative_time_ratio: float


@dataclass
class HistogramTableData:
    """Aggregated histogram data ready for rendering."""

    rows: List[HistogramTableRow]
    total_count: int
    total_time_s: float
    max_time_s: float


class _DuckDBCursor(Protocol):  # pragma: no cover - typing helper only
    description: Iterable[Any]

    def execute(self, query: str):
        ...

    def fetchall(self) -> List[Any]:
        ...


class HistogramPeekProvider:
    """Builds histogram data for peek modals using QueryBuilder."""

    def __init__(
        self,
        query_engine: Any,
        datadir: str | Path,
        query_builder: Optional[Any] = None,
    ) -> None:
        self.engine = query_engine
        self.datadir = Path(datadir)
        self._query_builder_override = query_builder
        self.logger = logging.getLogger("xtop.peek.histogram")

    def fetch_histogram_table(
        self,
        column_name: str,
        where_clause: str,
        low_time: Optional[datetime],
        high_time: Optional[datetime],
    ) -> HistogramTableData:
        builder = self._get_query_builder()
        histogram_type = self._determine_histogram_type(column_name)
        query = builder.build_histogram_drill_down_query(
            histogram_type=histogram_type,
            where_clause=where_clause,
            low_time=low_time,
            high_time=high_time,
            time_granularity=None,
        )

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Histogram table query:\n%s", query)

        conn = self.engine.data_source.connect()
        cursor = conn.execute(query)
        rows_raw = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        records = [
            {columns[idx]: row[idx] for idx in range(len(columns))}
            for row in rows_raw
        ]

        return self._records_to_table(records)

    def fetch_timeseries_histogram(
        self,
        column_name: str,
        where_clause: str,
        low_time: Optional[datetime],
        high_time: Optional[datetime],
        granularity: str,
    ) -> Optional[List[Dict[str, Any]]]:
        builder = self._get_query_builder()
        histogram_type = self._determine_histogram_type(column_name)
        query = builder.build_histogram_drill_down_query(
            histogram_type=histogram_type,
            where_clause=where_clause,
            low_time=low_time,
            high_time=high_time,
            time_granularity=granularity,
        )

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Histogram timeseries query (granularity=%s):\n%s", granularity, query)

        try:
            conn = self.engine.data_source.connect()
            cursor = conn.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            records = [
                {columns[idx]: row[idx] for idx in range(len(columns))}
                for row in rows
            ]

            return self._normalize_timeseries_records(records, granularity)
        except Exception as exc:  # pragma: no cover - protective log
            self.logger.error("Failed to execute timeseries histogram query: %s", exc)
            return None

    def _get_query_builder(self) -> Any:
        if self._query_builder_override is not None:
            return self._query_builder_override
        builder = getattr(self.engine, "query_builder", None)
        if builder is not None:
            return builder

        from .query_builder import QueryBuilder

        fragments_path = Path(__file__).parent.parent / "sql" / "fragments"
        builder = QueryBuilder(
            datadir=self.engine.data_source.datadir,
            fragments_path=fragments_path,
            use_materialized=getattr(self.engine, "use_materialized", False),
        )
        return builder

    @staticmethod
    def _determine_histogram_type(column_name: str) -> str:
        name = (column_name or "").lower()
        return "sclat" if "sclat" in name else "iolat"

    @staticmethod
    def _records_to_table(records: List[Dict[str, Any]]) -> HistogramTableData:
        if not records:
            return HistogramTableData([], 0, 0.0, 0.0)

        sorted_records = sorted(records, key=lambda rec: rec.get("bucket_us") or 0)
        total_count = sum(int(rec.get("count") or 0) for rec in sorted_records)
        total_time = sum(float(rec.get("est_time_s") or 0.0) for rec in sorted_records)
        max_time = max(float(rec.get("est_time_s") or 0.0) for rec in sorted_records)

        rows: List[HistogramTableRow] = []
        for rec in sorted_records:
            bucket_us = int(rec.get("bucket_us") or 0)
            count = int(rec.get("count") or 0)
            est_time = float(rec.get("est_time_s") or 0.0)
            est_events = HistogramPeekProvider._estimate_events_per_second(count, est_time)
            time_pct = (est_time / total_time * 100.0) if total_time > 0 else 0.0
            relative = (est_time / max_time) if max_time > 0 else 0.0
            rows.append(
                HistogramTableRow(
                    bucket_us=bucket_us,
                    count=count,
                    est_time_s=est_time,
                    est_events_per_s=est_events,
                    time_pct=time_pct,
                    relative_time_ratio=relative,
                )
            )

        return HistogramTableData(rows=rows, total_count=total_count, total_time_s=total_time, max_time_s=max_time)

    @staticmethod
    def _normalize_timeseries_records(
        records: List[Dict[str, Any]],
        granularity: str,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for rec in records:
            item = dict(rec)
            if granularity == TimeUtils.GRANULARITY_HOUR:
                item.setdefault("MI", "00")
            if granularity != TimeUtils.GRANULARITY_SECOND:
                item.pop("S10", None)
            normalized.append(item)
        return normalized

    @staticmethod
    def _estimate_events_per_second(count: int, est_time_s: float) -> float:
        if est_time_s <= 0:
            return 0.0
        return count / est_time_s


def parse_histogram_string(value: str, limit: int = 1000) -> List[tuple[int, int, float, float]]:
    """Parse compact histogram strings into tuples."""
    if not value or value == "-":
        return []

    buckets: List[tuple[int, int, float, float]] = []
    try:
        for index, item in enumerate(value.split(",")):
            if index >= limit:
                break
            parts = item.split(":")
            if len(parts) < 4:
                continue
            bucket = int(parts[0])
            count = int(parts[1])
            est_time = float(parts[2])
            global_max = float(parts[3])
            if count > 0 or est_time > 0:
                buckets.append((bucket, count, est_time, global_max))
    except Exception:
        return []

    return sorted(buckets, key=lambda item: item[0])


def parse_stack_trace(value: Optional[str]) -> List[str]:
    """Split stack trace strings into frames."""
    if not value or value == "-":
        return []
    return [frame.strip() for frame in value.split(";") if frame.strip()]


def format_latency_bucket(bucket_us: int) -> str:
    """Render a human-readable latency range for histogram buckets."""
    def _humanize(us: int) -> str:
        if us >= 1_000_000:
            return f"{us / 1_000_000:.0f}s"
        if us >= 1_000:
            return f"{us / 1_000:.0f}ms"
        return f"{us}μs"

    next_bucket = bucket_us * 2 if bucket_us > 0 else bucket_us
    return f"{_humanize(bucket_us)}-{_humanize(next_bucket)}"
