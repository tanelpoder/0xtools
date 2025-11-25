#!/usr/bin/env python3
"""
Data materialization support for XTOP.
Materializes CSV data into DuckDB tables for improved performance.
"""

from pathlib import Path
from typing import Optional, List, Dict
import logging
import time
import duckdb


class DataMaterializer:
    """Handles materialization of CSV data into DuckDB tables"""
    
    # Mapping of data sources to their materialized table names
    TABLE_NAMES = {
        'samples': 'xtop_samples',
        'syscend': 'xtop_syscend',
        'iorqend': 'xtop_iorqend',
        'kstacks': 'xtop_kstacks',
        'ustacks': 'xtop_ustacks',
        'partitions': 'xtop_partitions'
    }
    
    def __init__(self, conn: duckdb.DuckDBPyConnection, datadir: Path):
        """
        Initialize materializer.
        
        Args:
            conn: DuckDB connection
            datadir: Path to data directory containing CSV files
        """
        self.conn = conn
        self.datadir = datadir
        self.logger = logging.getLogger('xtop.materializer')
        self.is_materialized = False
    
    def materialize_all(self, sources: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Materialize CSV data into DuckDB tables.
        
        Args:
            sources: List of sources to materialize. If None, materialize all.
            
        Returns:
            Dictionary mapping source names to materialization times
        """
        if sources is None:
            sources = list(self.TABLE_NAMES.keys())
        
        timings = {}
        
        for source in sources:
            if source not in self.TABLE_NAMES:
                self.logger.warning(f"Unknown source: {source}")
                continue
            
            start_time = time.time()
            try:
                self._materialize_source(source)
                elapsed = time.time() - start_time
                timings[source] = elapsed
                self.logger.info(f"Materialized {source} in {elapsed:.2f}s")
            except Exception as e:
                self.logger.error(f"Failed to materialize {source}: {e}")
                timings[source] = -1
        
        self.is_materialized = len(timings) > 0 and all(t >= 0 for t in timings.values())
        return timings
    
    def _materialize_source(self, source: str):
        """Materialize a single data source"""
        table_name = self.TABLE_NAMES[source]
        
        # Drop existing table if it exists
        self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        
        if source == 'samples':
            # Create enriched samples table with computed columns
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT
                samples.*,
                -- Computed columns
                COALESCE(REGEXP_REPLACE(FILENAME, '[0-9]+', '*', 'g'), '-') AS FILENAMESUM,
                CASE
                    WHEN FILENAME IS NULL THEN '-'
                    WHEN REGEXP_MATCHES(FILENAME, '\\.([^\\.]+)$') 
                    THEN REGEXP_EXTRACT(FILENAME, '(\\.([^\\.]+))$', 1)
                    ELSE '-'
                END AS FEXT,
                CASE 
                    WHEN COMM LIKE 'ora_p%' 
                    THEN regexp_replace(COMM, '(?:p[0-9a-z]+_)', 'p*_', 'g')
                    ELSE regexp_replace(COMM, '[0-9]+', '*', 'g')
                END AS COMM2,
                CASE 
                    WHEN EXTRA_INFO LIKE '%"connection"%' 
                    THEN json_extract_string(EXTRA_INFO, '$.connection')
                    ELSE '-'
                END AS CONNECTION
            FROM read_csv_auto('{self.datadir}/xcapture_samples_*.csv') AS samples
            """
        elif source == 'syscend':
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{self.datadir}/xcapture_syscend_*.csv')
            """
        elif source == 'iorqend':
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{self.datadir}/xcapture_iorqend_*.csv')
            """
        elif source == 'kstacks':
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT 
                KSTACK_HASH,
                KSTACK_SYMS
            FROM read_csv_auto('{self.datadir}/xcapture_kstacks_*.csv')
            """
        elif source == 'ustacks':
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT 
                USTACK_HASH,
                USTACK_SYMS
            FROM read_csv_auto('{self.datadir}/xcapture_ustacks_*.csv')
            """
        elif source == 'partitions':
            query = f"""
            CREATE TABLE {table_name} AS
            SELECT
                LIST_EXTRACT(field_list, 1)::int  AS dev_maj,
                LIST_EXTRACT(field_list, 2)::int  AS dev_min,
                TRIM(LIST_EXTRACT(field_list, 4)) AS devname
            FROM (
                SELECT
                    REGEXP_EXTRACT_ALL(column0, ' +(\\w+)') field_list
                FROM
                    read_csv('/proc/partitions', skip=1, header=false)
                WHERE
                    field_list IS NOT NULL
            )
            """
        else:
            raise ValueError(f"Unknown source: {source}")
        
        self.conn.execute(query)
        
        # Create indexes for better join performance
        self._create_indexes(table_name, source)
    
    def _create_indexes(self, table_name: str, source: str):
        """Create indexes on materialized tables"""
        if source == 'samples':
            # Index on join columns and commonly filtered columns
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_tid ON {table_name}(tid)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name}(timestamp)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_sysc_seq ON {table_name}(sysc_seq_num)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_iorq_seq ON {table_name}(iorq_seq_num)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_kstack ON {table_name}(kstack_hash)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_ustack ON {table_name}(ustack_hash)")
        elif source == 'syscend':
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_tid ON {table_name}(tid, sysc_seq_num)")
        elif source == 'iorqend':
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_tid ON {table_name}(insert_tid, iorq_seq_num)")
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_dev ON {table_name}(dev_maj, dev_min)")
        elif source == 'kstacks':
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_hash ON {table_name}(KSTACK_HASH)")
        elif source == 'ustacks':
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_hash ON {table_name}(USTACK_HASH)")
        elif source == 'partitions':
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_dev ON {table_name}(dev_maj, dev_min)")
    
    def drop_all(self):
        """Drop all materialized tables"""
        for table_name in self.TABLE_NAMES.values():
            try:
                self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                self.logger.info(f"Dropped table {table_name}")
            except Exception as e:
                self.logger.error(f"Failed to drop table {table_name}: {e}")
        
        self.is_materialized = False
    
    def check_tables_exist(self) -> Dict[str, bool]:
        """Check which materialized tables exist"""
        result = {}
        
        for source, table_name in self.TABLE_NAMES.items():
            try:
                # Try to query the table
                self.conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
                result[source] = True
            except:
                result[source] = False
        
        return result
    
    def get_table_stats(self) -> Dict[str, Dict[str, int]]:
        """Get row counts and sizes for materialized tables"""
        stats = {}
        
        for source, table_name in self.TABLE_NAMES.items():
            try:
                # Get row count
                row_count = self.conn.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]
                
                # Get approximate table size (this is a rough estimate)
                col_count = len(self.conn.execute(
                    f"DESCRIBE {table_name}"
                ).fetchall())
                
                stats[source] = {
                    'rows': row_count,
                    'columns': col_count
                }
            except:
                stats[source] = {'rows': 0, 'columns': 0}
        
        return stats