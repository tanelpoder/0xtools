#!/usr/bin/env python3
"""
Heatmap visualization component.
Separates heatmap rendering logic from modal UI.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from rich.text import Text
from rich.console import Console
from rich.table import Table
from .time_utils import TimeUtils


class HeatmapVisualizer:
    """Creates terminal heatmap visualizations for time-series data"""
    
    # Color palettes for heatmaps (256-color terminal support)
    BLUE_PALETTE = [15, 51, 45, 39, 33, 27, 21]  # White to dark blue (frequency/IOPS)
    RED_PALETTE = [15, 226, 220, 214, 208, 202, 196]  # White to dark red (intensity/time)
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the heatmap visualizer
        
        Args:
            logger: Optional logger for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
        self.time_utils = TimeUtils()
    
    def generate_heatmap(self,
                        data: List[Dict],
                        granularity: str = "HH:MI",
                        width: Optional[int] = None,
                        height: int = 10,
                        palette: str = "blue") -> str:
        """Generate a terminal heatmap from time-series histogram data
        
        Args:
            data: List of dicts with time buckets and histogram data
            granularity: Time granularity (HH, HH:MI, HH:MI:S10)
            width: Maximum width in characters (None for auto)
            height: Number of latency buckets to show
            palette: Color palette ("blue" or "red")
            
        Returns:
            Formatted heatmap string
        """
        if not data:
            return "No data available for heatmap"
        
        try:
            # Fill missing time buckets
            filled_data = self._fill_missing_time_buckets(data, granularity)
            
            # Extract unique time buckets and latency buckets
            time_buckets = self._get_time_buckets(filled_data, granularity)
            latency_buckets = self._get_latency_buckets(filled_data)
            
            # Build the heatmap matrix
            matrix = self._build_heatmap_matrix(filled_data, time_buckets, latency_buckets)
            
            # Render the heatmap
            return self._render_heatmap(
                matrix, time_buckets, latency_buckets,
                width=width, palette=palette
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error generating heatmap: {e}")
            return f"Error generating heatmap: {str(e)}"
    
    def _fill_missing_time_buckets(self, data: List[Dict], granularity: str) -> List[Dict]:
        """Fill in missing time buckets with zero values
        
        Args:
            data: Original time-series data
            granularity: Time granularity
            
        Returns:
            Data with missing time buckets filled
        """
        if not data:
            return data
        
        filled = []
        prev_item = None
        
        for item in data:
            if prev_item:
                # Check for gaps and fill them
                missing = self._get_missing_time_buckets(prev_item, item, granularity)
                filled.extend(missing)
            filled.append(item)
            prev_item = item
        
        return filled
    
    def _get_missing_time_buckets(self, prev: Dict, curr: Dict, granularity: str) -> List[Dict]:
        """Get missing time buckets between two data points
        
        Args:
            prev: Previous data point
            curr: Current data point
            granularity: Time granularity
            
        Returns:
            List of missing time bucket entries
        """
        missing = []
        
        # Extract time components
        if granularity == "HH":
            prev_hour = int(prev.get('HH', 0))
            curr_hour = int(curr.get('HH', 0))
            
            for h in range(prev_hour + 1, curr_hour):
                missing.append({
                    'HH': str(h).zfill(2),
                    'histogram_data': []
                })
                
        elif granularity == "HH:MI":
            prev_hour = int(prev.get('HH', 0))
            prev_min = int(prev.get('MI', 0))
            curr_hour = int(curr.get('HH', 0))
            curr_min = int(curr.get('MI', 0))
            
            # Simple implementation - would need more logic for hour boundaries
            if prev_hour == curr_hour:
                for m in range(prev_min + 1, curr_min):
                    missing.append({
                        'HH': str(prev_hour).zfill(2),
                        'MI': str(m).zfill(2),
                        'histogram_data': []
                    })
        
        return missing
    
    def _get_time_buckets(self, data: List[Dict], granularity: str) -> List[str]:
        """Extract unique time bucket labels
        
        Args:
            data: Time-series data
            granularity: Time granularity
            
        Returns:
            List of time bucket labels
        """
        buckets = []
        seen = set()
        
        for item in data:
            if granularity == "HH":
                label = item.get('HH', '00')
            elif granularity == "HH:MI":
                label = f"{item.get('HH', '00')}:{item.get('MI', '00')}"
            elif granularity == "HH:MI:S10":
                label = f"{item.get('HH', '00')}:{item.get('MI', '00')}:{item.get('S10', '00')}"
            else:
                label = str(item.get('time_bucket', ''))
            
            if label not in seen:
                buckets.append(label)
                seen.add(label)
        
        return buckets
    
    def _get_latency_buckets(self, data: List[Dict]) -> List[int]:
        """Extract unique latency buckets from all histograms
        
        Args:
            data: Time-series data with histograms
            
        Returns:
            Sorted list of latency bucket values in microseconds
        """
        buckets = set()
        
        for item in data:
            hist_data = item.get('histogram_data', [])
            if isinstance(hist_data, str):
                # Parse histogram string if needed
                hist_data = self._parse_histogram_string(hist_data)
            
            for bucket_us, _, _, _ in hist_data:
                buckets.add(bucket_us)
        
        return sorted(buckets)
    
    def _parse_histogram_string(self, hist_str: str) -> List[tuple]:
        """Parse histogram string into tuples
        
        Args:
            hist_str: Histogram string
            
        Returns:
            List of (bucket_us, count, time, max) tuples
        """
        result = []
        if not hist_str or hist_str == '-':
            return result
        
        for bucket in hist_str.split(','):
            if bucket:
                try:
                    parts = bucket.split(':')
                    if len(parts) >= 4:
                        result.append((
                            int(parts[0]),
                            int(parts[1]),
                            float(parts[2]),
                            float(parts[3])
                        ))
                except (ValueError, IndexError):
                    pass
        
        return result
    
    def _build_heatmap_matrix(self, data: List[Dict], 
                             time_buckets: List[str],
                             latency_buckets: List[int]) -> Dict[Tuple[int, int], float]:
        """Build the heatmap matrix
        
        Args:
            data: Time-series data
            time_buckets: Time bucket labels
            latency_buckets: Latency bucket values
            
        Returns:
            Dictionary mapping (lat_idx, time_idx) to intensity value
        """
        matrix = {}
        max_value = 0
        
        for time_idx, time_label in enumerate(time_buckets):
            # Find matching data item
            matching_item = None
            for item in data:
                item_label = self._get_item_time_label(item)
                if item_label == time_label:
                    matching_item = item
                    break
            
            if matching_item:
                hist_data = matching_item.get('histogram_data', [])
                if isinstance(hist_data, str):
                    hist_data = self._parse_histogram_string(hist_data)
                
                # Fill in values for this time bucket
                for bucket_us, count, _, _ in hist_data:
                    if bucket_us in latency_buckets:
                        lat_idx = latency_buckets.index(bucket_us)
                        matrix[(lat_idx, time_idx)] = count
                        max_value = max(max_value, count)
        
        # Normalize values
        if max_value > 0:
            for key in matrix:
                matrix[key] = matrix[key] / max_value
        
        return matrix
    
    def _get_item_time_label(self, item: Dict) -> str:
        """Get time label for a data item based on available fields"""
        if 'HH' in item and 'MI' in item and 'S10' in item:
            return f"{item['HH']}:{item['MI']}:{item['S10']}"
        elif 'HH' in item and 'MI' in item:
            return f"{item['HH']}:{item['MI']}"
        elif 'HH' in item:
            return item['HH']
        else:
            return str(item.get('time_bucket', ''))
    
    def _render_heatmap(self, matrix: Dict[Tuple[int, int], float],
                       time_buckets: List[str],
                       latency_buckets: List[int],
                       width: Optional[int] = None,
                       palette: str = "blue") -> str:
        """Render the heatmap as a colored string
        
        Args:
            matrix: Heatmap matrix
            time_buckets: Time bucket labels
            latency_buckets: Latency bucket values
            width: Maximum width
            palette: Color palette to use
            
        Returns:
            Rendered heatmap string
        """
        lines = []
        colors = self.BLUE_PALETTE if palette == "blue" else self.RED_PALETTE
        
        # Header with time labels
        header = "       " + " ".join(f"{t:>5}" for t in time_buckets[:20])  # Limit width
        lines.append(header)
        
        # Render each latency row
        for lat_idx, lat_us in enumerate(latency_buckets[:10]):  # Limit height
            lat_label = self._format_latency(lat_us)
            row = f"{lat_label:>6} "
            
            for time_idx in range(min(len(time_buckets), 20)):
                value = matrix.get((lat_idx, time_idx), 0)
                
                # Choose color based on intensity
                if value == 0:
                    row += "     "
                else:
                    color_idx = min(int(value * len(colors)), len(colors) - 1)
                    color = colors[color_idx]
                    row += f"\033[48;5;{color}m     \033[0m"
            
            lines.append(row)
        
        return "\n".join(lines)
    
    def _format_latency(self, bucket_us: int) -> str:
        """Format latency bucket for display
        
        Args:
            bucket_us: Bucket in microseconds
            
        Returns:
            Formatted string
        """
        if bucket_us < 1000:
            return f"{bucket_us}μs"
        elif bucket_us < 1000000:
            return f"{bucket_us/1000:.0f}ms"
        else:
            return f"{bucket_us/1000000:.1f}s"