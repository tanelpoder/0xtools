#!/usr/bin/env python3
"""
SQL Fragment Manager - Centralized management of SQL query fragments.
Provides a cleaner interface for building dynamic SQL queries.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path


class SQLFragmentManager:
    """Manages SQL fragments for dynamic query building"""
    
    def __init__(self, fragment_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """Initialize the fragment manager
        
        Args:
            fragment_dir: Directory containing SQL fragment files
            logger: Optional logger
        """
        self.logger = logger or logging.getLogger(__name__)
        self.fragment_dir = fragment_dir or Path(__file__).parent / "fragments"
        self._fragments_cache = {}
        self._load_fragments()
    
    def _load_fragments(self) -> None:
        """Load all SQL fragments into memory"""
        if not self.fragment_dir.exists():
            if self.logger:
                self.logger.warning(f"Fragment directory not found: {self.fragment_dir}")
            return
        
        for fragment_file in self.fragment_dir.glob("*.sql"):
            try:
                fragment_name = fragment_file.stem
                fragment_content = fragment_file.read_text()
                self._fragments_cache[fragment_name] = fragment_content
                
                if self.logger:
                    self.logger.debug(f"Loaded fragment: {fragment_name}")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error loading fragment {fragment_file}: {e}")
    
    def get_fragment(self, name: str) -> str:
        """Get a SQL fragment by name
        
        Args:
            name: Fragment name (without .sql extension)
            
        Returns:
            SQL fragment content
        """
        if name not in self._fragments_cache:
            # Try to load it dynamically
            fragment_file = self.fragment_dir / f"{name}.sql"
            if fragment_file.exists():
                try:
                    self._fragments_cache[name] = fragment_file.read_text()
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Error loading fragment {name}: {e}")
                    return f"-- Fragment {name} not found"
        
        return self._fragments_cache.get(name, f"-- Fragment {name} not found")
    
    def build_with_clause(self, required_ctes: List[str]) -> str:
        """Build a WITH clause with required CTEs
        
        Args:
            required_ctes: List of CTE names needed
            
        Returns:
            Complete WITH clause
        """
        if not required_ctes:
            return ""
        
        cte_parts = []
        for cte_name in required_ctes:
            fragment = self.get_fragment(f"cte_{cte_name}")
            if fragment and not fragment.startswith("--"):
                cte_parts.append(f"{cte_name} AS (\n{fragment}\n)")
        
        if not cte_parts:
            return ""
        
        return "WITH " + ",\n".join(cte_parts)
    
    def build_enriched_samples(self, 
                              use_materialized: bool = False,
                              datadir: str = "out") -> str:
        """Build enriched_samples CTE
        
        Args:
            use_materialized: Whether to use materialized tables
            datadir: Data directory path
            
        Returns:
            Enriched samples CTE
        """
        # Get base samples source
        if use_materialized:
            samples_source = "SELECT * FROM xcapture_samples"
        else:
            samples_source = self.get_fragment("base_samples").replace("{datadir}", datadir)
        
        # Get computed columns
        computed_cols = self.get_fragment("computed_columns")
        
        # Combine
        return f"""enriched_samples AS (
    SELECT
        samples.*,
        {computed_cols}
    FROM ({samples_source}) AS samples
)"""
    
    def build_join_clause(self, required_joins: List[str], base_alias: str = "bs") -> str:
        """Build JOIN clauses for required data sources
        
        Args:
            required_joins: List of join types (syscend, iorqend, kstacks, ustacks)
            base_alias: Alias for the base table
            
        Returns:
            JOIN clause string
        """
        join_parts = []
        
        for join_type in required_joins:
            if join_type == "syscend":
                join_parts.append(f"""
    LEFT JOIN syscend_data sc ON {base_alias}.tid = sc.tid 
        AND {base_alias}.timestamp = sc.timestamp""")
            
            elif join_type == "iorqend":
                join_parts.append(f"""
    LEFT JOIN iorqend_data io ON {base_alias}.tid = io.insert_tid 
        AND {base_alias}.timestamp = io.timestamp""")
            
            elif join_type == "kstacks":
                join_parts.append(f"""
    LEFT JOIN kstacks_data ks ON {base_alias}.kstack_hash = ks.stack_hash""")
            
            elif join_type == "ustacks":
                join_parts.append(f"""
    LEFT JOIN ustacks_data us ON {base_alias}.ustack_hash = us.stack_hash""")
        
        return "\n".join(join_parts)
    
    def build_histogram_aggregation(self, 
                                   histogram_type: str,
                                   group_cols: List[str]) -> str:
        """Build histogram aggregation SQL
        
        Args:
            histogram_type: Type of histogram (SCLAT or IOLAT)
            group_cols: GROUP BY columns
            
        Returns:
            Histogram aggregation SQL
        """
        if histogram_type == "SCLAT":
            latency_col = "sc.sysc_latency_us"
            count_col = "COUNT(*)"
        else:  # IOLAT
            latency_col = "io.iorq_latency_us"
            count_col = "COUNT(*)"
        
        # Build histogram buckets
        buckets = self.get_fragment("histogram_buckets")
        
        # Build aggregation
        group_by = ", ".join(group_cols) if group_cols else "1"
        
        return f"""
    STRING_AGG(
        CASE 
            WHEN {latency_col} IS NOT NULL THEN
                {buckets}.format_bucket({latency_col}) || ':' ||
                {count_col} || ':' ||
                SUM({latency_col} / 1000000.0) || ':' ||
                MAX({latency_col})
            ELSE NULL
        END,
        ',' ORDER BY {buckets}.bucket_order({latency_col})
    ) AS {histogram_type}_HISTOGRAM"""
    
    def build_percentile_columns(self, 
                                percentiles: List[int],
                                latency_source: str) -> List[str]:
        """Build percentile column definitions
        
        Args:
            percentiles: List of percentile values (e.g., [50, 95, 99])
            latency_source: Source of latency data (e.g., "sc.sysc_latency_us")
            
        Returns:
            List of column definitions
        """
        columns = []
        for p in percentiles:
            columns.append(
                f"PERCENTILE_CONT({p/100.0}) WITHIN GROUP (ORDER BY {latency_source}) AS p{p}"
            )
        return columns
    
    def build_where_clause(self, filters: Dict[str, Any]) -> str:
        """Build WHERE clause from filters
        
        Args:
            filters: Dictionary of column -> value filters
            
        Returns:
            WHERE clause string
        """
        if not filters:
            return "1=1"
        
        conditions = []
        for col, val in filters.items():
            if val is None:
                conditions.append(f"{col} IS NULL")
            elif isinstance(val, str):
                # Escape single quotes
                val_escaped = val.replace("'", "''")
                conditions.append(f"{col} = '{val_escaped}'")
            elif isinstance(val, (list, tuple)):
                # IN clause
                if all(isinstance(v, str) for v in val):
                    values = ", ".join(f"'{v.replace("'", "''")}'" for v in val)
                else:
                    values = ", ".join(str(v) for v in val)
                conditions.append(f"{col} IN ({values})")
            else:
                conditions.append(f"{col} = {val}")
        
        return " AND ".join(conditions)
    
    def optimize_query(self, query: str) -> str:
        """Apply query optimizations
        
        Args:
            query: SQL query string
            
        Returns:
            Optimized query
        """
        # Remove unnecessary whitespace
        lines = [line.strip() for line in query.split('\n') if line.strip()]
        query = '\n'.join(lines)
        
        # Add query hints if beneficial
        if "enriched_samples" in query and "GROUP BY" in query:
            # Suggest using hash aggregation for large GROUP BY
            query = "-- Enable hash aggregation for better performance\n" + query
        
        return query