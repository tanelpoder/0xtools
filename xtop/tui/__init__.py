#!/usr/bin/env python3
"""
TUI module for xtop - provides interactive terminal UI components
"""

from .cell_peek_modal import CellPeekModal, HistogramPeekModal

__all__ = [
    'CellPeekModal',
    'HistogramPeekModal'
]

__version__ = '1.0'