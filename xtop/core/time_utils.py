#!/usr/bin/env python3
"""
Time handling utilities for XTOP.
Centralizes all time bucket calculations and formatting.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger('xtop')


@dataclass(frozen=True)
class TimeParseResult:
    """Result of parsing a time specification."""
    timestamp: datetime
    is_relative: bool
    has_explicit_sign: bool


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


_RELATIVE_COMPONENT_RE = re.compile(r'([+\-]?\d+(?:\.\d*)?)([a-z]+)')
_RELATIVE_UNITS_IN_SECONDS = {
    'ms': 0.001,
    'msec': 0.001,
    'millisecond': 0.001,
    'milliseconds': 0.001,
    's': 1.0,
    'sec': 1.0,
    'secs': 1.0,
    'second': 1.0,
    'seconds': 1.0,
    'm': 60.0,
    'min': 60.0,
    'mins': 60.0,
    'minute': 60.0,
    'minutes': 60.0,
    'h': 3600.0,
    'hr': 3600.0,
    'hrs': 3600.0,
    'hour': 3600.0,
    'hours': 3600.0,
    'd': 86400.0,
    'day': 86400.0,
    'days': 86400.0,
}


def _parse_relative_offset(time_str: str) -> Optional[Tuple[timedelta, bool]]:
    """Parse relative time strings like '5min' or '-2h30m'."""
    if not time_str:
        return None

    cleaned = time_str.strip().lower()
    if not cleaned:
        return None

    has_ago = False
    if cleaned.endswith('ago'):
        cleaned = cleaned[:-3].strip()
        has_ago = True

    compact = cleaned.replace(' ', '')
    if not compact:
        return None

    matches = list(_RELATIVE_COMPONENT_RE.finditer(compact))
    if not matches:
        return None

    total_seconds = 0.0
    explicit_sign = False
    cursor = 0

    for match in matches:
        if match.start() != cursor:
            return None
        cursor = match.end()

        raw_value, unit_key = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            return None

        unit_seconds = _RELATIVE_UNITS_IN_SECONDS.get(unit_key)
        if unit_seconds is None:
            return None

        total_seconds += value * unit_seconds
        if raw_value[0] in '+-':
            explicit_sign = True

    if cursor != len(compact):
        return None

    delta = timedelta(seconds=total_seconds)
    if has_ago:
        delta = -delta
        explicit_sign = True

    return delta, explicit_sign


def parse_time_spec(time_str: str, now: Optional[datetime] = None) -> TimeParseResult:
    """Parse a time specification into an absolute timestamp."""
    if time_str is None:
        raise ValueError("Time string cannot be None")

    spec = time_str.strip()
    if not spec:
        raise ValueError("Time string cannot be empty")

    reference = now or datetime.now()
    lower_spec = spec.lower()

    if lower_spec in {'now', 'current'}:
        return TimeParseResult(reference, True, True)

    if lower_spec == 'today':
        start_of_day = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        return TimeParseResult(start_of_day, True, True)

    if lower_spec == 'yesterday':
        start_of_yesterday = (reference - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return TimeParseResult(start_of_yesterday, True, True)

    relative = _parse_relative_offset(spec)
    if relative:
        delta, explicit = relative
        timestamp = reference + delta if explicit else reference - delta
        return TimeParseResult(timestamp, True, explicit)

    # Handle ISO 8601 and common datetime formats
    trimmed_spec = spec.rstrip('zZ')
    try:
        timestamp = datetime.fromisoformat(trimmed_spec)
        return TimeParseResult(timestamp, False, False)
    except ValueError:
        pass

    # Try space-separated formats explicitly for clarity
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            timestamp = datetime.strptime(trimmed_spec, fmt)
            if fmt == '%Y-%m-%d':
                timestamp = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            return TimeParseResult(timestamp, False, False)
        except ValueError:
            continue

    # Interpret time-only inputs as today at that time
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            parsed = datetime.strptime(trimmed_spec, fmt)
            timestamp = reference.replace(
                hour=parsed.hour,
                minute=parsed.minute,
                second=parsed.second,
                microsecond=0,
            )
            return TimeParseResult(timestamp, False, False)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse time: {time_str}")


def resolve_time_range(
    from_spec: Optional[str],
    to_spec: Optional[str],
    now: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime], Dict[str, Any]]:
    """Resolve time specifications into concrete datetime bounds.

    Returns (low_time, high_time, metadata) where metadata includes parsed
    `TimeParseResult` objects (keys `from`, `to`) and `default_to_now` when
    a relative `from` without `to` forces the upper bound to current time.
    """

    reference = (now or datetime.now()).replace(microsecond=0)
    meta: Dict[str, Any] = {
        'from': None,
        'to': None,
        'default_to_now': False,
    }

    low_time: Optional[datetime] = None
    high_time: Optional[datetime] = None

    if from_spec:
        from_result = parse_time_spec(from_spec, now=reference)
        meta['from'] = from_result
        low_time = from_result.timestamp
    else:
        from_result = None

    if to_spec:
        to_result = parse_time_spec(to_spec, now=reference)
        meta['to'] = to_result
        high_time = to_result.timestamp
    else:
        to_result = None

    if from_result and from_result.is_relative and not to_result:
        high_time = reference
        meta['default_to_now'] = True

    return low_time, high_time, meta
