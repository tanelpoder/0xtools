#!/usr/bin/env python3
"""
Performance optimizer for xtop queries and operations.
Provides caching, query optimization, and performance monitoring.
"""

import logging
import time
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
import threading


class PerformanceOptimizer:
    """Optimizes performance of xtop operations"""
    
    def __init__(self, 
                 cache_size: int = 100,
                 cache_ttl_seconds: int = 300,
                 logger: Optional[logging.Logger] = None):
        """Initialize the performance optimizer
        
        Args:
            cache_size: Maximum number of cached items
            cache_ttl_seconds: Cache time-to-live in seconds
            logger: Optional logger
        """
        self.logger = logger or logging.getLogger(__name__)
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl_seconds
        
        # Query result cache
        self._query_cache = {}
        self._cache_timestamps = {}
        self._cache_lock = threading.Lock()
        
        # Performance metrics
        self._query_times = []
        self._cache_hits = 0
        self._cache_misses = 0
    
    def cache_key(self, query: str, params: Dict[str, Any]) -> str:
        """Generate a cache key for a query
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Cache key string
        """
        # Create a stable hash of query + params
        key_data = f"{query}:{sorted(params.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get_cached_result(self, query: str, params: Dict[str, Any]) -> Optional[Any]:
        """Get cached query result if available
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Cached result or None
        """
        key = self.cache_key(query, params)
        
        with self._cache_lock:
            if key in self._query_cache:
                # Check if cache is still valid
                timestamp = self._cache_timestamps.get(key, 0)
                if time.time() - timestamp < self.cache_ttl:
                    self._cache_hits += 1
                    if self.logger:
                        self.logger.debug(f"Cache hit for query key: {key}")
                    return self._query_cache[key]
                else:
                    # Cache expired
                    del self._query_cache[key]
                    del self._cache_timestamps[key]
        
        self._cache_misses += 1
        return None
    
    def cache_result(self, query: str, params: Dict[str, Any], result: Any) -> None:
        """Cache a query result
        
        Args:
            query: SQL query
            params: Query parameters
            result: Query result to cache
        """
        key = self.cache_key(query, params)
        
        with self._cache_lock:
            # Implement LRU eviction if cache is full
            if len(self._query_cache) >= self.cache_size:
                # Remove oldest entry
                oldest_key = min(self._cache_timestamps, key=self._cache_timestamps.get)
                del self._query_cache[oldest_key]
                del self._cache_timestamps[oldest_key]
            
            self._query_cache[key] = result
            self._cache_timestamps[key] = time.time()
            
            if self.logger:
                self.logger.debug(f"Cached result for query key: {key}")
    
    def optimize_query(self, query: str, estimated_rows: int = 0) -> str:
        """Apply query optimizations based on expected data size
        
        Args:
            query: SQL query string
            estimated_rows: Estimated number of rows
            
        Returns:
            Optimized query with hints
        """
        optimized = query
        
        # Add DuckDB-specific optimizations
        hints = []
        
        # For large result sets, suggest parallel execution
        if estimated_rows > 10000:
            hints.append("-- PRAGMA threads=4;")
        
        # For GROUP BY queries, suggest hash aggregation
        if "group by" in query.lower():
            if estimated_rows > 1000:
                hints.append("-- Use hash aggregation for better performance")
        
        # For JOIN operations, suggest join order
        if "join" in query.lower():
            hints.append("-- Consider join order for optimal performance")
        
        # Add hints as comments
        if hints:
            optimized = "\n".join(hints) + "\n" + optimized
        
        return optimized
    
    def measure_query_time(self, func):
        """Decorator to measure query execution time
        
        Args:
            func: Function to measure
            
        Returns:
            Wrapped function
        """
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                # Record timing
                self._query_times.append(elapsed)
                if len(self._query_times) > 100:
                    self._query_times.pop(0)
                
                if self.logger:
                    self.logger.info(f"Query executed in {elapsed:.3f}s")
                
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                if self.logger:
                    self.logger.error(f"Query failed after {elapsed:.3f}s: {e}")
                raise
        
        return wrapper
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics
        
        Returns:
            Dictionary of performance metrics
        """
        stats = {
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': self._cache_hits / max(1, self._cache_hits + self._cache_misses),
            'cache_size': len(self._query_cache),
            'cache_size_limit': self.cache_size,
        }
        
        if self._query_times:
            stats.update({
                'avg_query_time': sum(self._query_times) / len(self._query_times),
                'min_query_time': min(self._query_times),
                'max_query_time': max(self._query_times),
                'total_queries': len(self._query_times),
            })
        
        return stats
    
    def clear_cache(self) -> None:
        """Clear the query cache"""
        with self._cache_lock:
            self._query_cache.clear()
            self._cache_timestamps.clear()
            
        if self.logger:
            self.logger.info("Query cache cleared")
    
    def should_use_materialized(self, 
                               data_size: int,
                               query_complexity: str) -> bool:
        """Determine if materialized tables should be used
        
        Args:
            data_size: Estimated data size in rows
            query_complexity: Query complexity (simple, moderate, complex)
            
        Returns:
            True if materialized tables should be used
        """
        # Use materialized for large datasets with complex queries
        if data_size > 1000000 and query_complexity == "complex":
            return True
        
        # Use materialized for very large datasets
        if data_size > 5000000:
            return True
        
        return False
    
    @lru_cache(maxsize=100)
    def estimate_row_count(self, 
                          table: str,
                          time_range: Tuple[datetime, datetime]) -> int:
        """Estimate row count for a table and time range
        
        Args:
            table: Table name
            time_range: (start, end) datetime tuple
            
        Returns:
            Estimated row count
        """
        # Simple estimation based on time range
        time_diff = time_range[1] - time_range[0]
        hours = time_diff.total_seconds() / 3600
        
        # Assume ~100k samples per hour as baseline
        if table == "samples":
            return int(hours * 100000)
        elif table == "syscend":
            return int(hours * 50000)
        elif table == "iorqend":
            return int(hours * 20000)
        else:
            return int(hours * 10000)
    
    def optimize_group_by(self, group_cols: List[str]) -> List[str]:
        """Optimize GROUP BY column order for better performance
        
        Args:
            group_cols: List of GROUP BY columns
            
        Returns:
            Optimized column order
        """
        # Order columns by cardinality (estimated)
        # Lower cardinality columns should come first
        cardinality_map = {
            'state': 10,  # Few states
            'cpu': 50,    # Limited CPUs
            'comm': 500,  # Moderate number of commands
            'username': 100,  # Limited users
            'tid': 10000,  # Many threads
            'pid': 5000,   # Many processes
            'exe': 1000,   # Many executables
            'filename': 5000,  # Many files
        }
        
        def get_cardinality(col):
            col_lower = col.lower()
            return cardinality_map.get(col_lower, 1000)
        
        # Sort by estimated cardinality
        return sorted(group_cols, key=get_cardinality)
    
    def batch_operations(self, operations: List[Any], batch_size: int = 100) -> List[List[Any]]:
        """Batch operations for better performance
        
        Args:
            operations: List of operations to batch
            batch_size: Size of each batch
            
        Returns:
            List of batches
        """
        batches = []
        for i in range(0, len(operations), batch_size):
            batches.append(operations[i:i + batch_size])
        return batches