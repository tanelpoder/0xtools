#!/usr/bin/env python3
"""
Refactored histogram peek modal using extracted components.
Focuses on UI responsibilities only.
"""

import logging
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Static, DataTable, Button
from textual.screen import ModalScreen
from textual.binding import Binding
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import the extracted components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.histogram_data_provider import HistogramDataProvider
from core.heatmap_visualizer import HeatmapVisualizer
from core.histogram_formatter import HistogramFormatter
from core.time_utils import TimeUtils


class HistogramPeekModalRefactored(ModalScreen[None]):
    """Refactored modal for displaying histogram details with heatmap"""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
        Binding("space", "toggle_granularity", "Toggle time granularity"),
    ]
    
    CSS = """
    HistogramPeekModalRefactored {
        align: center middle;
    }
    
    #histogram-container {
        width: 90%;
        height: 90%;
        max-width: 120;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #histogram-header {
        height: 3;
        background: $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    
    #histogram-content {
        height: 1fr;
    }
    
    #histogram-table-container {
        height: 40%;
        border: solid $primary;
        margin-bottom: 1;
    }
    
    #heatmap-container {
        height: 60%;
        border: solid $accent;
        padding: 1;
    }
    
    #heatmap-header {
        height: 3;
        dock: top;
        text-align: center;
        background: $accent;
    }
    
    #heatmap-content {
        padding: 1;
        overflow: auto;
    }
    
    #close-button {
        dock: bottom;
        height: 3;
        margin-top: 1;
    }
    """
    
    def __init__(self,
                 column_key: str,
                 value: Any,
                 query_engine,
                 filters: Dict[str, Any],
                 group_cols: List[str],
                 time_range: tuple,
                 logger: Optional[logging.Logger] = None,
                 **kwargs):
        """Initialize the refactored histogram peek modal
        
        Args:
            column_key: Column name (e.g., 'SCLAT_HISTOGRAM')
            value: The histogram data string
            query_engine: QueryEngine instance
            filters: Current filters
            group_cols: GROUP BY columns
            time_range: (start_time, end_time) tuple
            logger: Optional logger
        """
        super().__init__(**kwargs)
        
        self.column_key = column_key
        self.value = value
        self.filters = filters
        self.group_cols = group_cols
        self.time_range = time_range
        self.logger = logger
        
        # Initialize components
        self.data_provider = HistogramDataProvider(query_engine, logger)
        self.heatmap_viz = HeatmapVisualizer(logger)
        self.formatter = HistogramFormatter(logger)
        self.time_utils = TimeUtils()
        
        # State
        self.current_granularity = "HH:MI"
        self.granularities = ["HH", "HH:MI", "HH:MI:S10"]
        self.granularity_index = 1
        
        # Cache for data
        self.histogram_data = None
        self.timeseries_data = None
    
    def compose(self) -> ComposeResult:
        """Compose the modal UI"""
        with Container(id="histogram-container"):
            # Header
            with Container(id="histogram-header"):
                yield Label(
                    f"Histogram Details: {self.column_key}",
                    id="histogram-title"
                )
            
            # Content area
            with ScrollableContainer(id="histogram-content"):
                # Data table for histogram breakdown
                with Container(id="histogram-table-container"):
                    yield DataTable(id="histogram-table")
                
                # Heatmap visualization
                with Container(id="heatmap-container"):
                    yield Label(
                        f"Time-Series Heatmap (Press SPACE to toggle granularity: {self.current_granularity})",
                        id="heatmap-header"
                    )
                    yield Static("Loading heatmap...", id="heatmap-content")
            
            # Close button
            yield Button("Close (ESC)", id="close-button", variant="primary")
    
    def on_mount(self) -> None:
        """Initialize when modal is mounted"""
        # Load and display histogram data
        self._load_histogram_data()
        # Load and display heatmap
        self._load_heatmap_data()
    
    def _load_histogram_data(self) -> None:
        """Load and display histogram table data"""
        try:
            # Parse histogram data
            self.histogram_data = self.formatter.parse_histogram_string(self.value)
            
            if not self.histogram_data:
                return
            
            # Format for table display
            table_data = self.formatter.format_histogram_table_data(self.histogram_data)
            
            # Populate the table
            table = self.query_one("#histogram-table", DataTable)
            
            # Add columns
            table.add_column("Latency Range", key="latency_range", width=15)
            table.add_column("Samples", key="samples", width=12)
            table.add_column("% Samples", key="pct_samples", width=10)
            table.add_column("Cumulative", key="cumulative", width=10)
            table.add_column("Est Time", key="est_time", width=12)
            table.add_column("% Time", key="pct_time", width=10)
            
            # Add rows
            for row_data in table_data:
                table.add_row(
                    row_data['latency_range'],
                    row_data['samples'],
                    row_data['pct_samples'],
                    row_data['cumulative'],
                    row_data['est_time'],
                    row_data['pct_time']
                )
            
            if self.logger:
                self.logger.info(f"Loaded {len(table_data)} rows into histogram table")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error loading histogram data: {e}")
    
    def _load_heatmap_data(self) -> None:
        """Load and display heatmap visualization"""
        try:
            # Fetch time-series data
            self.timeseries_data = self.data_provider.fetch_timeseries_data(
                column_key=self.column_key,
                filters=self.filters,
                group_cols=self.group_cols,
                time_range=self.time_range,
                granularity=self.current_granularity
            )
            
            if not self.timeseries_data:
                self.query_one("#heatmap-content", Static).update("No time-series data available")
                return
            
            # Generate heatmap
            heatmap_str = self.heatmap_viz.generate_heatmap(
                data=self.timeseries_data,
                granularity=self.current_granularity,
                palette="blue" if "SCLAT" in self.column_key else "red"
            )
            
            # Update display
            self.query_one("#heatmap-content", Static).update(heatmap_str)
            
            # Update header
            time_range_str = f"{self.time_range[0].strftime('%H:%M')} - {self.time_range[1].strftime('%H:%M')}"
            header_text = (
                f"Time-Series Heatmap ({time_range_str}) | "
                f"Granularity: {self.current_granularity} | "
                f"Press SPACE to toggle"
            )
            self.query_one("#heatmap-header", Label).update(header_text)
            
            if self.logger:
                self.logger.info(f"Generated heatmap with {len(self.timeseries_data)} time points")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error loading heatmap data: {e}")
            self.query_one("#heatmap-content", Static).update(f"Error generating heatmap: {str(e)}")
    
    def action_toggle_granularity(self) -> None:
        """Toggle time granularity for heatmap"""
        # Cycle through granularities
        self.granularity_index = (self.granularity_index + 1) % len(self.granularities)
        self.current_granularity = self.granularities[self.granularity_index]
        
        if self.logger:
            self.logger.info(f"Toggled granularity to: {self.current_granularity}")
        
        # Reload heatmap with new granularity
        self._load_heatmap_data()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events"""
        if event.button.id == "close-button":
            self.dismiss(None)