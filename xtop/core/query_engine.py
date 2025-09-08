#!/usr/bin/env python3
"""
Query processing engine for xcapture data.
Handles SQL template loading, placeholder replacement, and query execution.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
import time
import sys
import logging
import re
from .data_source import XCaptureDataSource
from .query_builder import QueryBuilder
from .materializer import DataMaterializer


@dataclass
class QueryParams:
    """Parameters for query execution"""
    where_clause: str = "1=1"
    group_cols: List[str] = field(default_factory=list)
    low_time: Optional[datetime] = None
    high_time: Optional[datetime] = None
    limit: Optional[int] = None
    # Removed query_type - always uses dynamic queries now


@dataclass
class QueryResult:
    """Query execution results"""
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    execution_time: float
    # Removed query_type - always 'dynamic' now


class QueryEngine:
    """Processes SQL queries against xcapture data"""
    
    # Default group columns - now only one set for dynamic queries (all lowercase)
    DEFAULT_GROUP_COLS = {
        'dynamic': ['state', 'username', 'exe', 'comm', 'syscall', 'filename', 'extra_info']
    }
    
    # Map of data sources to their fragment files and dependencies
    DATA_SOURCES = {
        'samples': {
            'fragment': 'get_samples.sql',
            'alias': 'samples',
            'depends_on': [],
            'is_base': True
        },
        'syscend': {
            'fragment': 'get_syscend.sql',
            'alias': 'sc',
            'depends_on': [],
            'is_base': False
        },
        'iorqend': {
            'fragment': 'get_iorqend.sql',
            'alias': 'io',
            'depends_on': [],
            'is_base': False
        },
        'kstacks': {
            'fragment': 'get_kstacks.sql',
            'alias': 'ks',
            'depends_on': [],
            'is_base': False
        },
        'ustacks': {
            'fragment': 'get_ustacks.sql',
            'alias': 'us',
            'depends_on': [],
            'is_base': False
        },
        'partitions': {
            'fragment': 'get_partitions.sql',
            'alias': 'part',
            'depends_on': ['iorqend'],  # Requires iorqend for dev_maj/dev_min
            'is_base': False
        }
    }
    
    def __init__(self, data_source: XCaptureDataSource, use_materialized: bool = False):
        """Initialize with data source"""
        self.data_source = data_source
        self.query_cache = {}
        # Get the SQL directory relative to this file
        self.template_path = Path(__file__).parent.parent / 'sql'
        self.fragments_path = self.template_path / 'fragments'
        self.logger = logging.getLogger('xtop.query_engine')
        
        # Initialize the new query builder
        self.query_builder = QueryBuilder(
            datadir=data_source.datadir,
            fragments_path=self.fragments_path,
            use_materialized=use_materialized
        )
        
        # Initialize materializer
        self.materializer = DataMaterializer(data_source.conn, data_source.datadir)
        self.use_materialized = use_materialized
        
        # Cache for schema information
        self.schema_cache: Dict[str, List[Tuple[str, str]]] = {}
        self._discover_all_schemas()
    
    # Removed load_template method - no longer needed with only dynamic queries
    
    def prepare_query(self, params: QueryParams, latency_columns: Optional[List[str]] = None) -> str:
        """Build dynamic query based on requested columns"""
        # Always use dynamic query builder now
        return self.prepare_dynamic_query(params, latency_columns)
    
    def execute(self, query: str, params: QueryParams = None, 
                debug: bool = False, debug_profile: bool = False) -> QueryResult:
        """Execute query and return results"""
        if debug or debug_profile:
            self.logger.debug("\n" + "="*80)
            self.logger.debug("DEBUG SQL: About to execute the following query:")
            self.logger.debug("="*80)
            self.logger.debug(query)
            self.logger.debug("="*80)
        
        conn = self.data_source.connect()
        
        # Enable profiling if requested
        if debug_profile:
            conn.execute("PRAGMA enable_profiling")
            conn.execute("PRAGMA profiling_mode='standard'")
        
        start_time = time.time()
        
        try:
            result = conn.execute(query)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            
            # Disable profiling after query execution
            if debug_profile:
                conn.execute("PRAGMA disable_profiling")
            
            # Convert to list of dicts
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            execution_time = time.time() - start_time
            
            if debug:
                self.logger.debug(f"Query returned {len(data)} rows in {execution_time:.3f}s")
            
            return QueryResult(
                data=data,
                columns=columns,
                row_count=len(data),
                execution_time=execution_time
            )
            
        except Exception as e:
            print(f"Error executing query: {e}", file=sys.stderr)
            raise
    
    def execute_with_params(self, params: QueryParams, debug: bool = False, 
                           debug_profile: bool = False, latency_columns: Optional[List[str]] = None) -> QueryResult:
        """Prepare and execute query with given parameters"""
        query = self.prepare_query(params, latency_columns)
        return self.execute(query, params, debug, debug_profile)
    
    def get_available_columns(self, params: QueryParams = None) -> List[str]:
        """
        Get available columns for dynamic query.
        Executes the query with LIMIT 0 and DESCRIBE to get column info.
        """
        if params is None:
            params = QueryParams()
        
        # Prepare query with LIMIT 0
        original_limit = params.limit
        params.limit = 0
        query = self.prepare_query(params)
        params.limit = original_limit
        
        # Remove any existing LIMIT clause and add LIMIT 0
        import re
        query = re.sub(r'\s+LIMIT\s+\d+\s*$', '', query, flags=re.IGNORECASE)
        query = query.rstrip().rstrip(';')
        
        # Use DESCRIBE to get column info
        describe_query = f"DESCRIBE ({query} LIMIT 0)"
        
        conn = self.data_source.connect()
        try:
            result = conn.execute(describe_query).fetchall()
            return [row[0] for row in result]
        except Exception as e:
            print(f"Error getting columns: {e}", file=sys.stderr)
            return []
    
    def lookup_stack_trace(self, stack_hash: str, is_kernel: bool = True) -> Optional[str]:
        """Look up a stack trace by its hash from kstacks/ustacks CSV"""
        csv_type = 'kstacks' if is_kernel else 'ustacks'
        csv_pattern = f'xcapture_{csv_type}_*.csv'
        csv_path = str(self.data_source.datadir / csv_pattern)
        
        # Use the correct column names based on stack type
        hash_col = 'KSTACK_HASH' if is_kernel else 'USTACK_HASH'
        syms_col = 'KSTACK_SYMS' if is_kernel else 'USTACK_SYMS'
        
        query = f"""
        SELECT {syms_col} 
        FROM read_csv_auto('{csv_path}')
        WHERE {hash_col} = '{stack_hash}'
        LIMIT 1
        """
        
        conn = self.data_source.connect()
        try:
            result = conn.execute(query).fetchone()
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error looking up stack trace: {e}")
            return None
    
    def clear_cache(self):
        """Clear the query template cache"""
        self.query_cache.clear()
        if hasattr(self, 'query_builder'):
            self.query_builder.fragments.clear_cache()
    
    def materialize_data(self, sources: Optional[List[str]] = None) -> Dict[str, float]:
        """Materialize CSV data into DuckDB tables for performance"""
        return self.materializer.materialize_all(sources)
    
    def drop_materialized_data(self):
        """Drop all materialized tables"""
        self.materializer.drop_all()
    
    def set_use_materialized(self, use_materialized: bool):
        """Toggle between materialized tables and CSV files"""
        self.use_materialized = use_materialized
        self.query_builder.use_materialized = use_materialized
    
    def _discover_all_schemas(self):
        """Discover schemas for all data sources"""
        for source_name, source_info in self.DATA_SOURCES.items():
            if source_name == 'partitions':
                # Special handling for partitions - hardcode the schema
                # The partitions file requires special parsing, so we can't auto-discover
                self.schema_cache[source_name] = [
                    ('dev_maj', 'INTEGER'),
                    ('dev_min', 'INTEGER'),
                    ('devname', 'VARCHAR')
                ]
                continue
                
            # Build a simple query to get schema
            fragment_path = self.fragments_path / source_info['fragment']
            if not fragment_path.exists():
                self.logger.warning(f"Fragment file not found: {fragment_path}")
                continue
                
            with open(fragment_path, 'r') as f:
                fragment = f.read()
            
            # Extract the SELECT statement from the fragment
            if source_info['is_base']:
                # Base query - use directly
                query = fragment.replace('#XTOP_DATADIR#', str(self.data_source.datadir))
            else:
                # Extract the SELECT from within the JOIN
                match = re.search(r'SELECT.*?FROM\s+read_csv_auto\([^)]+\)', fragment, re.DOTALL | re.IGNORECASE)
                if match:
                    query = match.group(0).replace('#XTOP_DATADIR#', str(self.data_source.datadir))
                else:
                    self.logger.warning(f"Could not extract SELECT from fragment: {source_name}")
                    continue
            
            # Get schema using DESCRIBE
            describe_query = f"DESCRIBE ({query} LIMIT 0)"
            
            try:
                conn = self.data_source.connect()
                result = conn.execute(describe_query).fetchall()
                self.schema_cache[source_name] = [(row[0], row[1]) for row in result]
                self.logger.debug(f"Discovered schema for {source_name}: {len(result)} columns")
            except Exception as e:
                self.logger.error(f"Error discovering schema for {source_name}: {e}")
                self.schema_cache[source_name] = []
    
    def get_column_to_source_mapping(self) -> Dict[str, str]:
        """Get mapping of column names to their source data files"""
        mapping = {}
        
        for source_name, columns in self.schema_cache.items():
            alias = self.DATA_SOURCES[source_name]['alias']
            for col_name, _ in columns:
                # Handle column name conflicts by prefixing with source alias
                if col_name in mapping and mapping[col_name] != source_name:
                    # This column exists in multiple sources
                    prefixed_name = f"{alias}.{col_name}"
                    mapping[prefixed_name] = source_name
                else:
                    mapping[col_name] = source_name
        
        return mapping
    
    def get_columns_by_source(self) -> Dict[str, List[str]]:
        """Get columns grouped by their source"""
        result = {}
        
        for source_name, columns in self.schema_cache.items():
            result[source_name] = [col[0] for col in columns]
        
        return result
    
    def _determine_required_sources(self, columns: Set[str]) -> Set[str]:
        """Determine which data sources are needed based on requested columns"""
        required_sources = {'samples'}  # Always need the base source
        column_mapping = self.get_column_to_source_mapping()
        
        # Check which sources are needed for the requested columns
        for col in columns:
            # Handle prefixed columns (e.g., "sc.duration_ns")
            if '.' in col:
                prefix = col.split('.')[0]
                # Find source by alias
                for src_name, src_info in self.DATA_SOURCES.items():
                    if src_info['alias'] == prefix:
                        required_sources.add(src_name)
                        # Add dependencies
                        for dep in src_info['depends_on']:
                            required_sources.add(dep)
                        break
            else:
                source = column_mapping.get(col)
                if source:
                    required_sources.add(source)
                    # Add dependencies
                    for dep in self.DATA_SOURCES[source]['depends_on']:
                        required_sources.add(dep)
        
        # Add computed columns dependencies
        if 'kstack_current_func' in columns:
            required_sources.add('kstacks')
        if 'ustack_current_func' in columns:
            required_sources.add('ustacks')
        
        # Add dependencies for latency columns
        syscall_latency_cols = {'sc.min_lat_us', 'sc.avg_lat_us', 'sc.max_lat_us', 
                               'sc.p50_us', 'sc.p95_us', 'sc.p99_us', 'sc.p999_us', 'sclat_histogram'}
        io_latency_cols = {'io.min_lat_us', 'io.avg_lat_us', 'io.max_lat_us',
                          'io.p50_us', 'io.p95_us', 'io.p99_us', 'io.p999_us', 'iolat_histogram'}
        
        if any(col in columns for col in syscall_latency_cols):
            required_sources.add('syscend')
        if any(col in columns for col in io_latency_cols):
            required_sources.add('iorqend')
        
        return required_sources
    
    def _load_fragment(self, source_name: str) -> str:
        """Load SQL fragment for a data source"""
        fragment_file = self.fragments_path / self.DATA_SOURCES[source_name]['fragment']
        
        if not fragment_file.exists():
            raise FileNotFoundError(f"Fragment file not found: {fragment_file}")
        
        with open(fragment_file, 'r') as f:
            return f.read()
    
    def build_dynamic_query(self, params: QueryParams, requested_columns: List[str], 
                           latency_columns: Optional[List[str]] = None) -> str:
        """Build a dynamic query based on requested columns with proper histogram support"""
        # Standardize column names to lowercase
        requested_columns = [col.lower() for col in requested_columns]
        # Convert requested columns to set for analysis
        columns_set = set(requested_columns)
        
        # Add standard computed columns
        columns_set.update(['samples', 'avg_threads'])
        
        # Add latency columns if provided (standardize to lowercase)
        if latency_columns:
            columns_set.update([col.lower() for col in latency_columns])
        
        # Determine required data sources
        required_sources = self._determine_required_sources(columns_set)
        
        # Check if we need histograms (lowercase comparison)
        need_sc_histogram = 'sclat_histogram' in columns_set
        need_io_histogram = 'iolat_histogram' in columns_set
        
        # Time range for the query
        low_time = (params.low_time or (datetime.now() - timedelta(hours=1))).isoformat()
        high_time = (params.high_time or datetime.now()).isoformat()
        
        # Start building the query
        query_parts = []
        
        # Build base CTE with all joins and bucket calculations
        base_select = ["samples.*"]
        
        # Add computed columns that might be needed
        computed_column_defs = {
            'filenamesum': "REGEXP_REPLACE(samples.FILENAME, '[0-9]+', '*', 'g') as filenamesum",
            'comm2': """CASE 
                WHEN samples.COMM LIKE 'ora_p%' 
                THEN regexp_replace(samples.COMM, '(?:p[0-9a-z]+_)', 'p*_', 'g')
                ELSE regexp_replace(samples.COMM, '[0-9]+', '*', 'g')
            END as comm2""",
            # Stack-related computed columns (these are computed in SELECT, not available in base_samples)
            'KSTACK_CURRENT_FUNC': 'KSTACK_CURRENT_FUNC',
            'USTACK_CURRENT_FUNC': 'USTACK_CURRENT_FUNC'
        }
        
        # Add any computed columns that are requested
        for col in requested_columns:
            if col in computed_column_defs:
                base_select.append(computed_column_defs[col])
        
        if 'syscend' in required_sources:
            base_select.extend([
                "sc.tid AS sc_tid",
                "sc.duration_ns AS sc_duration_ns",
                "sc.type AS sc_type"
            ])
            if need_sc_histogram:
                base_select.append(
                    "POWER(2, CEIL(LOG2(CASE WHEN sc.duration_ns <= 0 THEN NULL ELSE CEIL(sc.duration_ns / 1000) END)))::bigint AS sc_lat_bkt_us"
                )
        
        if 'iorqend' in required_sources:
            base_select.extend([
                "io.duration_ns AS io_duration_ns",
                "io.dev_maj AS io_dev_maj",
                "io.dev_min AS io_dev_min"
            ])
            if need_io_histogram:
                base_select.append(
                    "POWER(2, CEIL(LOG2(CASE WHEN io.duration_ns <= 0 THEN NULL ELSE CEIL(io.duration_ns / 1000) END)))::bigint AS io_lat_bkt_us"
                )
        
        if 'kstacks' in required_sources:
            base_select.append("ks.kstack_syms")
            base_select.append("ks.kstack_hash")
        
        if 'ustacks' in required_sources:
            base_select.append("us.ustack_syms")
            base_select.append("us.ustack_hash")
        
        if 'partitions' in required_sources and 'iorqend' in required_sources:
            base_select.append("part.devname")
        
        # Build FROM clause with joins
        from_clause = f"FROM read_csv_auto('{self.data_source.datadir}/xcapture_samples_*.csv') AS samples"
        
        # Add joins for required sources
        join_order = ['syscend', 'iorqend', 'kstacks', 'ustacks', 'partitions']
        for source in join_order:
            if source in required_sources and source != 'samples':
                fragment = self._load_fragment(source)
                fragment = fragment.replace('#XTOP_DATADIR#', str(self.data_source.datadir))
                from_clause += "\n" + fragment
        
        # First CTE: base_samples with all data
        where_conditions = [f"({params.where_clause})"]
        where_conditions.append(f"samples.timestamp >= TIMESTAMP '{low_time}'")
        where_conditions.append(f"samples.timestamp < TIMESTAMP '{high_time}'")
        
        # Add duration filters if histograms are needed
        if need_sc_histogram:
            where_conditions.append("sc.duration_ns > 0")
        if need_io_histogram:
            where_conditions.append("io.duration_ns > 0")
        
        query_parts.append(f"""WITH base_samples AS (
    SELECT
        {chr(10)+'        , '.join(base_select)}
    {from_clause}
    WHERE {' AND '.join(where_conditions)}
)""")
        
        # If we need histograms, add bucket calculation CTEs
        if need_sc_histogram or need_io_histogram:
            # Get group columns for histogram aggregation
            group_cols = [col for col in requested_columns if col not in ['samples', 'avg_threads'] and not col.startswith('sc.') and not col.startswith('io.') and col not in ['sclat_histogram', 'iolat_histogram']]
            
            if need_sc_histogram:
                query_parts.append(f""", sc_bucket_counts AS (
    SELECT
        {', '.join(group_cols + ['sc_lat_bkt_us'])},
        COUNT(*) as cnt,
        SUM(CASE 
            WHEN sc_duration_ns > 0 
            THEN (1000000000.0 / sc_duration_ns) * sc_lat_bkt_us / 1000000.0
            ELSE 0 
        END) as est_time_s
    FROM base_samples
    WHERE sc_duration_ns > 0
    GROUP BY {', '.join(group_cols + ['sc_lat_bkt_us'])}
), sc_bucket_with_max AS (
    SELECT 
        *,
        MAX(est_time_s) OVER () as sc_global_max_time
    FROM sc_bucket_counts
)""")
            
            if need_io_histogram:
                query_parts.append(f""", io_bucket_counts AS (
    SELECT
        {', '.join(group_cols + ['io_lat_bkt_us'])},
        COUNT(*) as cnt,
        SUM(CASE 
            WHEN io_duration_ns > 0 
            THEN (1000000000.0 / io_duration_ns) * io_lat_bkt_us / 1000000.0
            ELSE 0 
        END) as est_time_s
    FROM base_samples
    WHERE io_duration_ns > 0
    GROUP BY {', '.join(group_cols + ['io_lat_bkt_us'])}
), io_bucket_with_max AS (
    SELECT 
        *,
        MAX(est_time_s) OVER () as io_global_max_time
    FROM io_bucket_counts
)""")
        
        # Build final SELECT
        select_parts = []
        
        # Add requested group columns
        for col in requested_columns:
            if col in ['samples', 'avg_threads', 'sclat_histogram', 'iolat_histogram'] or col.startswith('sc.') or col.startswith('io.'):
                continue
            
            # Add computed columns
            if col == 'KSTACK_CURRENT_FUNC' and 'kstacks' in required_sources:
                select_parts.append("""CASE 
                WHEN bs.kstack_syms IS NOT NULL AND bs.kstack_syms != ''
                THEN SPLIT_PART(SPLIT_PART(bs.kstack_syms, ';', 1), '+', 1)
                ELSE '-'
            END AS KSTACK_CURRENT_FUNC""")
            elif col == 'USTACK_CURRENT_FUNC' and 'ustacks' in required_sources:
                select_parts.append("""CASE 
                WHEN bs.ustack_syms IS NOT NULL AND bs.ustack_syms != ''
                THEN SPLIT_PART(SPLIT_PART(bs.ustack_syms, ';', 1), '+', 1)
                ELSE '-'
            END AS USTACK_CURRENT_FUNC""")
            elif '.' in col:
                # Column already has a qualifier (e.g., samples.KSTACK_HASH), use as-is
                select_parts.append(col)
            else:
                select_parts.append(f"bs.{col}")
        
        # Add histogram aggregations
        if need_sc_histogram:
            select_parts.append("""STRING_AGG(
        scb.sc_lat_bkt_us::VARCHAR || ':' || 
        scb.cnt::VARCHAR || ':' || 
        scb.est_time_s::VARCHAR || ':' ||
        scb.sc_global_max_time::VARCHAR,
        ',' ORDER BY scb.sc_lat_bkt_us
    ) AS SCLAT_HISTOGRAM""")
        
        if need_io_histogram:
            select_parts.append("""STRING_AGG(
        iob.io_lat_bkt_us::VARCHAR || ':' || 
        iob.cnt::VARCHAR || ':' || 
        iob.est_time_s::VARCHAR || ':' ||
        iob.io_global_max_time::VARCHAR,
        ',' ORDER BY iob.io_lat_bkt_us
    ) AS IOLAT_HISTOGRAM""")
        
        # Add aggregates
        select_parts.append("COUNT(*) AS samples")
        select_parts.append(f"ROUND(COUNT(*) / EXTRACT(EPOCH FROM (TIMESTAMP '{high_time}' - TIMESTAMP '{low_time}')), 2) AS avg_threads")
        
        # Add latency statistics
        if 'syscend' in required_sources:
            if 'sc.min_lat_us' in columns_set:
                select_parts.append("ROUND(MIN(bs.sc_duration_ns) / 1000) AS \"sc.min_lat_us\"")
            if 'sc.avg_lat_us' in columns_set:
                select_parts.append("ROUND(AVG(bs.sc_duration_ns) / 1000) AS \"sc.avg_lat_us\"")
            if 'sc.max_lat_us' in columns_set:
                select_parts.append("ROUND(MAX(bs.sc_duration_ns) / 1000) AS \"sc.max_lat_us\"")
            if 'sc.p50_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY bs.sc_duration_ns) / 1000) AS \"sc.p50_us\"")
            if 'sc.p95_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY bs.sc_duration_ns) / 1000) AS \"sc.p95_us\"")
            if 'sc.p99_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY bs.sc_duration_ns) / 1000) AS \"sc.p99_us\"")
            if 'sc.p999_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY bs.sc_duration_ns) / 1000) AS \"sc.p999_us\"")
        
        if 'iorqend' in required_sources:
            if 'io.min_lat_us' in columns_set:
                select_parts.append("ROUND(MIN(bs.io_duration_ns) / 1000) AS \"io.min_lat_us\"")
            if 'io.avg_lat_us' in columns_set:
                select_parts.append("ROUND(AVG(bs.io_duration_ns) / 1000) AS \"io.avg_lat_us\"")
            if 'io.max_lat_us' in columns_set:
                select_parts.append("ROUND(MAX(bs.io_duration_ns) / 1000) AS \"io.max_lat_us\"")
            if 'io.p50_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY bs.io_duration_ns) / 1000) AS \"io.p50_us\"")
            if 'io.p95_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY bs.io_duration_ns) / 1000) AS \"io.p95_us\"")
            if 'io.p99_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY bs.io_duration_ns) / 1000) AS \"io.p99_us\"")
            if 'io.p999_us' in columns_set:
                select_parts.append("ROUND(PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY bs.io_duration_ns) / 1000) AS \"io.p999_us\"")
        
        # Build FROM clause for final query
        if need_sc_histogram or need_io_histogram:
            final_from = "FROM base_samples bs"
            if need_sc_histogram:
                final_from += f"\nLEFT JOIN sc_bucket_with_max scb USING ({', '.join(group_cols)})"  
            if need_io_histogram:
                final_from += f"\nLEFT JOIN io_bucket_with_max iob USING ({', '.join(group_cols)})"
            
            # Build GROUP BY clause, handling computed columns
            group_by_cols = []
            for col in group_cols:
                if col in computed_column_defs:
                    # Computed columns don't need bs. prefix
                    group_by_cols.append(col)
                elif '.' in col:
                    # Column already has a qualifier (e.g., samples.KSTACK_HASH), don't add bs.
                    group_by_cols.append(col)
                else:
                    group_by_cols.append(f'bs.{col}')
            
            # Complete the query
            query_parts.append(f"""
SELECT
    {chr(10)+'    , '.join(select_parts)}
{final_from}
GROUP BY {', '.join(group_by_cols)}
ORDER BY samples DESC
LIMIT {params.limit or 30}""")
        else:
            # Simple query without histograms
            # Build GROUP BY clause, handling computed columns
            group_by_cols = []
            for col in requested_columns:
                if col in ['samples', 'avg_threads'] or col.startswith('sc.') or col.startswith('io.'):
                    continue
                if col in computed_column_defs:
                    # Computed columns don't need bs. prefix
                    group_by_cols.append(col)
                elif '.' in col:
                    # Column already has a qualifier (e.g., samples.KSTACK_HASH), don't add bs.
                    group_by_cols.append(col)
                else:
                    group_by_cols.append(f'bs.{col}')
            
            query_parts.append(f"""
SELECT
    {chr(10)+'    , '.join(select_parts)}
FROM base_samples bs
GROUP BY {', '.join(group_by_cols)}
ORDER BY samples DESC
LIMIT {params.limit or 30}""")
        
        return '\n'.join(query_parts)
    
    def prepare_dynamic_query(self, params: QueryParams, latency_columns: Optional[List[str]] = None) -> str:
        """Prepare a dynamic query based on requested columns"""
        # Use group_cols to determine which columns are requested
        if not params.group_cols:
            params.group_cols = self.DEFAULT_GROUP_COLS.get('dynamic', [])
        
        # Use the new query builder
        return self.query_builder.build_dynamic_query(
            group_cols=params.group_cols,
            where_clause=params.where_clause,
            low_time=params.low_time,
            high_time=params.high_time,
            latency_columns=latency_columns,
            limit=params.limit
        )