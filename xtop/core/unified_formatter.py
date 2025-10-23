#!/usr/bin/env python3
"""
Unified formatter module that consolidates all formatting functionality.
Combines TableFormatter, HistogramFormatter, and other formatting utilities.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from core.display import compute_column_layout, format_value as display_format_value

class UnifiedFormatter:
    """Unified formatter that consolidates all formatting functionality"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the unified formatter
        
        Args:
            logger: Optional logger for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
    
    # ==================== Column Formatting ====================
    
    def format_column_name(self, name: str) -> str:
        """Format column name for display
        
        Args:
            name: Raw column name
            
        Returns:
            Formatted column name
        """
        if not name:
            return ""
        
        # Map common column names to display formats
        format_map = {
            'comm': 'Command',
            'pid': 'PID',
            'tid': 'TID',
            'cpu': 'CPU',
            'avg_threads': 'Avg Thr',
            'samples': 'Samples',
            'pct': 'Percent',
            'state': 'State',
            'sclat_p50': 'SC P50',
            'sclat_p95': 'SC P95',
            'sclat_p99': 'SC P99',
            'iolat_p50': 'IO P50',
            'iolat_p95': 'IO P95',
            'iolat_p99': 'IO P99',
            'kstack_current_func': 'Kernel Func',
            'ustack_current_func': 'User Func',
            'filenamesum': 'File Pattern',
            'username': 'User',
            'exe': 'Executable',
            'connection': 'Connection',
            'remote_addr': 'Remote Addr',
            'local_port': 'Local Port',
            'device': 'Device',
            'sclat_histogram': 'SC Latency',
            'iolat_histogram': 'IO Latency',
            'time_bar': '',  # No header for time bar
        }
        
        # Check if we have a mapping
        name_lower = name.lower()
        if name_lower in format_map:
            return format_map[name_lower]
        
        # Check for time columns
        if name_lower in ['yyyy', 'mm', 'dd', 'hh', 'mi', 'ss', 's10']:
            return name.lower()
        
        # Title case for other columns
        return name.replace('_', ' ').title()
    
    def format_column_width(self, name: str, data: List[Any]) -> int:
        """Calculate appropriate column width

        Args:
            name: Column name
            data: Column data

        Returns:
            Column width in characters
        """
        header = self.format_column_name(name)
        rows = [{name: value} for value in data]
        layout = compute_column_layout([name], rows, headers={name: header}, sample_limit=len(rows) or 1)
        width = layout.widths.get(name, len(header))
        width = max(width, len(header) + 2)

        name_lower = name.lower()
        if name_lower in ['comm', 'exe', 'username']:
            width = min(width, 20)
        elif name_lower in ['filenamesum', 'connection']:
            width = min(width, 30)
        elif name_lower in ['kstack_current_func', 'ustack_current_func']:
            width = min(width, 40)
        elif 'histogram' in name_lower:
            width = 30
        elif name_lower == 'time_bar':
            width = 12
        else:
            width = min(width, 15)

        return width
    
    def reorder_columns_samples_first(self, columns: List[str]) -> List[str]:
        """Reorder columns to put samples-related columns first
        
        Args:
            columns: List of column names
            
        Returns:
            Reordered list
        """
        # Define priority order
        priority = {
            'samples': 1,
            'avg_threads': 2,
            'avg_thr': 2,
            'time_bar': 3,
            'pct': 4,
            'percent': 4,
        }
        
        def get_priority(col: str):
            col_lower = col.lower()
            for key, pri in priority.items():
                if key in col_lower:
                    return pri
            return 100  # Default priority for other columns
        
        # Separate priority columns from others
        priority_cols = []
        other_cols = []
        
        for col in columns:
            if get_priority(col) < 100:
                priority_cols.append(col)
            else:
                other_cols.append(col)
        
        # Sort priority columns by their priority
        priority_cols.sort(key=get_priority)
        
        # Return priority columns first, then others
        return priority_cols + other_cols
    
    # ==================== Value Formatting ====================
    
    def format_value(self, value: Any, column: str = "") -> str:
        """Format a value for display based on its type and column
        
        Args:
            value: Value to format
            column: Column name for context
            
        Returns:
            Formatted string
        """
        if value is None:
            return "-"
        
        column_lower = column.lower()

        if column:
            formatted = display_format_value(column, value)
            if formatted != str(value) or value is None:
                return formatted

        # Numeric formatting
        if isinstance(value, (int, float)):
            if 'pct' in column_lower or 'percent' in column_lower:
                return self.format_percentage(value)
            elif column_lower == 'avg_threads':
                return f"{float(value):.2f}"
            elif column_lower in ['samples', 'count', 'total_samples']:
                return self.format_count(int(value))
            elif 'time' in column_lower or 'latency' in column_lower or '_us' in column_lower:
                # For latency values in microseconds
                if '_us' in column_lower:
                    return f"{value:,.0f}" if value >= 1000 else f"{value:.1f}"
                return self.format_time(value)
            elif isinstance(value, float):
                # Apply thousand separators to all floats
                if value >= 1000:
                    return f"{value:,.2f}"
                return f"{value:.2f}"
            else:
                # Apply thousand separators to all integers
                if value >= 1000:
                    return f"{value:,}"
                return str(value)
        
        # String values
        return str(value)
    
    def format_count(self, count: int) -> str:
        """Format count with thousands separator
        
        Args:
            count: Number to format
            
        Returns:
            Formatted string with commas
        """
        return f"{count:,}"
    
    def format_percentage(self, value: float, decimals: int = 1) -> str:
        """Format percentage value
        
        Args:
            value: Percentage value (0-100)
            decimals: Number of decimal places
            
        Returns:
            Formatted percentage string
        """
        return f"{value:.{decimals}f}%"
    
    def format_time(self, seconds: float) -> str:
        """Format time in seconds to human-readable format
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string
        """
        if seconds < 0.000001:
            return f"{seconds * 1000000000:.0f}ns"
        elif seconds < 0.001:
            return f"{seconds * 1000000:.0f}μs"
        elif seconds < 1:
            return f"{seconds * 1000:.1f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"
    
    # ==================== Latency Formatting ====================
    
    def format_latency_range(self, bucket_us: int) -> str:
        """Format microsecond bucket into human-readable range
        
        Args:
            bucket_us: Bucket value in microseconds
            
        Returns:
            Formatted string like "1-2ms" or "10-20s"
        """
        if bucket_us <= 0:
            return "0μs"

        low_us = max(bucket_us // 2, 1)
        high_us = bucket_us

        if high_us < 1000:
            return f"{low_us}-{high_us}μs"

        low_ms = low_us / 1000
        high_ms = high_us / 1000
        if high_us < 1_000_000:
            if high_ms < 10:
                return f"{low_ms:.1f}-{high_ms:.1f}ms"
            return f"{low_ms:.0f}-{high_ms:.0f}ms"

        low_s = low_us / 1_000_000
        high_s = high_us / 1_000_000
        if high_s < 10:
            return f"{low_s:.1f}-{high_s:.1f}s"
        return f"{low_s:.0f}-{high_s:.0f}s"
    
    def format_latency_us(self, microseconds: float) -> str:
        """Format microseconds to human-readable format
        
        Args:
            microseconds: Latency in microseconds
            
        Returns:
            Formatted string
        """
        if microseconds < 1000:
            return f"{microseconds:.0f}μs"
        elif microseconds < 1000000:
            return f"{microseconds/1000:.1f}ms"
        else:
            return f"{microseconds/1000000:.2f}s"
    
    # ==================== Histogram Formatting ====================
    
    def parse_histogram_string(self, value: str) -> List[Tuple[int, int, float, float]]:
        """Parse histogram string into structured data
        
        Args:
            value: Histogram string in format "bucket:count:time:global_max,..."
            
        Returns:
            List of tuples (bucket_us, count, estimated_time, global_max)
        """
        if not value or value == '-':
            return []
        
        histogram_data = []
        
        # Parse the histogram string
        buckets = value.split(',')
        for bucket in buckets:
            if bucket:
                try:
                    parts = bucket.split(':')
                    if len(parts) >= 4:
                        bucket_us = int(parts[0])
                        count = int(parts[1])
                        est_time = float(parts[2])
                        global_max = float(parts[3])
                        histogram_data.append((bucket_us, count, est_time, global_max))
                except (ValueError, IndexError) as e:
                    if self.logger:
                        self.logger.warning(f"Failed to parse histogram bucket: {bucket}, error: {e}")
        
        return histogram_data
    
    def format_histogram_table_data(self, 
                                   histogram_data: List[Tuple[int, int, float, float]]) -> List[Dict[str, str]]:
        """Format histogram data for table display
        
        Args:
            histogram_data: List of (bucket_us, count, est_time, global_max) tuples
            
        Returns:
            List of formatted dictionaries for table rows
        """
        if not histogram_data:
            return []
        
        # Calculate totals
        total_samples = sum(count for _, count, _, _ in histogram_data)
        total_time = sum(est_time for _, _, est_time, _ in histogram_data)
        
        # Format rows
        rows = []
        cumulative_pct = 0.0
        
        for bucket_us, count, est_time, global_max in histogram_data:
            pct_samples = (count / total_samples * 100) if total_samples > 0 else 0
            cumulative_pct += pct_samples
            pct_time = (est_time / total_time * 100) if total_time > 0 else 0
            
            rows.append({
                'latency_range': self.format_latency_range(bucket_us),
                'samples': self.format_count(count),
                'pct_samples': self.format_percentage(pct_samples),
                'cumulative': self.format_percentage(cumulative_pct),
                'est_time': self.format_time(est_time),
                'pct_time': self.format_percentage(pct_time)
            })
        
        return rows
    
    def format_histogram_summary(self, histogram_data: List[Tuple[int, int, float, float]]) -> str:
        """Format a summary of histogram statistics
        
        Args:
            histogram_data: List of histogram tuples
            
        Returns:
            Formatted summary string
        """
        if not histogram_data:
            return "No histogram data available"
        
        total_samples = sum(count for _, count, _, _ in histogram_data)
        total_time = sum(est_time for _, _, est_time, _ in histogram_data)
        bucket_count = len(histogram_data)
        
        # Find min and max latencies
        min_bucket = min(bucket_us for bucket_us, _, _, _ in histogram_data)
        max_bucket = max(bucket_us for bucket_us, _, _, _ in histogram_data)
        
        # Calculate percentiles (simplified)
        cumulative = 0
        p50_bucket = p95_bucket = p99_bucket = max_bucket
        
        for bucket_us, count, _, _ in histogram_data:
            cumulative += count
            pct = (cumulative / total_samples * 100)
            
            if pct >= 50 and p50_bucket == max_bucket:
                p50_bucket = bucket_us
            if pct >= 95 and p95_bucket == max_bucket:
                p95_bucket = bucket_us
            if pct >= 99 and p99_bucket == max_bucket:
                p99_bucket = bucket_us
        
        summary = [
            f"Total Samples: {self.format_count(total_samples)}",
            f"Total Time: {self.format_time(total_time)}",
            f"Buckets: {bucket_count}",
            f"Range: {self.format_latency_range(min_bucket)} to {self.format_latency_range(max_bucket)}",
            f"P50: {self.format_latency_range(p50_bucket)}",
            f"P95: {self.format_latency_range(p95_bucket)}",
            f"P99: {self.format_latency_range(p99_bucket)}"
        ]
        
        return " | ".join(summary)
