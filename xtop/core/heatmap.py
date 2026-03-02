#!/usr/bin/env python3
"""
Latency heatmap visualization for xcapture data.
Generates Unicode-based heatmaps for latency distribution over time.
"""

from typing import Dict, List, Tuple, Optional
import math
from dataclasses import dataclass


@dataclass
class HeatmapConfig:
    """Configuration for heatmap rendering"""
    width: int = 60  # Number of time buckets to show
    height: int = 12  # Number of latency buckets
    min_latency_us: int = 1  # Minimum latency in microseconds
    max_latency_us: int = 1000000000  # Maximum latency in microseconds (1 second)
    use_color: bool = False  # Whether to use colors (for terminal)
    use_rich_markup: bool = False  # Whether to use Rich/Textual markup instead of raw ANSI


class LatencyHeatmap:
    """Generate latency heatmap visualizations"""
    
    # Unicode block characters for intensity levels
    INTENSITY_CHARS = [' ', '░', '▒', '▓', '█']
    
    # Alternative ASCII characters for simpler display
    ASCII_CHARS = [' ', '.', ':', '=', '#']
    
    # 256-color gradient palettes for heatmap
    # Blue palette for frequency (events/sec)
    BLUE_PALETTE_256 = {
        0: 15,   # White (no data)
        1: 51,   # Light blue
        2: 45,   # Blue  
        3: 39,   # Blue
        4: 33,   # Darker blue
        5: 27,   # Dark blue
        6: 21,   # Very dark blue
    }
    
    # Red palette for intensity (time waited)
    RED_PALETTE_256 = {
        0: 15,   # White (no data)
        1: 226,  # Light yellow
        2: 220,  # Yellow
        3: 214,  # Orange-yellow
        4: 208,  # Orange
        5: 202,  # Red-orange
        6: 196,  # Red
    }
    
    # Rich/Textual color names for the palettes (using color indices)
    BLUE_PALETTE_RICH = {
        0: "color(15)",   # White (no data)
        1: "color(51)",   # Light blue
        2: "color(45)",   # Blue
        3: "color(39)",   # Blue
        4: "color(33)",   # Darker blue
        5: "color(27)",   # Dark blue
        6: "color(21)",   # Very dark blue
    }
    
    RED_PALETTE_RICH = {
        0: "color(15)",   # White (no data)
        1: "color(226)",  # Light yellow
        2: "color(220)",  # Yellow
        3: "color(214)",  # Orange-yellow
        4: "color(208)",  # Orange
        5: "color(202)",  # Red-orange
        6: "color(196)",  # Red
    }
    
    def __init__(self, config: Optional[HeatmapConfig] = None):
        """Initialize heatmap generator with configuration"""
        self.config = config or HeatmapConfig()
        self.latency_buckets = self._generate_latency_buckets()
    
    def _generate_latency_buckets(self) -> List[int]:
        """Generate exponential latency buckets in microseconds"""
        buckets = []
        current = self.config.min_latency_us
        
        while current <= self.config.max_latency_us:
            buckets.append(current)
            # Use powers of 2 for bucket boundaries
            current = current * 2
        
        return buckets
    
    def _format_latency(self, upper_us: int) -> str:
        """Format latency bucket using half-open range notation."""

        if upper_us <= 0:
            return "0μs"

        low_us = max(upper_us // 2, 1)
        high_us = upper_us

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
    
    def _get_bucket_index(self, latency_us: int) -> int:
        """Find the bucket index for a given latency value"""
        for i, bucket in enumerate(self.latency_buckets):
            if latency_us < bucket:
                return max(0, i - 1)
        return len(self.latency_buckets) - 1
    
    def generate_timeseries_heatmap(self, 
                                   data: List[Dict], 
                                   palette: str = 'blue') -> str:
        """
        Generate a time-series latency heatmap from query results.
        
        Args:
            data: List of dicts with columns: HH, MI, lat_bucket_us, count, etc.
            palette: 'blue' for frequency or 'red' for intensity
            
        Returns:
            String representation of the time-series heatmap
        """
        if not data:
            return "No data available for heatmap"
        
        # Parse data into time buckets and latency buckets
        time_data = {}  # {time_str: {bucket_us: count}}
        all_buckets = set()
        time_labels = []
        
        for row in data:
            # Create time label from HH:MI or HH:MI:S10 if S10 is present
            if 'S10' in row:
                time_str = f"{row.get('HH', '00')}:{row.get('MI', '00')}:{row.get('S10', '00')}"
            else:
                time_str = f"{row.get('HH', '00')}:{row.get('MI', '00')}"
            
            if time_str not in time_data:
                time_data[time_str] = {}
                time_labels.append(time_str)
            
            # Get latency bucket and count
            bucket_us = row.get('lat_bucket_us', row.get('sc_lat_bkt_us', row.get('io_lat_bkt_us', 0)))
            count = row.get('cnt', row.get('count', 0))
            
            # Skip None values (NULL from SQL when no latency data)
            if bucket_us is None:
                continue
            
            time_data[time_str][bucket_us] = count
            all_buckets.add(bucket_us)
        
        # Sort time labels and buckets
        time_labels = sorted(time_labels)
        # Check if we have any valid buckets
        if not all_buckets:
            return "No latency data available for heatmap (all values were NULL)"
        sorted_buckets = sorted(all_buckets)
        
        # Debug logging
        import logging
        logger = logging.getLogger('xtop')
        logger.debug(f"Heatmap buckets found: {sorted_buckets[:10] if len(sorted_buckets) > 10 else sorted_buckets}")
        
        # Don't limit time buckets - the width should be set appropriately by caller
        # This allows for horizontal scrolling when needed
        # if len(time_labels) > self.config.width:
        #     time_labels = time_labels[-self.config.width:]
        
        # Select palette based on output format
        if self.config.use_rich_markup:
            color_map = self.BLUE_PALETTE_RICH if palette == 'blue' else self.RED_PALETTE_RICH
        else:
            color_map = self.BLUE_PALETTE_256 if palette == 'blue' else self.RED_PALETTE_256
        
        # Find max count for normalization
        max_count = 0
        for time_str in time_labels:
            for bucket in sorted_buckets:
                count = time_data.get(time_str, {}).get(bucket, 0)
                max_count = max(max_count, count)
        
        # Generate the heatmap display
        lines = []
        
        # Header
        lines.append("═══ Latency Heatmap (Time Series) ═══")
        lines.append("")
        
        # Time range
        if time_labels:
            lines.append(f"Time range: {time_labels[0]} → {time_labels[-1]}")
            lines.append("")
        
        # Determine label width for alignment
        label_width = max(8, max(len(self._format_latency(bucket)) for bucket in sorted_buckets))

        # Generate heatmap rows (from high latency to low)
        # Show ALL buckets, not just the highest ones
        for bucket in reversed(sorted_buckets):
            label = self._format_latency(bucket).rjust(label_width)
            
            row_chars = []
            for time_str in time_labels:
                count = time_data.get(time_str, {}).get(bucket, 0)
                
                # Calculate color token (0-6)
                if count == 0:
                    token = 0
                elif max_count > 0:
                    token = min(6, int((count / max_count) * 6) + 1)
                else:
                    token = 0
                
                # Get color code or Rich color name
                color = color_map[token]
                
                if self.config.use_color:
                    if self.config.use_rich_markup:
                        # Use Rich markup for background color
                        row_chars.append(f"[on {color}] [/]")
                    else:
                        # Use raw ANSI for background color
                        row_chars.append(f"\033[48;5;{color}m \033[0m")
                else:
                    # Fallback to intensity characters
                    row_chars.append(self.INTENSITY_CHARS[min(token, len(self.INTENSITY_CHARS)-1)])
            
            row_str = ''.join(row_chars)
            lines.append(f"{label} │ {row_str}")
        
        # Bottom axis
        axis_offset = label_width + 1
        lines.append(" " * axis_offset + "└" + "─" * len(time_labels))
        lines.append(" " * (axis_offset + 2) + "Time →")
        
        # Legend
        lines.append("")
        lines.append("Color scale: ")
        legend_bar = []
        for token in range(7):
            color = color_map[token]
            if self.config.use_rich_markup:
                legend_bar.append(f"[on {color}]  [/]")
            else:
                legend_bar.append(f"\033[48;5;{color}m  \033[0m")
        lines.append(''.join(legend_bar) + " (0 → max)")
        
        return '\n'.join(lines)
    
    def generate_histogram_heatmap(self, histogram_data: str, 
                                  time_bucket: str = "HH:MI") -> Tuple[str, Dict]:
        """
        Generate a heatmap from histogram string data.
        
        Args:
            histogram_data: String in format "bucket:count:time:max,..."
            time_bucket: Time aggregation level (HH:MI, DD, etc.)
            
        Returns:
            Tuple of (heatmap_string, parsed_data_dict)
        """
        if not histogram_data or histogram_data == '-':
            return "No histogram data available", {}
        
        # Parse histogram data
        parsed = {}
        items = histogram_data.split(',')
        
        for item in items:
            parts = item.split(':')
            if len(parts) >= 2:
                bucket_us = int(parts[0])
                count = int(parts[1])
                parsed[bucket_us] = count
        
        # For single histogram, create a colorful bar chart
        lines = []
        lines.append("═══ Latency Distribution ═══")
        lines.append("")
        
        # Find max count for scaling
        max_count = max(parsed.values()) if parsed else 1
        total_count = sum(parsed.values()) if parsed else 1
        bar_width = 40
        
        # Sort buckets and display with colors
        for bucket_us in sorted(parsed.keys()):
            count = parsed[bucket_us]
            label = self._format_latency(bucket_us).rjust(8)
            
            # Calculate bar length and intensity
            bar_len = int((count / max_count) * bar_width)
            percentage = (count / total_count) * 100 if total_count > 0 else 0
            
            if self.config.use_color and bar_len > 0:
                # Create colored bar using 256-color background
                bar_chars = []
                # Calculate color token based on the relative value (percentage)
                if count == 0:
                    token = 0
                elif max_count > 0:
                    token = min(6, int((count / max_count) * 6) + 1)
                else:
                    token = 0
                
                if self.config.use_rich_markup:
                    color = self.BLUE_PALETTE_RICH[token]
                    for i in range(bar_width):
                        if i < bar_len:
                            bar_chars.append(f"[on {color}] [/]")
                        else:
                            bar_chars.append(" ")
                else:
                    color_code = self.BLUE_PALETTE_256[token]
                    for i in range(bar_width):
                        if i < bar_len:
                            bar_chars.append(f"\033[48;5;{color_code}m \033[0m")
                        else:
                            bar_chars.append(" ")
                bar = ''.join(bar_chars)
            else:
                # Fallback to Unicode blocks without color
                bar = '█' * bar_len + '░' * (bar_width - bar_len)
            
            lines.append(f"{label} │ {bar} {count:,} ({percentage:.1f}%)")
        
        # Add color legend if using colors
        if self.config.use_color:
            lines.append("")
            lines.append("Color scale: ")
            legend_bar = []
            for token in range(7):
                if self.config.use_rich_markup:
                    color = self.BLUE_PALETTE_RICH[token]
                    legend_bar.append(f"[on {color}]  [/]")
                else:
                    color_code = self.BLUE_PALETTE_256[token]
                    legend_bar.append(f"\033[48;5;{color_code}m  \033[0m")
            lines.append(''.join(legend_bar) + " (0 → max)")
        
        return '\n'.join(lines), parsed
