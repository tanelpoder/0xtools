#!/usr/bin/env python3
"""
Modular SQL query builder for xcapture data.
Builds queries using reusable SQL fragments for better maintainability.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
import logging
from .csv_time_filter import CSVTimeFilter


class FragmentLoader:
    """Loads and caches SQL fragments from disk"""
    
    def __init__(self, fragments_path: Path):
        self.fragments_path = fragments_path
        self.cache: Dict[str, str] = {}
        self.logger = logging.getLogger('xtop.fragments')
    
    def load(self, fragment_name: str) -> str:
        """Load a SQL fragment by name (without .sql extension)"""
        if fragment_name in self.cache:
            return self.cache[fragment_name]
        
        fragment_file = self.fragments_path / f"{fragment_name}.sql"
        if not fragment_file.exists():
            raise FileNotFoundError(f"Fragment not found: {fragment_file}")
        
        with open(fragment_file, 'r') as f:
            content = f.read()
        
        self.cache[fragment_name] = content
        return content
    
    def clear_cache(self):
        """Clear the fragment cache"""
        self.cache.clear()


class QueryBuilder:
    """Builds SQL queries using modular fragments"""
    
    # Columns that require specific data sources
    COLUMN_SOURCE_MAP = {
        # Syscall latency columns
        'sc.min_lat_us': 'syscend',
        'sc.avg_lat_us': 'syscend', 
        'sc.max_lat_us': 'syscend',
        'sc.p50_us': 'syscend',
        'sc.p95_us': 'syscend',
        'sc.p99_us': 'syscend',
        'sc.p999_us': 'syscend',
        'sclat_histogram': 'syscend',
        
        # I/O latency columns
        'io.min_lat_us': 'iorqend',
        'io.avg_lat_us': 'iorqend',
        'io.max_lat_us': 'iorqend',
        'io.p50_us': 'iorqend',
        'io.p95_us': 'iorqend',
        'io.p99_us': 'iorqend',
        'io.p999_us': 'iorqend',
        'iolat_histogram': 'iorqend',
        
        # Device columns
        'devname': 'partitions',
        'devname': 'partitions',
        
        # Stack columns
        'kstack_hash': 'kstacks',
        'kstack_syms': 'kstacks',
        'kstack_current_func': 'kstacks',
        
        'ustack_hash': 'ustacks',
        'ustack_syms': 'ustacks',
        'ustack_current_func': 'ustacks',
    }
    
    # Computed columns that are always available in enriched_samples
    COMPUTED_COLUMNS = [
        'filenamesum', 'fext', 'comm2', 'connection'
    ]
    
    def __init__(self, datadir: Path, fragments_path: Path, 
                 use_materialized: bool = False):
        """
        Initialize query builder.
        
        Args:
            datadir: Path to data directory
            fragments_path: Path to SQL fragments directory
            use_materialized: If True, use materialized tables instead of CSV
        """
        self.datadir = datadir
        self.fragments = FragmentLoader(fragments_path)
        self.use_materialized = use_materialized
        self.csv_filter = CSVTimeFilter(datadir)
        self.logger = logging.getLogger('xtop.query_builder')
    
    def build_dynamic_query(self, 
                           group_cols: List[str],
                           where_clause: str = "1=1",
                           low_time: Optional[datetime] = None,
                           high_time: Optional[datetime] = None,
                           latency_columns: Optional[List[str]] = None,
                           limit: Optional[int] = None) -> str:
        """
        Build a dynamic query based on requested columns.
        
        Args:
            group_cols: Columns to group by
            where_clause: WHERE clause conditions
            low_time: Start time for data range
            high_time: End time for data range
            latency_columns: Additional latency/aggregate columns to include
            limit: Row limit for results
            
        Returns:
            Complete SQL query string
        """
        # Standardize column names to lowercase
        group_cols = [col.lower() for col in group_cols]
        # Determine all requested columns
        all_columns = set(group_cols)
        all_columns.update(['samples', 'avg_threads'])  # Always include these
        if latency_columns:
            all_columns.update([col.lower() for col in latency_columns])
        
        # Determine required data sources
        required_sources = self._determine_required_sources(all_columns)
        
        # Check for histogram requirements
        # Check for histogram columns (case-insensitive)
        all_columns_lower = {col.lower() for col in all_columns}
        need_sc_histogram = 'sclat_histogram' in all_columns_lower
        need_io_histogram = 'iolat_histogram' in all_columns_lower
        
        # Build the query parts
        ctes = []
        
        # 1. Build enriched_samples CTE with all computed columns
        enriched_cte = self._build_enriched_samples_cte(low_time, high_time)
        ctes.append(f"enriched_samples AS (\n{enriched_cte}\n)")
        
        # 2. Build base_samples CTE with JOINs and filters
        base_cte = self._build_base_samples_cte(
            required_sources, where_clause, low_time, high_time,
            need_sc_histogram, need_io_histogram
        )
        ctes.append(f"base_samples AS (\n{base_cte}\n)")
        
        # 3. Add histogram CTEs if needed
        if need_sc_histogram:
            hist_cte = self._build_histogram_cte(
                'sc', group_cols, 'sc_duration_ns', 'sc_lat_bkt_us'
            )
            ctes.extend(hist_cte)
        
        if need_io_histogram:
            hist_cte = self._build_histogram_cte(
                'io', group_cols, 'io_duration_ns', 'io_lat_bkt_us'
            )
            ctes.extend(hist_cte)
        
        # 3.5 Add sample counts CTE if we have histograms
        # This prevents the histogram JOIN from multiplying the count
        if need_sc_histogram or need_io_histogram:
            # Filter group columns (exclude aggregates)
            count_group_cols = [col for col in group_cols 
                               if col.lower() not in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']
                               and not col.lower().startswith('sc.') and not col.lower().startswith('io.')]
            
            # Build sample counts CTE with latency columns
            count_cte = self._build_sample_counts_cte(count_group_cols, low_time, high_time, latency_columns)
            ctes.append(f"sample_counts AS (\n{count_cte}\n)")
        
        # 4. Build final SELECT
        final_select = self._build_final_select(
            group_cols, latency_columns, required_sources,
            need_sc_histogram, need_io_histogram, low_time, high_time
        )
        
        # 5. Build GROUP BY and ORDER BY
        has_histogram = need_sc_histogram or need_io_histogram
        group_by = self._build_group_by(group_cols, required_sources, has_histogram)
        
        # Add FROM clause with histogram JOINs if needed
        if need_sc_histogram or need_io_histogram:
            # When we have histograms, we need to join sample_counts with histogram data
            from_clause = "FROM sample_counts sc"
            
            if need_sc_histogram:
                # Filter group columns for JOIN (exclude aggregates)
                join_cols = [col for col in group_cols 
                            if col.lower() not in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']
                            and not col.lower().startswith('sc.') and not col.lower().startswith('io.')]
                if join_cols:
                    from_clause += f"\nLEFT JOIN sc_bucket_with_max sc_bc ON ({' AND '.join([f'sc.{col} = sc_bc.{col}' for col in join_cols])})"
                else:
                    # If no group columns, we need a different join strategy
                    from_clause += f"\nCROSS JOIN sc_bucket_with_max sc_bc"
            
            if need_io_histogram:
                # Filter group columns for JOIN (exclude aggregates)
                join_cols = [col for col in group_cols 
                            if col.lower() not in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']
                            and not col.lower().startswith('sc.') and not col.lower().startswith('io.')]
                if join_cols:
                    from_clause += f"\nLEFT JOIN io_bucket_with_max io_bc ON ({' AND '.join([f'sc.{col} = io_bc.{col}' for col in join_cols])})"
                else:
                    # If no group columns, we need a different join strategy
                    from_clause += f"\nCROSS JOIN io_bucket_with_max io_bc"
        else:
            # No histograms, use base_samples directly
            from_clause = "FROM base_samples bs"
        
        # Combine everything
        query = f"WITH {',\n'.join(ctes)}\n{final_select}\n{from_clause}\n{group_by}\nORDER BY samples DESC"
        if limit:
            query += f"\nLIMIT {limit}"
        
        return query
    
    def build_histogram_drill_down_query(self,
                                        histogram_type: str,  # 'sclat' or 'iolat'
                                        where_clause: str,
                                        low_time: Optional[datetime] = None,
                                        high_time: Optional[datetime] = None,
                                        time_granularity: Optional[str] = None) -> str:
        """
        Build a histogram drill-down query for peek modal.
        Uses the same infrastructure as main queries but focuses on histogram data.
        
        Args:
            histogram_type: 'sclat' for syscall latency, 'iolat' for I/O latency
            where_clause: WHERE clause with row-specific filters
            low_time: Start time for data range
            high_time: End time for data range
            time_granularity: Optional time bucketing ('HH', 'HH:MI', 'HH:MI:S10')
            
        Returns:
            SQL query for histogram drill-down
        """
        # Determine which columns are referenced in WHERE clause
        where_cols = self._extract_columns_from_where(where_clause)
        
        # Determine required sources based on WHERE clause columns
        required_sources = self._determine_required_sources(where_cols)
        
        # Always need the appropriate latency source
        if histogram_type == 'sclat':
            required_sources.add('syscend')
        else:
            required_sources.add('iorqend')
            
        # Build the query parts
        ctes = []
        
        # 1. Build enriched_samples CTE
        enriched_cte = self._build_enriched_samples_cte(low_time, high_time)
        ctes.append(f"enriched_samples AS (\n{enriched_cte}\n)")
        
        # 2. Build base_samples CTE with appropriate JOINs
        base_cte = self._build_base_samples_cte(
            required_sources, "1=1", low_time, high_time,
            histogram_type == 'sclat', histogram_type == 'iolat'
        )
        ctes.append(f"base_samples AS (\n{base_cte}\n)")
        
        # 3. Build final SELECT for histogram
        if time_granularity:
            # Time-series histogram for heatmap
            select_clause = self._build_time_series_histogram_select(
                histogram_type, time_granularity
            )
        else:
            # Simple histogram for data table
            select_clause = self._build_simple_histogram_select(histogram_type)
        
        # Combine everything
        # Add filter for non-NULL bucket values to avoid comparison errors
        bucket_col = 'sc_lat_bkt_us' if histogram_type == 'sclat' else 'io_lat_bkt_us'
        query = f"""WITH {',\n'.join(ctes)}
{select_clause}
FROM base_samples
WHERE ({where_clause})
    AND {bucket_col} IS NOT NULL
GROUP BY {self._get_histogram_group_by(time_granularity)}
ORDER BY {self._get_histogram_order_by(time_granularity)}"""
        
        return query
    
    def _extract_columns_from_where(self, where_clause: str) -> Set[str]:
        """Extract column names referenced in WHERE clause"""
        import re
        columns = set()
        
        # Simple regex to find column names before = operator
        # This is a simplified approach - could be enhanced with proper SQL parsing
        pattern = r'(\w+)\s*='
        matches = re.findall(pattern, where_clause)
        columns.update(matches)
        
        return columns
    
    def _build_time_series_histogram_select(self, histogram_type: str, 
                                           time_granularity: str) -> str:
        """Build SELECT clause for time-series histogram"""
        # Time bucket columns are already computed in enriched_samples CTE
        # Just reference them directly
        time_cols = []
        if 'HH' in time_granularity:
            time_cols.append("HH")
        if 'MI' in time_granularity:
            time_cols.append("MI")
        if 'S10' in time_granularity:
            time_cols.append("S10")
        
        bucket_col = 'sc_lat_bkt_us' if histogram_type == 'sclat' else 'io_lat_bkt_us'
        
        return f"""SELECT
    {', '.join(time_cols)},
    {bucket_col} AS lat_bucket_us,
    COUNT(*) as cnt"""
    
    def _build_simple_histogram_select(self, histogram_type: str) -> str:
        """Build SELECT clause for simple histogram"""
        bucket_col = 'sc_lat_bkt_us' if histogram_type == 'sclat' else 'io_lat_bkt_us'
        duration_col = 'sc_duration_ns' if histogram_type == 'sclat' else 'io_duration_ns'
        
        return f"""SELECT
    {bucket_col} AS bucket_us,
    COUNT(*) as count,
    SUM(CASE 
        WHEN {duration_col} > 0 
        THEN (1000000000.0 / {duration_col}) * {bucket_col} / 1000000.0
        ELSE 0 
    END) as est_time_s"""
    
    def _get_histogram_group_by(self, time_granularity: Optional[str]) -> str:
        """Get GROUP BY clause for histogram query"""
        if time_granularity:
            groups = []
            if 'HH' in time_granularity:
                groups.append('HH')
            if 'MI' in time_granularity:
                groups.append('MI')
            if 'S10' in time_granularity:
                groups.append('S10')
            groups.append('lat_bucket_us')
            return ', '.join(groups)
        else:
            return 'bucket_us'
    
    def _get_histogram_order_by(self, time_granularity: Optional[str]) -> str:
        """Get ORDER BY clause for histogram query"""
        if time_granularity:
            orders = []
            if 'HH' in time_granularity:
                orders.append('HH')
            if 'MI' in time_granularity:
                orders.append('MI')
            if 'S10' in time_granularity:
                orders.append('S10')
            orders.append('lat_bucket_us')
            return ', '.join(orders)
        else:
            return 'bucket_us'
    
    def _determine_required_sources(self, columns: Set[str]) -> Set[str]:
        """Determine which data sources are needed based on columns"""
        required = {'samples'}  # Always need base samples
        
        for col in columns:
            col_lower = col.lower()
            # Check direct column mapping (case-insensitive)
            # First check lowercase version
            if col_lower in {k.lower() for k in self.COLUMN_SOURCE_MAP}:
                # Find the matching key case-insensitively
                for key, source in self.COLUMN_SOURCE_MAP.items():
                    if key.lower() == col_lower:
                        required.add(source)
                        # Add dependencies
                        if source == 'partitions':
                            required.add('iorqend')  # partitions requires iorqend
                        break
            # Check prefixed columns
            elif '.' in col_lower:
                prefix = col_lower.split('.')[0]
                if prefix == 'sc':
                    required.add('syscend')
                elif prefix == 'io':
                    required.add('iorqend')
                elif prefix == 'ks':
                    required.add('kstacks')
                elif prefix == 'us':
                    required.add('ustacks')
        
        return required
    
    def _build_enriched_samples_cte(self, low_time: Optional[datetime] = None,
                                    high_time: Optional[datetime] = None) -> str:
        """Build enriched_samples CTE with all computed columns"""
        # Load base samples
        if self.use_materialized:
            base_samples = "SELECT * FROM xtop_samples"
        else:
            # Get the optimized file pattern for the time range
            samples_pattern = self.csv_filter.get_hourly_files_in_range(
                'samples', low_time, high_time
            )
            # Use read_csv_auto with the specific files - pattern must be quoted
            base_samples = f"SELECT * FROM read_csv_auto('{samples_pattern}')"
        
        # Load computed columns
        computed_cols = self.fragments.load('computed_columns')
        
        return f"""    SELECT
        samples.*,
        {computed_cols}
    FROM ({base_samples}) AS samples"""
    
    def _build_base_samples_cte(self, required_sources: Set[str],
                                where_clause: str,
                                low_time: Optional[datetime],
                                high_time: Optional[datetime],
                                need_sc_histogram: bool,
                                need_io_histogram: bool) -> str:
        """Build base_samples CTE with JOINs and filters"""
        # Start with SELECT columns
        select_cols = ["es.*"]
        
        # Add columns from joined sources
        if 'syscend' in required_sources:
            select_cols.extend([
                "sc.duration_ns AS sc_duration_ns",
                "sc.type AS sc_type"
            ])
            if need_sc_histogram:
                # Add bucket calculation
                bucket_calc = self.fragments.load('histogram_buckets')
                bucket_calc = bucket_calc.replace('#DURATION_COLUMN#', 'sc.duration_ns')
                bucket_calc = bucket_calc.replace('lat_bkt_us', 'sc_lat_bkt_us')
                select_cols.append(bucket_calc)
        
        if 'iorqend' in required_sources:
            select_cols.extend([
                "io.duration_ns AS io_duration_ns",
                "io.service_ns AS io_service_ns",
                "io.queued_ns AS io_queued_ns",
                "io.bytes AS io_bytes",
                "io.dev_maj AS io_dev_maj",
                "io.dev_min AS io_dev_min"
            ])
            if need_io_histogram:
                # Add bucket calculation
                bucket_calc = self.fragments.load('histogram_buckets')
                bucket_calc = bucket_calc.replace('#DURATION_COLUMN#', 'io.duration_ns')
                bucket_calc = bucket_calc.replace('lat_bkt_us', 'io_lat_bkt_us')
                select_cols.append(bucket_calc)
        
        if 'kstacks' in required_sources:
            select_cols.extend([
                "ks.KSTACK_HASH",
                "ks.KSTACK_SYMS"
            ])
        
        if 'ustacks' in required_sources:
            select_cols.extend([
                "us.USTACK_HASH",
                "us.USTACK_SYMS"
            ])
        
        if 'partitions' in required_sources:
            select_cols.append("part.devname")
        
        # Build FROM clause
        from_clause = "FROM enriched_samples AS es"
        
        # Add JOINs
        if 'syscend' in required_sources:
            if self.use_materialized:
                from_clause += "\n    LEFT OUTER JOIN xtop_syscend sc"
            else:
                # Get optimized file pattern for syscend
                syscend_pattern = self.csv_filter.get_hourly_files_in_range(
                    'syscend', low_time, high_time
                )
                from_clause += f"\n    LEFT OUTER JOIN (SELECT * FROM read_csv_auto('{syscend_pattern}')) sc"
            from_clause += "\n        ON es.tid = sc.tid AND es.sysc_seq_num = sc.sysc_seq_num"
        
        if 'iorqend' in required_sources:
            if self.use_materialized:
                from_clause += "\n    LEFT OUTER JOIN xtop_iorqend io"
            else:
                # Get optimized file pattern for iorqend
                iorqend_pattern = self.csv_filter.get_hourly_files_in_range(
                    'iorqend', low_time, high_time
                )
                from_clause += f"\n    LEFT OUTER JOIN (SELECT * FROM read_csv_auto('{iorqend_pattern}')) io"
            from_clause += "\n        ON es.tid = io.insert_tid AND es.iorq_seq_num = io.iorq_seq_num"
        
        if 'kstacks' in required_sources:
            if self.use_materialized:
                from_clause += "\n    LEFT OUTER JOIN xtop_kstacks ks"
            else:
                # Get optimized file pattern for kstacks
                kstacks_pattern = self.csv_filter.get_hourly_files_in_range(
                    'kstacks', low_time, high_time
                )
                from_clause += f"\n    LEFT OUTER JOIN (SELECT * FROM read_csv_auto('{kstacks_pattern}')) ks"
            from_clause += "\n        ON es.kstack_hash = ks.KSTACK_HASH"
        
        if 'ustacks' in required_sources:
            if self.use_materialized:
                from_clause += "\n    LEFT OUTER JOIN xtop_ustacks us"
            else:
                # Get optimized file pattern for ustacks
                ustacks_pattern = self.csv_filter.get_hourly_files_in_range(
                    'ustacks', low_time, high_time
                )
                from_clause += f"\n    LEFT OUTER JOIN (SELECT * FROM read_csv_auto('{ustacks_pattern}')) us"
            from_clause += "\n        ON es.ustack_hash = us.USTACK_HASH"
        
        if 'partitions' in required_sources:
            if self.use_materialized:
                from_clause += "\n    LEFT OUTER JOIN xtop_partitions part"
            else:
                partitions_base = self.fragments.load('base_partitions')
                partitions_base = partitions_base.replace('#XTOP_DATADIR#', str(self.datadir))
                from_clause += f"\n    LEFT OUTER JOIN ({partitions_base}) part"
            from_clause += "\n        ON io.dev_maj = part.dev_maj AND io.dev_min = part.dev_min"
        
        # Build WHERE clause
        where_conditions = [f"({where_clause})"]
        
        # Add time filters
        if low_time:
            where_conditions.append(f"es.timestamp >= TIMESTAMP '{low_time.isoformat()}'")
        if high_time:
            where_conditions.append(f"es.timestamp < TIMESTAMP '{high_time.isoformat()}'")
        
        # Don't add duration filters here - they should only be in the histogram CTEs
        # This allows sample_counts to count ALL samples, not just those with I/O
        
        where_str = "\n        AND ".join(where_conditions)
        
        return f"""    SELECT
        {',\n        '.join(select_cols)}
    {from_clause}
    WHERE {where_str}"""
    
    def _build_sample_counts_cte(self, group_cols: List[str], 
                                 low_time: Optional[datetime],
                                 high_time: Optional[datetime],
                                 latency_columns: Optional[List[str]] = None) -> str:
        """Build CTE that pre-calculates sample counts and latency metrics to avoid multiplication from histogram JOINs"""
        # Build SELECT columns for grouping
        select_cols = []
        for col in group_cols:
            col_lower = col.lower()
            # Handle computed columns
            if col_lower == 'kstack_current_func':
                select_cols.append("""CASE 
        WHEN bs.KSTACK_SYMS IS NOT NULL AND bs.KSTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.KSTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END AS KSTACK_CURRENT_FUNC""")
            elif col_lower == 'ustack_current_func':
                select_cols.append("""CASE 
        WHEN bs.USTACK_SYMS IS NOT NULL AND bs.USTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.USTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END AS USTACK_CURRENT_FUNC""")
            else:
                select_cols.append(f"bs.{col}")
        
        # Add the count columns
        select_cols.append("COUNT(*) AS samples")
        
        # Add avg_threads calculation
        if low_time and high_time:
            select_cols.append(
                f"ROUND(COUNT(*) / EXTRACT(EPOCH FROM (TIMESTAMP '{high_time}' - TIMESTAMP '{low_time}')), 2) AS avg_threads"
            )
        else:
            select_cols.append("COUNT(*) AS avg_threads")
        
        # Add latency percentile columns if requested
        if latency_columns:
            for col in latency_columns:
                col_lower = col.lower()
                # Skip histogram columns (handled separately)
                if 'histogram' in col_lower:
                    continue
                # Handle percentile and other latency metrics
                if col.startswith('sc.'):
                    metric = col.split('.')[1]
                    if metric.startswith('p'):
                        percentile = metric[1:-3]  # Extract percentile number
                        select_cols.append(
                            f"ROUND(PERCENTILE_CONT(0.{percentile}) WITHIN GROUP (ORDER BY bs.sc_duration_ns) / 1000.0, 1) AS sc_{metric}"
                        )
                    elif metric == 'min_lat_us':
                        select_cols.append("ROUND(MIN(bs.sc_duration_ns) / 1000.0, 1) AS sc_min_lat_us")
                    elif metric == 'avg_lat_us':
                        select_cols.append("ROUND(AVG(bs.sc_duration_ns) / 1000.0, 1) AS sc_avg_lat_us")
                    elif metric == 'max_lat_us':
                        select_cols.append("ROUND(MAX(bs.sc_duration_ns) / 1000.0, 1) AS sc_max_lat_us")
                elif col.startswith('io.'):
                    metric = col.split('.')[1]
                    if metric.startswith('p'):
                        percentile = metric[1:-3]  # Extract percentile number
                        select_cols.append(
                            f"ROUND(PERCENTILE_CONT(0.{percentile}) WITHIN GROUP (ORDER BY bs.io_duration_ns) / 1000.0, 1) AS io_{metric}"
                        )
                    elif metric == 'min_lat_us':
                        select_cols.append("ROUND(MIN(bs.io_duration_ns) / 1000.0, 1) AS io_min_lat_us")
                    elif metric == 'avg_lat_us':
                        select_cols.append("ROUND(AVG(bs.io_duration_ns) / 1000.0, 1) AS io_avg_lat_us")
                    elif metric == 'max_lat_us':
                        select_cols.append("ROUND(MAX(bs.io_duration_ns) / 1000.0, 1) AS io_max_lat_us")
        
        # Build GROUP BY clause
        group_by_cols = []
        for col in group_cols:
            col_lower = col.lower()
            if col_lower == 'kstack_current_func':
                group_by_cols.append("""CASE 
        WHEN bs.KSTACK_SYMS IS NOT NULL AND bs.KSTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.KSTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END""")
            elif col_lower == 'ustack_current_func':
                group_by_cols.append("""CASE 
        WHEN bs.USTACK_SYMS IS NOT NULL AND bs.USTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.USTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END""")
            else:
                group_by_cols.append(f"bs.{col}")
        
        # Build the complete CTE
        if group_by_cols:
            return f"""    SELECT
        {',\n        '.join(select_cols)}
    FROM base_samples bs
    GROUP BY
        {',\n        '.join(group_by_cols)}"""
        else:
            # No grouping, just aggregate all
            return f"""    SELECT
        {',\n        '.join(select_cols)}
    FROM base_samples bs"""
    
    def _build_histogram_cte(self, prefix: str, group_cols: List[str],
                            duration_col: str, bucket_col: str) -> List[str]:
        """Build histogram aggregation CTEs"""
        ctes = []
        
        # Filter group columns to exclude aggregates (case-insensitive)
        hist_group_cols = [col for col in group_cols 
                          if col.lower() not in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']
                          and not col.lower().startswith('sc.') and not col.lower().startswith('io.')]
        
        # Build aggregation CTE
        agg_cte = f"""{prefix}_bucket_counts AS (
    SELECT
        {', '.join(hist_group_cols)},
        {bucket_col},
        COUNT(*) as cnt,
        SUM(CASE 
            WHEN {duration_col} > 0 
            THEN (1000000000.0 / {duration_col}) * {bucket_col} / 1000000.0
            ELSE 0 
        END) as est_time_s
    FROM base_samples
    WHERE {duration_col} > 0 AND {bucket_col} IS NOT NULL
    GROUP BY {', '.join(hist_group_cols)}, {bucket_col}
)"""
        ctes.append(agg_cte)
        
        # Build max calculation CTE
        max_cte = f"""{prefix}_bucket_with_max AS (
    SELECT 
        *,
        MAX(est_time_s) OVER () as {prefix}_global_max_time
    FROM {prefix}_bucket_counts
)"""
        ctes.append(max_cte)
        
        return ctes
    
    def _build_final_select(self, group_cols: List[str],
                           latency_columns: Optional[List[str]],
                           required_sources: Set[str],
                           need_sc_histogram: bool,
                           need_io_histogram: bool,
                           low_time: Optional[datetime],
                           high_time: Optional[datetime]) -> str:
        """Build the final SELECT clause"""
        select_parts = []
        
        # When we have histograms, use pre-calculated counts from sample_counts CTE
        has_histogram = need_sc_histogram or need_io_histogram
        
        # Add group columns (case-insensitive checks)
        for col in group_cols:
            col_lower = col.lower()
            if col_lower in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']:
                continue
            if col_lower.startswith('sc.') or col_lower.startswith('io.'):
                continue
            
            if has_histogram:
                # When using sample_counts CTE, reference columns from sc table
                select_parts.append(f"sc.{col}")
            else:
                # Handle stack current function columns (case-insensitive)
                if col_lower == 'kstack_current_func':
                    select_parts.append("""CASE 
        WHEN bs.KSTACK_SYMS IS NOT NULL AND bs.KSTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.KSTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END AS KSTACK_CURRENT_FUNC""")
                elif col_lower == 'ustack_current_func':
                    select_parts.append("""CASE 
        WHEN bs.USTACK_SYMS IS NOT NULL AND bs.USTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.USTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END AS USTACK_CURRENT_FUNC""")
                else:
                    select_parts.append(f"bs.{col}")
        
        # Add aggregate columns
        if has_histogram:
            # Use pre-calculated counts from sample_counts CTE
            select_parts.append("MAX(sc.samples) AS samples")
            select_parts.append("MAX(sc.avg_threads) AS avg_threads")
        else:
            select_parts.append("COUNT(*) AS samples")
            
            # avg_threads is computed as samples per second (rate over time period)
            if low_time and high_time:
                # Calculate the time difference in seconds using DuckDB's EXTRACT function
                select_parts.append(
                    f"ROUND(COUNT(*) / EXTRACT(EPOCH FROM (TIMESTAMP '{high_time}' - TIMESTAMP '{low_time}')), 2) AS avg_threads"
                )
            else:
                # Fallback when time range is not provided
                select_parts.append("COUNT(*) AS avg_threads")
        
        # Add latency columns
        if latency_columns:
            for col in latency_columns:
                col_lower = col.lower()
                if col_lower == 'sclat_histogram' and need_sc_histogram:
                    select_parts.append(self._build_histogram_select('sc'))
                elif col_lower == 'iolat_histogram' and need_io_histogram:
                    select_parts.append(self._build_histogram_select('io'))
                elif col.startswith('sc.') and 'syscend' in required_sources:
                    metric = col.split('.')[1]
                    select_parts.append(self._build_latency_metric('sc', metric, has_histogram))
                elif col.startswith('io.') and 'iorqend' in required_sources:
                    metric = col.split('.')[1]
                    select_parts.append(self._build_latency_metric('io', metric, has_histogram))
        
        return f"SELECT\n    {',\n    '.join(select_parts)}"
    
    def _build_histogram_select(self, prefix: str) -> str:
        """Build histogram aggregation in SELECT"""
        # Build the histogram aggregation using STRING_AGG
        bucket_col = f"{prefix}_lat_bkt_us"
        histogram_agg = f"""STRING_AGG(
        {prefix}_bc.{bucket_col}::VARCHAR || ':' || 
        {prefix}_bc.cnt::VARCHAR || ':' || 
        {prefix}_bc.est_time_s::VARCHAR || ':' ||
        {prefix}_bc.{prefix}_global_max_time::VARCHAR,
        ',' ORDER BY {prefix}_bc.{bucket_col}
    ) AS {prefix}lat_histogram"""
        return histogram_agg
    
    def _build_latency_metric(self, prefix: str, metric: str, has_histogram: bool = False) -> str:
        """Build latency metric calculation
        
        Args:
            prefix: 'sc' for syscall or 'io' for I/O
            metric: The metric name (min_lat_us, p99_us, etc.)
            has_histogram: If True, the metric is already calculated in sample_counts CTE
        """
        if has_histogram:
            # When we have histograms, these metrics are pre-calculated in sample_counts CTE
            # Just reference them with MAX() aggregation
            return f"MAX(sc.{prefix}_{metric}) AS {prefix}_{metric}"
        else:
            # Normal case - we have base_samples available
            duration_col = f"bs.{prefix}_duration_ns"
            
            if metric == 'min_lat_us':
                return f"ROUND(MIN({duration_col}) / 1000.0, 1) AS {prefix}_min_lat_us"
            elif metric == 'avg_lat_us':
                return f"ROUND(AVG({duration_col}) / 1000.0, 1) AS {prefix}_avg_lat_us"
            elif metric == 'max_lat_us':
                return f"ROUND(MAX({duration_col}) / 1000.0, 1) AS {prefix}_max_lat_us"
            elif metric.startswith('p'):
                percentile = metric[1:-3]  # Extract percentile number
                return f"ROUND(PERCENTILE_CONT(0.{percentile}) WITHIN GROUP (ORDER BY {duration_col}) / 1000.0, 1) AS {prefix}_{metric}"
            else:
                return f"'-' AS {prefix}_{metric}"
    
    def _build_group_by(self, group_cols: List[str], required_sources: Set[str], 
                        has_histogram: bool = False) -> str:
        """Build GROUP BY clause"""
        group_by_cols = []
        
        for col in group_cols:
            col_lower = col.lower()
            if col_lower in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram']:
                continue
            if col_lower.startswith('sc.') or col_lower.startswith('io.'):
                continue
            
            if has_histogram:
                # When using sample_counts CTE, reference columns from sc table
                group_by_cols.append(f"sc.{col}")
            else:
                # Handle computed columns in GROUP BY (case-insensitive)
                if col_lower == 'kstack_current_func':
                    group_by_cols.append("""CASE 
        WHEN bs.KSTACK_SYMS IS NOT NULL AND bs.KSTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.KSTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END""")
                elif col_lower == 'ustack_current_func':
                    group_by_cols.append("""CASE 
        WHEN bs.USTACK_SYMS IS NOT NULL AND bs.USTACK_SYMS != ''
        THEN SPLIT_PART(SPLIT_PART(bs.USTACK_SYMS, ';', 1), '+', 1)
        ELSE '-'
    END""")
                else:
                    group_by_cols.append(f"bs.{col}")
        
        if group_by_cols:
            return f"GROUP BY\n    {',\n    '.join(group_by_cols)}"
        else:
            return ""