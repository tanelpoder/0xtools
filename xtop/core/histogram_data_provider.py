#!/usr/bin/env python3
"""
Data provider for histogram queries and time-series data.
Separates data fetching logic from UI components.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from .query_builder import QueryBuilder
from .time_utils import TimeUtils


class HistogramDataProvider:
    """Provides data for histogram visualizations"""
    
    def __init__(self, query_engine, logger: Optional[logging.Logger] = None):
        """Initialize the histogram data provider
        
        Args:
            query_engine: QueryEngine instance for executing queries
            logger: Optional logger for debugging
        """
        self.query_engine = query_engine
        self.logger = logger or logging.getLogger(__name__)
        self.time_utils = TimeUtils()
        self.query_builder = QueryBuilder(query_engine.data_source)
    
    def parse_histogram_data(self, value: str) -> List[Tuple[int, int, float, float]]:
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
        # Format: bucket:count:time:global_max,bucket:count:time:global_max,...
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
    
    def fetch_timeseries_data(self,
                             column_key: str,
                             filters: Dict[str, Any],
                             group_cols: List[str],
                             time_range: Tuple[datetime, datetime],
                             granularity: str = "HH:MI") -> List[Dict]:
        """Fetch time-series histogram data
        
        Args:
            column_key: The histogram column (SCLAT_HISTOGRAM or IOLAT_HISTOGRAM)
            filters: Current filters to apply
            group_cols: GROUP BY columns (excluding time)
            time_range: (start, end) datetime tuple
            granularity: Time granularity (HH, HH:MI, HH:MI:S10)
            
        Returns:
            List of dictionaries with time bucket data
        """
        try:
            # Determine histogram type
            is_syscall = 'sclat' in column_key.lower()
            
            # Build time-series query
            query = self._build_timeseries_query(
                is_syscall=is_syscall,
                filters=filters,
                group_cols=group_cols,
                time_range=time_range,
                granularity=granularity
            )
            
            if self.logger:
                self.logger.debug(f"Executing time-series query for {column_key}")
                self.logger.debug(f"Query: {query}")
            
            # Execute query
            result = self.query_engine.conn.execute(query).fetchall()
            
            # Convert to list of dicts
            data = []
            for row in result:
                data.append(dict(row))
            
            if self.logger:
                self.logger.info(f"Time-series query returned {len(data)} rows")
            
            return data
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error fetching time-series data: {e}")
            return []
    
    def fetch_histogram_summary(self,
                               column_key: str,
                               value: str,
                               filters: Dict[str, Any],
                               group_cols: List[str],
                               time_range: Tuple[datetime, datetime]) -> Tuple[List[Dict], Dict]:
        """Fetch histogram summary data
        
        Args:
            column_key: The histogram column
            value: The histogram value string
            filters: Current filters
            group_cols: GROUP BY columns
            time_range: Time range
            
        Returns:
            Tuple of (table_data, summary_stats)
        """
        try:
            # Parse the histogram data
            histogram_data = self.parse_histogram_data(value)
            
            if not histogram_data:
                return [], {}
            
            # Calculate summary statistics
            total_samples = sum(count for _, count, _, _ in histogram_data)
            total_time = sum(est_time for _, _, est_time, _ in histogram_data)
            
            # Create table data
            table_data = []
            cumulative_pct = 0.0
            
            for bucket_us, count, est_time, global_max in histogram_data:
                pct_samples = (count / total_samples * 100) if total_samples > 0 else 0
                cumulative_pct += pct_samples
                pct_time = (est_time / total_time * 100) if total_time > 0 else 0
                
                table_data.append({
                    'latency_range': self._format_latency_range(bucket_us),
                    'samples': f"{count:,}",
                    'pct_samples': f"{pct_samples:.1f}%",
                    'cumulative': f"{cumulative_pct:.1f}%",
                    'est_time': f"{est_time:.2f}",
                    'pct_time': f"{pct_time:.1f}%"
                })
            
            summary_stats = {
                'total_samples': total_samples,
                'total_time': total_time,
                'bucket_count': len(histogram_data)
            }
            
            return table_data, summary_stats
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error fetching histogram summary: {e}")
            return [], {}
    
    def _build_timeseries_query(self,
                                is_syscall: bool,
                                filters: Dict[str, Any],
                                group_cols: List[str],
                                time_range: Tuple[datetime, datetime],
                                granularity: str) -> str:
        """Build time-series histogram query
        
        This is a simplified version - the actual implementation would use
        QueryBuilder or HistogramQueryBuilder
        """
        # Map granularity to time columns
        granularity_map = {
            'HH': ['HH'],
            'HH:MI': ['HH', 'MI'],
            'HH:MI:S10': ['HH', 'MI', 'S10']
        }
        
        time_cols = granularity_map.get(granularity, ['HH', 'MI'])
        
        # Build the query using QueryBuilder
        # This is simplified - actual implementation would be more complex
        histogram_col = 'sclat_histogram' if is_syscall else 'iolat_histogram'
        
        # Create WHERE clause from filters
        where_parts = []
        for col, val in filters.items():
            if isinstance(val, str):
                where_parts.append(f"{col} = '{val}'")
            else:
                where_parts.append(f"{col} = {val}")
        
        where_clause = ' AND '.join(where_parts) if where_parts else '1=1'
        
        # Build GROUP BY with time columns
        all_group_cols = time_cols + [col for col in group_cols if col.lower() not in time_cols]
        
        # Use QueryBuilder to construct the query
        # This would need to be enhanced to support histogram columns properly
        params = {
            'group_cols': all_group_cols,
            'where_clause': where_clause,
            'low_time': time_range[0],
            'high_time': time_range[1],
            'latency_columns': [histogram_col]
        }
        
        # For now, return a placeholder - actual implementation would use QueryBuilder
        return f"-- Time-series query for {histogram_col} with granularity {granularity}"
    
    def _format_latency_range(self, bucket_us: int) -> str:
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
            return f"{ms:.0f}-{next_ms:.0f}ms"
        else:
            # Seconds
            s = bucket_us / 1000000
            next_s = (bucket_us * 2) / 1000000
            if s < 10:
                return f"{s:.1f}-{next_s:.1f}s"
            else:
                return f"{s:.0f}-{next_s:.0f}s"