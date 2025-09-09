#!/usr/bin/env python3
"""
Histogram formatting utilities.
Provides consistent formatting for histogram data across the application.
"""

from typing import List, Tuple, Dict, Any, Optional
import logging


class HistogramFormatter:
    """Formats histogram data for display"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the formatter
        
        Args:
            logger: Optional logger for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def format_latency_range(self, bucket_us: int) -> str:
        """Format microsecond bucket into human-readable range
        
        Args:
            bucket_us: Bucket value in microseconds
            
        Returns:
            Formatted string like "1-2ms" or "10-20s"
        """
        if bucket_us < 1000:
            # Microseconds
            next_bucket = bucket_us * 2 if bucket_us > 0 else 1
            return f"{bucket_us}-{next_bucket}μs"
        elif bucket_us < 1000000:
            # Milliseconds
            ms = bucket_us / 1000
            next_ms = (bucket_us * 2) / 1000
            if ms < 10:
                return f"{ms:.1f}-{next_ms:.1f}ms"
            else:
                return f"{ms:.0f}-{next_ms:.0f}ms"
        else:
            # Seconds
            s = bucket_us / 1000000
            next_s = (bucket_us * 2) / 1000000
            if s < 10:
                return f"{s:.1f}-{next_s:.1f}s"
            else:
                return f"{s:.0f}-{next_s:.0f}s"
    
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
        if seconds < 0.001:
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
    
    def format_histogram_chart(self, 
                               histogram_data: List[Tuple[int, int, float, float]], 
                               width: int = 40, 
                               show_percentage: bool = True) -> str:
        """Create a Unicode bar chart from histogram data
        
        Args:
            histogram_data: List of (bucket_us, count, est_time, global_max) tuples
            width: Width of the chart in characters
            show_percentage: Whether to show percentage labels
            
        Returns:
            Unicode bar chart string
        """
        if not histogram_data:
            return ""
        
        # Calculate totals
        total_samples = sum(count for _, count, _, _ in histogram_data)
        if total_samples == 0:
            return ""
        
        # Unicode block characters for bar chart
        blocks = ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
        
        lines = []
        max_count = max(count for _, count, _, _ in histogram_data)
        
        for bucket_us, count, _, _ in histogram_data:
            # Format label
            label = self.format_latency_range(bucket_us)
            
            # Calculate bar width
            bar_width = (count / max_count) * width if max_count > 0 else 0
            full_blocks = int(bar_width)
            partial = bar_width - full_blocks
            
            # Create bar
            bar = '█' * full_blocks
            if partial > 0:
                bar += blocks[min(int(partial * 8), 7)]
            
            # Add percentage if requested
            if show_percentage:
                pct = (count / total_samples * 100)
                line = f"{label:>12} {bar:<{width}} {pct:5.1f}%"
            else:
                line = f"{label:>12} {bar}"
            
            lines.append(line)
        
        return '\n'.join(lines)
    
    def create_unicode_bar_chart(self, 
                                 histogram_data: List[Tuple[int, int, float, float]],
                                 width: int = 30,
                                 show_percentage: bool = True) -> str:
        """Create a Unicode bar chart from histogram data
        
        Args:
            histogram_data: List of (bucket_us, count, est_time, global_max) tuples
            width: Width of the chart in characters
            show_percentage: Whether to show percentage labels
            
        Returns:
            Unicode bar chart string
        """
        if not histogram_data:
            return ""
        
        # Calculate totals
        total_samples = sum(count for _, count, _, _ in histogram_data)
        if total_samples == 0:
            return ""
        
        # Unicode block characters for bar chart
        blocks = ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
        
        lines = []
        max_count = max(count for _, count, _, _ in histogram_data)
        
        for bucket_us, count, _, _ in histogram_data:
            # Format label
            label = self.format_latency_range(bucket_us)
            
            # Calculate bar width
            bar_width = (count / max_count) * width if max_count > 0 else 0
            full_blocks = int(bar_width)
            partial = bar_width - full_blocks
            
            # Create bar
            bar = '█' * full_blocks
            if partial > 0:
                bar += blocks[min(int(partial * 8), 7)]
            
            # Add percentage if requested
            if show_percentage:
                pct = (count / total_samples * 100)
                line = f"{label:>12} {bar:<{width}} {pct:5.1f}%"
            else:
                line = f"{label:>12} {bar}"
            
            lines.append(line)
        
        return '\n'.join(lines)
    
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
        
        # Calculate percentiles (simplified - actual would be more complex)
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
