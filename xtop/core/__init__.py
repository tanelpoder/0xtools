#!/usr/bin/env python3
"""
Core module for xtop - provides data access, query processing, and formatting utilities.
"""

from .data_source import XCaptureDataSource
from .query_engine import QueryEngine, QueryParams, QueryResult
from .formatters import TableFormatter
from .visualizers import ChartGenerator
from .navigation import NavigationState, NavigationFrame
from .peek_providers import (
    HistogramPeekProvider,
    HistogramTableData,
    HistogramTableRow,
    parse_histogram_string,
    parse_stack_trace,
    format_latency_bucket,
)
from .heatmap import LatencyHeatmap, HeatmapConfig

__all__ = [
    'XCaptureDataSource',
    'QueryEngine',
    'QueryParams',
    'QueryResult',
    'TableFormatter',
    'ChartGenerator',
    'NavigationState',
    'NavigationFrame',
    'HistogramPeekProvider',
    'HistogramTableData',
    'HistogramTableRow',
    'parse_histogram_string',
    'parse_stack_trace',
    'format_latency_bucket',
    'LatencyHeatmap',
    'HeatmapConfig'
]

__version__ = '1.0'
