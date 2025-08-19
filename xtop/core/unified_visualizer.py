#!/usr/bin/env python3
"""
Unified visualizer module that consolidates all visualization functionality.
Combines ChartGenerator, HeatmapVisualizer, and other visualization utilities.
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from .time_utils import TimeUtils


class UnifiedVisualizer:
    """Unified visualizer that consolidates all visualization functionality"""
    
    # Unicode block characters for horizontal bar charts
    BLOCK_CHARS = ['', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
    
    # Vertical Unicode block characters for histograms
    VBLOCK_CHARS = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    # Color palettes for heatmaps (256-color terminal support)
    BLUE_PALETTE = [15, 51, 45, 39, 33, 27, 21]  # White to dark blue (frequency/IOPS)
    RED_PALETTE = [15, 226, 220, 214, 208, 202, 196]  # White to dark red (intensity/time)
    GREEN_PALETTE = [15, 82, 76, 70, 64, 58, 22]  # White to dark green (success)
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the unified visualizer
        
        Args:
            logger: Optional logger for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
        self.time_utils = TimeUtils()
    
    # ==================== Bar Charts ====================
    
    def make_bar(self, value: float, max_value: float, width: int = 15) -> str:
        """Create a horizontal bar chart for a value
        
        Args:
            value: The value to represent
            max_value: The maximum value in the dataset
            width: Width of the bar in characters
            
        Returns:
            Unicode bar string
        """
        if max_value == 0:
            return ''
        
        ratio = min(value / max_value, 1.0)  # Cap at 100%
        full_blocks = int(ratio * width)
        remainder = (ratio * width) - full_blocks
        
        bar = self.BLOCK_CHARS[-1] * full_blocks
        
        # Add partial block
        if remainder > 0 and full_blocks < width:
            partial_idx = int(remainder * (len(self.BLOCK_CHARS) - 1))
            if partial_idx > 0:
                bar += self.BLOCK_CHARS[partial_idx]
        
        # Pad to width
        return bar.ljust(width)
    
    def make_vertical_bar(self, value: float, max_value: float) -> str:
        """Create a single vertical bar character
        
        Args:
            value: The value to represent
            max_value: The maximum value
            
        Returns:
            Single Unicode character
        """
        if max_value == 0 or value == 0:
            return self.VBLOCK_CHARS[0]
        
        ratio = min(value / max_value, 1.0)
        idx = int(ratio * (len(self.VBLOCK_CHARS) - 1))
        return self.VBLOCK_CHARS[idx]
    
    def create_sparkline(self, values: List[float], width: int = 20) -> str:
        """Create a sparkline visualization
        
        Args:
            values: List of values to visualize
            width: Maximum width of sparkline
            
        Returns:
            Sparkline string
        """
        if not values:
            return ''
        
        # Downsample if needed
        if len(values) > width:
            step = len(values) / width
            sampled = []
            for i in range(width):
                idx = int(i * step)
                sampled.append(values[idx])
            values = sampled
        
        max_val = max(values) if values else 0
        
        sparkline = ''
        for val in values:
            sparkline += self.make_vertical_bar(val, max_val)
        
        return sparkline
    
    # ==================== Histogram Visualization ====================
    
    def create_histogram_bars(self, 
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
        
        lines = []
        max_count = max(count for _, count, _, _ in histogram_data)
        
        for bucket_us, count, _, _ in histogram_data:
            # Format label
            label = self._format_latency_label(bucket_us)
            
            # Create bar
            bar = self.make_bar(count, max_count, width)
            
            # Add percentage if requested
            if show_percentage:
                pct = (count / total_samples * 100)
                line = f"{label:>12} {bar} {pct:5.1f}%"
            else:
                line = f"{label:>12} {bar}"
            
            lines.append(line)
        
        return '\n'.join(lines)
    
    def create_inline_histogram(self, histogram_str: str, width: int = 26) -> str:
        """Create inline histogram visualization for table cells
        
        Args:
            histogram_str: Histogram data string
            width: Width in characters
            
        Returns:
            Inline visualization string
        """
        if not histogram_str or histogram_str == '-':
            return ' ' * width
        
        # Parse histogram
        buckets = []
        try:
            for item in histogram_str.split(',')[:20]:  # Limit buckets
                parts = item.split(':')
                if len(parts) >= 2:
                    count = int(parts[1])
                    buckets.append(count)
        except (ValueError, IndexError):
            return ' ' * width
        
        if not buckets:
            return ' ' * width
        
        # Create sparkline-style visualization
        max_count = max(buckets)
        viz = ''
        
        for count in buckets[:width]:
            viz += self.make_vertical_bar(count, max_count)
        
        # Pad to width
        return viz.ljust(width)
    
    # ==================== Heatmap Visualization ====================
    
    def generate_heatmap(self,
                        data: List[Dict],
                        granularity: str = "HH:MI",
                        width: Optional[int] = None,
                        height: int = 10,
                        palette: str = "blue") -> str:
        """Generate a terminal heatmap from time-series data
        
        Args:
            data: List of dicts with time buckets and values
            granularity: Time granularity
            width: Maximum width in characters
            height: Number of rows to show
            palette: Color palette name
            
        Returns:
            Formatted heatmap string
        """
        if not data:
            return "No data available for heatmap"
        
        try:
            # Extract time buckets and values
            time_buckets = self._extract_time_buckets(data, granularity)
            value_matrix = self._build_value_matrix(data, time_buckets)
            
            # Render the heatmap
            return self._render_heatmap(
                value_matrix, time_buckets,
                width=width, height=height, palette=palette
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error generating heatmap: {e}")
            return f"Error generating heatmap: {str(e)}"
    
    def _extract_time_buckets(self, data: List[Dict], granularity: str) -> List[str]:
        """Extract unique time bucket labels from data"""
        buckets = []
        seen = set()
        
        for item in data:
            label = self._format_time_label(item, granularity)
            if label not in seen:
                buckets.append(label)
                seen.add(label)
        
        return buckets
    
    def _format_time_label(self, item: Dict, granularity: str) -> str:
        """Format time label based on granularity"""
        if granularity == "HH":
            return item.get('HH', '00')
        elif granularity == "HH:MI":
            return f"{item.get('HH', '00')}:{item.get('MI', '00')}"
        elif granularity == "HH:MI:S10":
            return f"{item.get('HH', '00')}:{item.get('MI', '00')}:{item.get('S10', '00')}"
        else:
            return str(item.get('time_bucket', ''))
    
    def _build_value_matrix(self, data: List[Dict], time_buckets: List[str]) -> Dict[Tuple[int, int], float]:
        """Build matrix of values for heatmap"""
        matrix = {}
        max_value = 0
        
        # Extract unique value categories (e.g., latency buckets)
        categories = self._extract_categories(data)
        
        for time_idx, time_label in enumerate(time_buckets):
            # Find matching data item
            for item in data:
                if self._format_time_label(item, "HH:MI") == time_label:
                    # Extract values for each category
                    for cat_idx, category in enumerate(categories):
                        value = item.get(category, 0)
                        if isinstance(value, (int, float)):
                            matrix[(cat_idx, time_idx)] = value
                            max_value = max(max_value, value)
                    break
        
        # Normalize values
        if max_value > 0:
            for key in matrix:
                matrix[key] = matrix[key] / max_value
        
        return matrix
    
    def _extract_categories(self, data: List[Dict]) -> List[str]:
        """Extract category names from data"""
        if not data:
            return []
        
        # Use keys from first item (excluding time fields)
        exclude = {'HH', 'MI', 'SS', 'S10', 'YYYY', 'MM', 'DD', 'time_bucket'}
        categories = []
        
        for key in data[0].keys():
            if key not in exclude and not key.startswith('_'):
                categories.append(key)
        
        return sorted(categories)[:10]  # Limit to 10 categories
    
    def _render_heatmap(self, 
                       matrix: Dict[Tuple[int, int], float],
                       time_buckets: List[str],
                       width: Optional[int] = None,
                       height: int = 10,
                       palette: str = "blue") -> str:
        """Render the heatmap with colors"""
        lines = []
        
        # Choose palette
        if palette == "red":
            colors = self.RED_PALETTE
        elif palette == "green":
            colors = self.GREEN_PALETTE
        else:
            colors = self.BLUE_PALETTE
        
        # Limit dimensions
        max_width = width or 80
        max_time_buckets = min(len(time_buckets), max_width // 3)
        max_categories = height
        
        # Header with time labels
        header = "    "
        for i in range(max_time_buckets):
            if i < len(time_buckets):
                label = time_buckets[i][-5:]  # Last 5 chars
                header += f"{label:>3}"
            else:
                header += "   "
        lines.append(header)
        
        # Render each category row
        for cat_idx in range(max_categories):
            row = f"{cat_idx:2}: "
            
            for time_idx in range(max_time_buckets):
                value = matrix.get((cat_idx, time_idx), 0)
                
                if value == 0:
                    row += "   "
                else:
                    # Choose color based on intensity
                    color_idx = min(int(value * len(colors)), len(colors) - 1)
                    color = colors[color_idx]
                    row += f"\033[48;5;{color}m   \033[0m"
            
            lines.append(row)
        
        return "\n".join(lines)
    
    # ==================== Helper Methods ====================
    
    def _format_latency_label(self, bucket_us: int) -> str:
        """Format latency bucket for display"""
        if bucket_us < 1000:
            return f"{bucket_us}μs"
        elif bucket_us < 1000000:
            return f"{bucket_us/1000:.0f}ms"
        else:
            return f"{bucket_us/1000000:.1f}s"
    
    def create_progress_bar(self, progress: float, width: int = 20, 
                           show_percent: bool = True) -> str:
        """Create a progress bar
        
        Args:
            progress: Progress value (0.0 to 1.0)
            width: Width of progress bar
            show_percent: Whether to show percentage
            
        Returns:
            Progress bar string
        """
        progress = min(max(progress, 0.0), 1.0)
        filled = int(progress * width)
        
        bar = '[' + '█' * filled + '░' * (width - filled) + ']'
        
        if show_percent:
            bar += f" {progress * 100:.1f}%"
        
        return bar