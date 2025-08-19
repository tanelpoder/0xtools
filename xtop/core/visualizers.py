#!/usr/bin/env python3
"""
Visualization utilities for xcapture data.
Generates Unicode charts, histograms, and other visual elements.
"""

from typing import List, Dict, Optional


class ChartGenerator:
    """Generate Unicode charts and histograms"""
    
    # Unicode block characters for horizontal bar charts
    BLOCK_CHARS = ['', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
    
    # Vertical Unicode block characters for histograms
    VBLOCK_CHARS = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    def __init__(self):
        """Initialize chart generator"""
        pass
    
    def make_bar(self, value: float, max_value: float, width: int = 15) -> str:
        """
        Create a horizontal bar chart for a value.
        
        Args:
            value: The value to represent
            max_value: The maximum value in the dataset
            width: Width of the bar in characters
            
        Returns:
            Unicode bar string
        """
        if max_value == 0:
            return ''
        
        ratio = value / max_value
        full_blocks = int(ratio * width)
        remainder = (ratio * width) - full_blocks
        
        bar = self.BLOCK_CHARS[-1] * full_blocks
        
        # Add partial block
        if remainder > 0:
            partial_idx = int(remainder * (len(self.BLOCK_CHARS) - 1))
            if partial_idx > 0:
                bar += self.BLOCK_CHARS[partial_idx]
        
        return bar
    
    def parse_histogram(self, hist_str: str) -> Dict[int, int]:
        """
        Parse histogram string format 'bucket:count,bucket:count' into dict.
        
        Args:
            hist_str: Histogram string
            
        Returns:
            Dict mapping bucket values to counts
        """
        if not hist_str or hist_str == '-':
            return {}
        
        hist_dict = {}
        try:
            for pair in hist_str.split(','):
                if ':' in pair:
                    bucket, count = pair.split(':')[:2]  # Take only first two parts
                    # Handle float notation (e.g., "1048576.0")
                    hist_dict[int(float(bucket))] = int(float(count))
        except:
            return {}
        
        return hist_dict
    
    def make_histogram(self, hist_str: str, width: int = 26, 
                      use_time_based: bool = True) -> str:
        """
        Create vertical histogram visualization from bucket:count:time_s string.
        
        Args:
            hist_str: Histogram data string
            width: Width of histogram in characters
            use_time_based: Whether to use time-based normalization
            
        Returns:
            Unicode histogram string
        """
        if not hist_str or hist_str == '-':
            return ' ' * width
        
        # Check if we have time-based data (3+ fields per item)
        if use_time_based and ':' in hist_str:
            first_item = hist_str.split(',')[0]
            if len(first_item.split(':')) >= 3:
                return self._make_histogram_from_detail(hist_str, width)
        
        # Fallback to simple count-based histogram
        return self._make_histogram_from_counts(hist_str, width)
    
    def _make_histogram_from_detail(self, detail_str: str, width: int = 26) -> str:
        """Create histogram from detailed bucket info (bucket:count:est_time_s)"""
        if not detail_str:
            return ' ' * width
        
        # Collect time spent in each bucket
        time_data = {}
        try:
            for item in detail_str.split(','):
                parts = item.split(':')
                if len(parts) >= 3:
                    bucket = int(parts[0])
                    # Use estimated time (3rd field)
                    est_time = float(parts[2])
                    time_data[bucket] = est_time
        except:
            return ' ' * width
        
        # Calculate total time from all buckets
        total_time = sum(time_data.values())
        
        # Normalize each bucket's time against total time
        buckets_data = {}
        if total_time > 0:
            for bucket, time_spent in time_data.items():
                buckets_data[bucket] = time_spent / total_time
        else:
            buckets_data = {k: 0 for k in time_data}
        
        return self._create_histogram_display(buckets_data, width)
    
    def _make_histogram_from_counts(self, hist_str: str, width: int = 26) -> str:
        """Create histogram from simple bucket:count format"""
        hist_dict = self.parse_histogram(hist_str)
        if not hist_dict:
            return ' ' * width
        
        # Normalize counts
        total_count = sum(hist_dict.values())
        if total_count > 0:
            buckets_data = {k: v/total_count for k, v in hist_dict.items()}
        else:
            buckets_data = {k: 0 for k in hist_dict}
        
        return self._create_histogram_display(buckets_data, width)
    
    def _create_histogram_display(self, buckets_data: Dict[int, float], 
                                 width: int = 26) -> str:
        """Create the actual histogram display string"""
        # Create display buckets
        display_buckets = []
        
        # First 25 buckets (2^0 to 2^24)
        for i in range(25):
            power = 2 ** i
            display_buckets.append(buckets_data.get(power, 0))
        
        # Last bucket aggregates everything > 2^24 (> 16.78 seconds)
        last_bucket_ratio = 0
        for bucket, ratio in buckets_data.items():
            if bucket > 2**24:
                last_bucket_ratio += ratio
        display_buckets.append(last_bucket_ratio)
        
        # Add padding to match header length (26 characters)
        while len(display_buckets) < width:
            display_buckets.append(0)
        
        # Create histogram string
        hist_chars = []
        for ratio in display_buckets[:width]:
            if ratio <= 0:
                hist_chars.append(' ')
            else:
                # Scale ratio (0-1) to character height (0-8)
                height = int(ratio * 8)
                if height == 0 and ratio > 0:  # If ratio is very small but non-zero
                    height = 1
                height = min(height, 8)  # Cap at 8
                hist_chars.append(self.VBLOCK_CHARS[height])
        
        return ''.join(hist_chars)
    
    def make_histogram_with_embedded_max(self, hist_str: str, width: int = 26) -> str:
        """
        Create histogram with global max embedded in the data.
        Format: bucket:count:time:global_max
        
        Args:
            hist_str: Histogram data with embedded global max
            width: Width of histogram
            
        Returns:
            Unicode histogram string
        """
        if not hist_str:
            return ' ' * width
        
        # Parse bucket data and extract global max
        buckets_data = {}
        max_bucket_time = 0
        try:
            for item in hist_str.split(','):
                parts = item.split(':')
                if len(parts) >= 4:
                    bucket = int(parts[0])
                    est_time = float(parts[2])
                    global_max = float(parts[3])
                    buckets_data[bucket] = est_time
                    max_bucket_time = global_max  # Same for all buckets
        except:
            return ' ' * width
        
        if max_bucket_time <= 0:
            return ' ' * width
        
        # Create display buckets with global normalization
        display_buckets = []
        
        # First 25 buckets (2^0 to 2^24)
        for i in range(25):
            power = 2 ** i
            time_val = buckets_data.get(power, 0)
            display_buckets.append(time_val)
        
        # Last bucket aggregates everything > 2^24
        last_bucket_time = 0
        for bucket, time_val in buckets_data.items():
            if bucket > 2**24:
                last_bucket_time += time_val
        display_buckets.append(last_bucket_time)
        
        # Add padding
        while len(display_buckets) < width:
            display_buckets.append(0)
        
        # Create histogram string with global normalization
        hist_chars = []
        for time_val in display_buckets[:width]:
            if time_val <= 0:
                hist_chars.append(' ')
            else:
                # Scale to max_bucket_time
                ratio = time_val / max_bucket_time
                height = int(ratio * 8)
                if height == 0 and ratio > 0:  # If ratio is very small but non-zero
                    height = 1
                height = min(height, 8)  # Cap at 8
                hist_chars.append(self.VBLOCK_CHARS[height])
        
        return ''.join(hist_chars)
    
    def make_sparkline(self, values: List[float], width: int = 20) -> str:
        """
        Create a sparkline chart from a series of values.
        
        Args:
            values: List of numeric values
            width: Maximum width of sparkline
            
        Returns:
            Unicode sparkline string
        """
        if not values:
            return ''
        
        # Limit to specified width
        if len(values) > width:
            # Sample evenly from the values
            step = len(values) / width
            sampled = []
            for i in range(width):
                idx = int(i * step)
                sampled.append(values[idx])
            values = sampled
        
        # Find min and max for normalization
        min_val = min(values)
        max_val = max(values)
        
        if max_val == min_val:
            # All values are the same
            return self.VBLOCK_CHARS[4] * len(values)
        
        # Normalize and create sparkline
        sparkline = []
        for val in values:
            # Normalize to 0-1 range
            normalized = (val - min_val) / (max_val - min_val)
            # Map to block character (1-8, avoiding space)
            height = int(normalized * 7) + 1
            sparkline.append(self.VBLOCK_CHARS[height])
        
        return ''.join(sparkline)
    
    def format_duration(self, nanoseconds: int) -> str:
        """
        Format duration from nanoseconds to human-readable format.
        
        Args:
            nanoseconds: Duration in nanoseconds
            
        Returns:
            Formatted duration string
        """
        if nanoseconds < 1000:
            return f"{nanoseconds}ns"
        elif nanoseconds < 1000000:
            return f"{nanoseconds/1000:.1f}μs"
        elif nanoseconds < 1000000000:
            return f"{nanoseconds/1000000:.1f}ms"
        else:
            return f"{nanoseconds/1000000000:.1f}s"