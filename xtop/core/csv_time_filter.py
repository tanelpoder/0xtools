#!/usr/bin/env python3
"""
CSV Time Filter - Uses DuckDB glob patterns to efficiently filter CSV files by time range.
"""

from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging


class CSVTimeFilter:
    """
    Generates glob patterns for DuckDB to read only relevant hourly CSV files.
    
    xcapture generates hourly CSV files with names like:
    - xcapture_samples_2025-08-11.16.csv (16:00-16:59:59)
    - xcapture_samples_2025-08-11.17.csv (17:00-17:59:59)
    
    Uses DuckDB's glob syntax to create efficient patterns:
    - ? matches any single character
    - * matches any number of characters
    - [0-9] matches any digit
    - {16,17,18} matches any of the listed values
    """
    
    def __init__(self, datadir: Path):
        """Initialize with data directory path."""
        self.datadir = Path(datadir)
        self.logger = logging.getLogger('xtop.csv_time_filter')
    
    def get_hourly_files_in_range(self,
                                  csv_type: str,
                                  low_time: Optional[datetime] = None,
                                  high_time: Optional[datetime] = None) -> str:
        """
        Get a DuckDB glob pattern for CSV files within the time range.
        
        Args:
            csv_type: Type of CSV file ('samples', 'syscend', 'iorqend', 'kstacks', 'ustacks')
            low_time: Start of time range (inclusive)
            high_time: End of time range (exclusive)
            
        Returns:
            DuckDB glob pattern string
        """
        prefix = f"xcapture_{csv_type}_"
        
        # If no time range specified, return wildcard pattern
        if not low_time and not high_time:
            return str(self.datadir / f"{prefix}*.csv")
        
        # Handle partial time ranges by using wildcards
        if not low_time:
            # No lower bound - use wildcard up to high_time
            if high_time:
                # Round up high_time to next hour boundary
                end_hour = high_time.hour
                if high_time.minute > 0 or high_time.second > 0:
                    end_hour = (end_hour + 1) % 24
                return self._build_glob_pattern(csv_type, None, high_time)
            else:
                return str(self.datadir / f"{prefix}*.csv")
        
        if not high_time:
            # No upper bound - use wildcard from low_time
            return self._build_glob_pattern(csv_type, low_time, None)
        
        # Both bounds specified - build optimized glob
        return self._build_glob_pattern(csv_type, low_time, high_time)

    def _iter_hours(self, low_time: datetime, high_time: datetime):
        """Yield each hour boundary that overlaps [low_time, high_time).

        Example: 16:25–17:05 yields 16:00 and 17:00 hours.
        """
        if low_time is None or high_time is None:
            return
        # Floor to start hour
        t = low_time.replace(minute=0, second=0, microsecond=0)
        # Compute exclusive end boundary
        end = high_time.replace(minute=0, second=0, microsecond=0)
        if (high_time.minute != 0) or (high_time.second != 0) or (high_time.microsecond != 0):
            end = end + timedelta(hours=1)
        while t < end:
            yield t
            t = t + timedelta(hours=1)

    def get_files_for_range(self,
                            csv_type: str,
                            low_time: Optional[datetime],
                            high_time: Optional[datetime]):
        """Return (parquet_files, csv_files) for the given hourly time window.

        Prefers per-hour .parquet if present, otherwise uses .csv for that hour.
        Hours without either file are skipped.
        """
        parquet_files = []
        csv_files = []

        # If no complete range is supplied, we can't enumerate hours reliably
        if not low_time or not high_time:
            return parquet_files, csv_files

        for hour_dt in self._iter_hours(low_time, high_time):
            date_str = hour_dt.strftime("%Y-%m-%d")
            hour_str = hour_dt.strftime("%H")
            base = f"xcapture_{csv_type}_{date_str}.{hour_str}"
            parquet_path = self.datadir / f"{base}.parquet"
            csv_path = self.datadir / f"{base}.csv"
            try:
                if parquet_path.exists():
                    parquet_files.append(str(parquet_path))
                elif csv_path.exists():
                    csv_files.append(str(csv_path))
                else:
                    # Nothing for this hour; skip
                    self.logger.debug(f"No files for {base} (type={csv_type})")
            except Exception as e:
                self.logger.warning(f"Error checking files for {base}: {e}")

        # Log summary
        if parquet_files:
            self.logger.info(f"{csv_type}: using parquet for {len(parquet_files)} hour(s)")
        if csv_files:
            self.logger.info(f"{csv_type}: using csv for {len(csv_files)} hour(s)")

        return parquet_files, csv_files

    def build_mixed_source_select(self,
                                  csv_type: str,
                                  low_time: Optional[datetime],
                                  high_time: Optional[datetime]) -> str:
        """Build a SELECT source that prefers per-hour parquet, falls back to CSV.

        Returns a SELECT statement suitable for use as a subquery, e.g.:
          SELECT * FROM read_parquet(['file1.parquet','file2.parquet'])
        or when both exist across hours:
          (SELECT * FROM read_parquet([...]) UNION ALL SELECT * FROM read_csv_auto([...] ))

        If no time range is provided or no files found, falls back to CSV glob.
        """
        pq_files, csv_files = self.get_files_for_range(csv_type, low_time, high_time)

        def _list_literal(files):
            # Build a DuckDB list literal of quoted file paths
            return '[' + ', '.join(f"'{p}'" for p in files) + ']'

        if pq_files and csv_files:
            return (
                f"(SELECT * FROM read_parquet({_list_literal(pq_files)}) "
                f"UNION ALL SELECT * FROM read_csv_auto({_list_literal(csv_files)}))"
            )
        elif pq_files:
            return f"SELECT * FROM read_parquet({_list_literal(pq_files)})"
        elif csv_files:
            return f"SELECT * FROM read_csv_auto({_list_literal(csv_files)})"
        else:
            # Fallback to previous behavior: CSV glob pattern
            pattern = self.get_hourly_files_in_range(csv_type, low_time, high_time)
            return f"SELECT * FROM read_csv_auto('{pattern}')"
    
    def _build_glob_pattern(self, 
                           csv_type: str,
                           low_time: Optional[datetime],
                           high_time: Optional[datetime]) -> str:
        """
        Build an optimized glob pattern for the time range.
        
        Examples:
        - Same day, consecutive hours: xcapture_samples_2025-08-11.{16,17}.csv
        - Same day, hour range: xcapture_samples_2025-08-11.1[6-9].csv
        - Multiple days: xcapture_samples_2025-08-1[1-2].*.csv
        - Wide range: xcapture_samples_*.csv
        """
        prefix = f"xcapture_{csv_type}_"
        
        # No bounds - use wildcard
        if not low_time and not high_time:
            return str(self.datadir / f"{prefix}*.csv")
        
        # Extract date components
        if low_time and high_time:
            # Check if same day
            if low_time.date() == high_time.date():
                # Same day - can optimize hour pattern
                date_str = low_time.strftime("%Y-%m-%d")
                
                # Calculate hour range (inclusive start, exclusive end)
                start_hour = low_time.hour
                # If high_time is exactly on the hour, don't include that hour
                end_hour = high_time.hour - 1 if high_time.minute == 0 and high_time.second == 0 else high_time.hour
                
                if start_hour == end_hour:
                    # Single hour
                    pattern = f"{prefix}{date_str}.{start_hour:02d}.csv"
                elif end_hour - start_hour <= 9 and start_hour // 10 == end_hour // 10:
                    # Hours in same decade (0-9, 10-19, 20-23) - use character class
                    if start_hour < 10:
                        # Single digit hours (00-09)
                        if start_hour == end_hour:
                            pattern = f"{prefix}{date_str}.0{start_hour}.csv"
                        else:
                            pattern = f"{prefix}{date_str}.0[{start_hour}-{end_hour}].csv"
                    elif start_hour < 20:
                        # Teens (10-19)
                        if start_hour == end_hour:
                            pattern = f"{prefix}{date_str}.{start_hour}.csv"
                        else:
                            pattern = f"{prefix}{date_str}.1[{start_hour-10}-{end_hour-10}].csv"
                    else:
                        # Twenties (20-23)
                        if start_hour == end_hour:
                            pattern = f"{prefix}{date_str}.{start_hour}.csv"
                        else:
                            pattern = f"{prefix}{date_str}.2[{start_hour-20}-{end_hour-20}].csv"
                else:
                    # Spans multiple decades or wide range - use wildcards
                    # For a range like 16-17, we need to widen to 1? to capture both
                    if start_hour >= 10 and end_hour < 20:
                        pattern = f"{prefix}{date_str}.1?.csv"
                    elif start_hour >= 20 or end_hour >= 20:
                        pattern = f"{prefix}{date_str}.2?.csv"
                    else:
                        # Full day or complex range
                        pattern = f"{prefix}{date_str}.??.csv"
                
                self.logger.debug(f"Same day pattern: {pattern}")
                return str(self.datadir / pattern)
            
            # Different days - use wildcard for simplicity
            # DuckDB doesn't support complex brace expansions
            # Using wildcard is acceptable as it will still filter by timestamp
            pattern = f"{prefix}*.csv"
            
            self.logger.debug(f"Multi-day pattern: {pattern}")
            return str(self.datadir / pattern)
        
        # Only one bound specified - use wildcard
        return str(self.datadir / f"{prefix}*.csv")
    
    def get_file_patterns_for_query(self,
                                   low_time: Optional[datetime] = None,
                                   high_time: Optional[datetime] = None) -> dict:
        """
        Get file patterns for all CSV types based on time range.
        
        Returns:
            Dictionary mapping CSV type to DuckDB glob pattern
        """
        csv_types = ['samples', 'syscend', 'iorqend', 'kstacks', 'ustacks']
        patterns = {}
        
        for csv_type in csv_types:
            patterns[csv_type] = self.get_hourly_files_in_range(
                csv_type, low_time, high_time
            )
            self.logger.info(f"{csv_type}: Using pattern: {patterns[csv_type]}")
        
        return patterns
