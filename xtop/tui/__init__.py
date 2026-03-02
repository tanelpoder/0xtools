#!/usr/bin/env python3
"""
TUI module for xtop - provides interactive terminal UI components
"""

from .cell_peek_modal import CellPeekModal, HistogramPeekModal
from .value_filter_modal import ValueFilterModal

__all__ = [
    'CellPeekModal',
    'HistogramPeekModal',
    'ValueFilterModal'
]

__version__ = '1.0'
