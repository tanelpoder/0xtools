#!/usr/bin/env python3
"""
Time handling utilities for XTOP.
Centralizes all time bucket calculations and formatting.
"""

from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger('xtop')


class TimeUtils:
    """Centralized time handling utilities for XTOP"""
    
    # Granularity options
    GRANULARITY_HOUR = 'HH'
    GRANULARITY_MINUTE = 'HH:MI'
    GRANULARITY_SECOND = 'HH:MI:S10'
    
    @staticmethod
    def parse_s10_value(s10_val: Any) -> int:
        """
        Safely parse S10 values that might be float or string.
        
        Args:
            s10_val: Value that could be int, float, string, or None
            
        Returns:
            Integer value of S10, defaulting to 0
        """
        if s10_val is None or s10_val == '':
            return 0
        
        try:
            # Handle strings like "0." or "10.0"
            if isinstance(s10_val, str) and s10_val != '00':
                return int(float(s10_val))
            elif isinstance(s10_val, (int, float)):
                return int(s10_val)
            else:
                return 0
        except (ValueError, TypeError):
            logger.warning(f"Could not parse S10 value: {s10_val}")
            return 0
    
    @staticmethod
    def extract_time_buckets(row: Dict, granularity: str) -> str:
        """
        Extract time bucket key from a data row based on granularity.
        
        Args:
            row: Data row containing HH, MI, and optionally S10
            granularity: One of 'HH', 'HH:MI', 'HH:MI:S10'
            
        Returns:
            Time bucket key as string
        """
        if granularity == TimeUtils.GRANULARITY_HOUR:
            return row.get('HH', '00')
        elif granularity == TimeUtils.GRANULARITY_MINUTE:
            return f"{row.get('HH', '00')}:{row.get('MI', '00')}"
        else:  # HH:MI:S10
            s10_val = row.get('S10', '00')
            s10 = TimeUtils.parse_s10_value(s10_val)
            return f"{row.get('HH', '00')}:{row.get('MI', '00')}:{s10:02d}"
    
    @staticmethod
    def sort_by_time(data: List[Dict], granularity: str) -> List[Dict]:
        """
        Sort data by time buckets according to granularity.
        
        Args:
            data: List of data rows
            granularity: Time granularity level
            
        Returns:
            Sorted list of data rows
        """
        if granularity == TimeUtils.GRANULARITY_HOUR:
            return sorted(data, key=lambda x: x.get('HH', '00'))
        elif granularity == TimeUtils.GRANULARITY_MINUTE:
            return sorted(data, key=lambda x: (x.get('HH', '00'), x.get('MI', '00')))
        else:  # HH:MI:S10
            def sort_key(x):
                s10_val = x.get('S10', '00')
                s10 = TimeUtils.parse_s10_value(s10_val)
                return (x.get('HH', '00'), x.get('MI', '00'), f"{s10:02d}")
            return sorted(data, key=sort_key)
    
    @staticmethod
    def get_missing_buckets(prev_item: Dict, curr_item: Dict, granularity: str) -> List[Dict]:
        """
        Get list of missing time buckets between two items.
        
        Args:
            prev_item: Previous time bucket
            curr_item: Current time bucket
            granularity: Time granularity level
            
        Returns:
            List of missing time bucket dictionaries
        """
        missing = []
        
        if granularity == TimeUtils.GRANULARITY_HOUR:
            prev_hour = int(prev_item.get('HH', '00'))
            curr_hour = int(curr_item.get('HH', '00'))
            
            for hour in range(prev_hour + 1, curr_hour):
                missing.append({'HH': f"{hour:02d}", 'MI': '00'})
                
        elif granularity == TimeUtils.GRANULARITY_MINUTE:
            prev_hour = int(prev_item.get('HH', '00'))
            prev_min = int(prev_item.get('MI', '00'))
            curr_hour = int(curr_item.get('HH', '00'))
            curr_min = int(curr_item.get('MI', '00'))
            
            # Convert to total minutes for easier calculation
            prev_total = prev_hour * 60 + prev_min
            curr_total = curr_hour * 60 + curr_min
            
            for total_min in range(prev_total + 1, curr_total):
                hour = (total_min // 60) % 24
                minute = total_min % 60
                missing.append({'HH': f"{hour:02d}", 'MI': f"{minute:02d}"})
                
        else:  # HH:MI:S10
            prev_hour = int(prev_item.get('HH', '00'))
            prev_min = int(prev_item.get('MI', '00'))
            prev_s10 = TimeUtils.parse_s10_value(prev_item.get('S10', '00'))
            
            curr_hour = int(curr_item.get('HH', '00'))
            curr_min = int(curr_item.get('MI', '00'))
            curr_s10 = TimeUtils.parse_s10_value(curr_item.get('S10', '00'))
            
            # Convert to total 10-second buckets
            prev_total = prev_hour * 360 + prev_min * 6 + prev_s10 // 10
            curr_total = curr_hour * 360 + curr_min * 6 + curr_s10 // 10
            
            for total_s10 in range(prev_total + 1, curr_total):
                hour = (total_s10 // 360) % 24
                minute = (total_s10 % 360) // 6
                second = (total_s10 % 6) * 10
                missing.append({
                    'HH': f"{hour:02d}", 
                    'MI': f"{minute:02d}", 
                    'S10': f"{second:02d}"
                })
        
        return missing
    
    @staticmethod
    def fill_missing_buckets(data: List[Dict], granularity: str) -> List[Dict]:
        """
        Fill missing time buckets with zero values.
        
        Args:
            data: List of data rows with time buckets
            granularity: Time granularity level
            
        Returns:
            List with missing buckets filled with zero values
        """
        if not data:
            return data
        
        # Sort data first
        sorted_data = TimeUtils.sort_by_time(data, granularity)
        
        # Collect all unique latency buckets if present
        all_lat_buckets = set()
        for item in sorted_data:
            if 'lat_bucket_us' in item:
                all_lat_buckets.add(item['lat_bucket_us'])
        
        # Fill in missing time buckets
        filled_data = []
        prev_item = None
        
        for item in sorted_data:
            if prev_item:
                # Check for gaps and fill them
                missing_buckets = TimeUtils.get_missing_buckets(prev_item, item, granularity)
                for missing_time in missing_buckets:
                    # Add zero entries for all latency buckets
                    if all_lat_buckets:
                        for lat_bucket in all_lat_buckets:
                            filled_entry = missing_time.copy()
                            filled_entry['lat_bucket_us'] = lat_bucket
                            filled_entry['cnt'] = 0
                            filled_data.append(filled_entry)
                    else:
                        # Just add the time bucket with zero count
                        missing_time['cnt'] = 0
                        filled_data.append(missing_time)
            
            filled_data.append(item)
            prev_item = item
        
        return filled_data
    
    @staticmethod
    def format_time_range(low_time: Optional[str], high_time: Optional[str]) -> str:
        """
        Format time range for display.
        
        Args:
            low_time: Start time or None
            high_time: End time or None
            
        Returns:
            Formatted time range string
        """
        if low_time and high_time:
            return f"{low_time} to {high_time}"
        elif low_time:
            return f"from {low_time}"
        elif high_time:
            return f"until {high_time}"
        else:
            return "all time"
    
    @staticmethod
    def get_time_select_sql(granularity: str) -> Tuple[str, str, str]:
        """
        Get SQL SELECT, GROUP BY, and ORDER BY clauses for time buckets.
        
        Args:
            granularity: Time granularity level
            
        Returns:
            Tuple of (time_select, time_group, time_order) SQL fragments
        """
        if granularity == TimeUtils.GRANULARITY_HOUR:
            time_select = """
                    LPAD(EXTRACT(HOUR FROM timestamp)::VARCHAR, 2, '0') AS HH"""
            time_group = "HH"
            time_order = "HH"
        elif granularity == TimeUtils.GRANULARITY_MINUTE:
            time_select = """
                    LPAD(EXTRACT(HOUR FROM timestamp)::VARCHAR, 2, '0') AS HH,
                    LPAD(EXTRACT(MINUTE FROM timestamp)::VARCHAR, 2, '0') AS MI"""
            time_group = "HH, MI"
            time_order = "HH, MI"
        else:  # HH:MI:S10
            time_select = """
                    LPAD(EXTRACT(HOUR FROM timestamp)::VARCHAR, 2, '0') AS HH,
                    LPAD(EXTRACT(MINUTE FROM timestamp)::VARCHAR, 2, '0') AS MI,
                    LPAD((FLOOR(EXTRACT(SECOND FROM timestamp) / 10) * 10)::VARCHAR, 2, '0') AS S10"""
            time_group = "HH, MI, S10"
            time_order = "HH, MI, S10"
        
        return time_select, time_group, time_order
    
    @staticmethod
    def build_time_constraints(low_time: Optional[str], high_time: Optional[str]) -> str:
        """
        Build SQL time constraint clauses.
        
        Args:
            low_time: Start time or None
            high_time: End time or None
            
        Returns:
            SQL WHERE clause fragment for time constraints
        """
        constraints = []
        
        if low_time is not None:
            constraints.append(f"timestamp >= TIMESTAMP '{low_time}'")
        
        if high_time is not None:
            constraints.append(f"timestamp < TIMESTAMP '{high_time}'")
        
        if constraints:
            return " AND " + " AND ".join(constraints)
        else:
            return ""