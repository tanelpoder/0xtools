#!/usr/bin/env python3
"""
Formatting utilities for xcapture data output.
Handles table formatting, CSV, JSON, and other output formats.
"""

import json
from typing import List, Dict, Any, Optional, Set
from decimal import Decimal


class TableFormatter:
    """Format data as aligned tables with psn-style formatting"""
    
    # State code to description mapping
    STATE_DESCRIPTIONS = {
        'R': 'Running (ON CPU)',
        'D': 'Disk (Uninterruptible)',
        'S': 'Sleeping',
        'T': 'Stopped',
        'Z': 'Zombie',
        'I': 'Idle',
        'X': 'Dead',
        'W': 'Paging'
    }
    
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
    
    def format_state(self, state_code: str) -> str:
        """Convert state codes to descriptive names"""
        return self.STATE_DESCRIPTIONS.get(state_code, state_code)
    
    def format_number_with_commas(self, num: float) -> str:
        """Format a number with comma separators"""
        return f"{int(num):,}"
    
    def format_latency_bucket(self, us: int) -> str:
        """Format latency bucket value"""
        try:
            us = int(us)
            if us >= 1000000:
                return f"{us/1000000:.0f}s"
            elif us >= 1000:
                return f"{us/1000:.0f}ms"
            else:
                return f"{us}μs"
        except:
            return str(us)
    
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
    
    def calculate_column_widths(self, data: List[Dict[str, Any]], 
                               columns: List[str], headers: Dict[str, str]) -> Dict[str, int]:
        """Calculate optimal column widths based on content"""
        widths = {}
        
        for col in columns:
            # Start with header width
            header = headers.get(col, col)
            widths[col] = len(header)
            
            # Check data widths
            for row in data:
                val = self._format_value(col, row.get(col))
                widths[col] = max(widths[col], len(val))
        
        # Apply minimum widths for numeric columns
        numeric_columns = self._identify_numeric_columns(data, columns)
        for col in numeric_columns:
            widths[col] = max(widths.get(col, 0), 8)
        
        return widths
    
    def _identify_numeric_columns(self, data: List[Dict[str, Any]], columns: List[str]) -> Set[str]:
        """Identify which columns contain numeric data"""
        numeric_columns = set()
        
        for col in columns:
            # Sample first few rows to determine if column is numeric
            for row in data[:10]:
                val = row.get(col)
                if val is not None and val != '-' and isinstance(val, (int, float, Decimal)):
                    numeric_columns.add(col)
                    break
        
        return numeric_columns
    
    def _format_value(self, column: str, value: Any) -> str:
        """Format a single value based on column type"""
        if value is None:
            return '-'
        
        # Special formatting by column name (case-insensitive)
        col_lower = column.lower()
        
        if col_lower == 'state':
            return self.format_state(str(value))
        elif col_lower == 'syscall' and str(value) == 'NULL':
            return '[running]'
        elif col_lower in ['io_lat_bkt_us', 'lat_bucket_us'] and value not in [None, '-']:
            return self.format_latency_bucket(value)
        elif 'histogram' in col_lower and col_lower not in ['histogram_viz', 'sclat_histogram_viz', 'iolat_histogram_viz']:
            # Format histogram data as unicode block visualization
            # (but not for _viz columns which are already formatted)
            if value and str(value) != '-':
                # Import visualizer here to avoid circular imports
                from .visualizers import ChartGenerator
                visualizer = ChartGenerator()
                # Use make_histogram_with_embedded_max if data has 4 fields per item
                hist_str = str(value)
                if ':' in hist_str:
                    first_item = hist_str.split(',')[0]
                    if len(first_item.split(':')) >= 4:
                        return visualizer.make_histogram_with_embedded_max(hist_str, width=26)
                    else:
                        return visualizer.make_histogram(hist_str, width=26)
                return ' ' * 26  # Empty histogram
            return ' ' * 26  # Empty histogram
        elif isinstance(value, (int, float, Decimal)):
            # Numeric formatting based on column name
            # Check for latency columns (including prefixed ones like sc.min_lat_us)
            if col_lower in ['min_lat_us', 'avg_lat_us', 'max_lat_us', 
                            'p50_us', 'p95_us', 'p99_us', 'p999_us'] or \
               col_lower.endswith('.min_lat_us') or col_lower.endswith('.avg_lat_us') or \
               col_lower.endswith('.max_lat_us') or col_lower.endswith('.p50_us') or \
               col_lower.endswith('.p95_us') or col_lower.endswith('.p99_us') or \
               col_lower.endswith('.p999_us') or '_us' in col_lower:
                # All microsecond latency columns get thousand separators
                return self.format_number_with_commas(value)
            elif col_lower in ['samples', 'total_samples', 'est_sc_cnt', 'count', 
                              'est_iorq_cnt', 'est_evt_cnt', 'tid', 'pid', 'tgid']:
                # Integer count columns get thousand separators
                return self.format_number_with_commas(int(value))
            elif col_lower in ['avg_lat_ms', 'est_iorq_time_s', 'est_evt_time_s']:
                # Float columns with thousand separators if >= 1000
                float_val = float(value)
                if float_val >= 1000:
                    return f"{float_val:,.2f}"
                return f"{float_val:.2f}"
            elif col_lower == 'avg_threads':
                # Average threads with thousand separators if >= 1000
                float_val = float(value)
                if float_val >= 1000:
                    return f"{float_val:,.2f}"
                return f"{float_val:.2f}"
            else:
                # All other numeric values get thousand separators if >= 1000
                if isinstance(value, int) or value == int(value):
                    int_val = int(value)
                    if int_val >= 1000:
                        return f"{int_val:,}"
                    return str(int_val)
                else:
                    float_val = float(value)
                    if float_val >= 1000:
                        return f"{float_val:,.0f}"
                    return f"{float_val:.0f}"
        else:
            return str(value)
    
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
        
        # Calculate column widths
        widths = self.calculate_column_widths(data, columns, headers)
        
        # Determine which columns contain numeric data
        numeric_columns = self._identify_numeric_columns(data, columns)
        
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
                val = self._format_value(col, row.get(col))
                
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
