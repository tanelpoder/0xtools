#!/usr/bin/env python3
"""
Formatting utilities for xcapture data output.
Handles table formatting, CSV, JSON, and other output formats.
"""

import json
from typing import List, Dict, Any, Optional
from decimal import Decimal

from core.display import ColumnLayout, compute_column_layout, format_value as display_format_value


class TableFormatter:
    """Format data as aligned tables with psn-style formatting"""
    
    # Special column name mappings (lowercase key -> display name)
    COLUMN_HEADERS = {
        'username': 'user',
        'exe': 'exe',
        'comm': 'comm',
        'comm2': 'comm',
        'state': 'state',
        'syscall': 'syscall',
        'filename': 'filename',
        'extra_info': 'extra_info',
        'connection': 'connection',
        'devname': 'device',
        'dev_name': 'device',
        'syscall_name': 'syscall',
        'sclat_histogram': 'latency_histogram',
        'histogram_viz': '<1us__32us_1ms__32ms_1s_8∞',
        'sclat_histogram_viz': '<1us__32us_1ms__32ms_1s_8∞',
        'iolat_histogram_viz': '<1us__32us_1ms__32ms_1s_8∞',
        'total_samples': 'samples',
        'avg_threads': 'avg_thr',
        'seconds': 'seconds',
        'est_iorq_cnt': 'ios/s',
        'est_evt_cnt': 'calls/s',
        'est_iorq_time_s': 'io_time_s',
        'est_evt_time_s': 'time_s',
        'io_lat_bkt_us': 'latency_us',
        'lat_bucket_us': 'latency_us',
        'avg_lat_ms': 'avg_lat_ms',
        'avg_lat_us': 'avg_lat_us',
        'min_lat_us': 'min_lat_us',
        'max_lat_us': 'max_lat_us',
        'total_ms': 'total_ms',
        'activity': 'time_bar',
        'distribution': 'time_bar',
        'time_bar': 'time_bar',
        'p50_us': 'p50_us',
        'p95_us': 'p95_us',
        'p99_us': 'p99_us',
        'p999_us': 'p999_us',
        'est_sc_cnt': 'est_calls_s',
        'samples': 'samples',
        # Time bucket columns
        'yyyy': 'year',
        'mm': 'month',
        'dd': 'day', 
        'hh': 'hour',
        'mi': 'min',
        'ss': 'sec',
        's10': 's10'
    }
    
    def __init__(self):
        """Initialize formatter"""
        pass
    
    def generate_headers(self, columns: List[str]) -> Dict[str, str]:
        """Generate headers dictionary dynamically based on available columns"""
        headers = {}
        
        for col in columns:
            col_lower = col.lower()
            if col_lower in self.COLUMN_HEADERS:
                headers[col] = self.COLUMN_HEADERS[col_lower]
            else:
                # Use lowercase version of column name as default
                headers[col] = col_lower
        
        return headers
    
    def calculate_column_layout(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
        headers: Dict[str, str],
    ) -> ColumnLayout:
        """Compute column layout metadata shared across display layers."""

        return compute_column_layout(columns, data, headers)
    
    def reorder_columns_samples_first(self, columns: List[str]) -> List[str]:
        """Reorder columns to put important metrics first"""
        # Define the exact order for the first columns
        first_cols = ['samples', 'total_samples', 'avg_threads', 'time_bar']
        early_cols = ['est_sc_cnt', 'est_iorq_cnt', 'est_evt_cnt']
        percentile_cols = ['p50_us', 'p95_us', 'p99_us', 'p999_us']
        
        # Find which columns exist
        reordered = []
        
        # Add first columns in order if they exist
        for col in first_cols:
            if col in columns:
                reordered.append(col)
        
        # Separate remaining columns
        early_metric_cols = []
        percentile_metric_cols = []
        other_cols = []
        
        for col in columns:
            if col in reordered:
                continue
            elif col in early_cols:
                early_metric_cols.append(col)
            elif col in percentile_cols:
                percentile_metric_cols.append(col)
            else:
                other_cols.append(col)
        
        # Return with proper ordering
        return reordered + early_metric_cols + other_cols + percentile_metric_cols
    
    def format_table(self, data: List[Dict[str, Any]], columns: List[str],
                    headers: Optional[Dict[str, str]] = None,
                    title: str = "Results",
                    reorder: bool = True,
                    right_align_all: bool = False) -> str:
        """Format results as aligned table with psn-style formatting"""
        if not data:
            return "No data found for the specified criteria.\n"
        
        if headers is None:
            headers = self.generate_headers(columns)
        
        # Reorder columns unless explicitly disabled
        if reorder:
            columns = self.reorder_columns_samples_first(columns)
        
        # Calculate column layout (widths + numeric alignment)
        layout = self.calculate_column_layout(data, columns, headers)
        widths = layout.widths
        numeric_columns = layout.numeric_columns
        
        # Build output
        output = []
        
        # Section header
        title_line = f"═══ {title} "
        title_line += "═" * (sum(widths.values()) + len(columns) * 3 - len(title_line))
        output.append(title_line)
        output.append("")
        
        # Column headers
        header_parts = []
        for col in columns:
            header = headers.get(col, col)
            if right_align_all or (col in numeric_columns):
                # Right-align numeric headers
                header_parts.append(header.rjust(widths[col]))
            else:
                header_parts.append(header.ljust(widths[col]))
        output.append(" │ ".join(header_parts))
        
        # Separator line
        sep_parts = []
        for col in columns:
            sep_parts.append("─" * widths[col])
        output.append("─┼─".join(sep_parts))
        
        # Data rows
        for row in data:
            row_parts = []
            for col in columns:
                val = display_format_value(col, row.get(col))
                
                # Align based on whether column contains numeric data
                if right_align_all or (col in numeric_columns):
                    row_parts.append(val.rjust(widths[col]))
                else:
                    row_parts.append(val.ljust(widths[col]))
            
            output.append(" │ ".join(row_parts))
        
        output.append("")
        return "\n".join(output)
    
    def format_csv(self, data: List[Dict[str, Any]], columns: List[str]) -> str:
        """Format as CSV"""
        lines = [','.join(columns)]
        
        for row in data:
            values = []
            for col in columns:
                val = row.get(col, '')
                # Escape quotes in CSV
                if isinstance(val, str) and ',' in val:
                    val = f'"{val}"'
                values.append(str(val))
            lines.append(','.join(values))
        
        return '\n'.join(lines)
    
    def format_json(self, data: List[Dict[str, Any]]) -> str:
        """Format as JSON"""
        # Convert Decimal values to float for JSON serialization
        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError
        
        return json.dumps(data, indent=2, default=decimal_default)
