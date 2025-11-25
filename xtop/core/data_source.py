#!/usr/bin/env python3
"""
Data access layer for xcapture CSV files.
Manages DuckDB connections and CSV file discovery.
"""

import duckdb
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import sys
from .csv_time_filter import CSVTimeFilter


class XCaptureDataSource:
    """Manages access to xcapture CSV files via DuckDB"""
    
    def __init__(self, datadir: str, duckdb_threads: Optional[int] = None):
        """
        Initialize data source with directory containing CSV files.
        
        Args:
            datadir: Directory containing CSV files
            duckdb_threads: Number of DuckDB threads (None for default, 1 for deterministic)
        """
        self.datadir = Path(datadir)
        self.conn = None
        self.duckdb_threads = duckdb_threads
        self.available_columns = {}  # Lowercase -> actual column name mapping
        self.csv_metadata = {}
        self.schema_info: Dict[str, List[Tuple[str, str]]] = {}
        self.csv_filter = CSVTimeFilter(self.datadir)
        
        # Validate datadir exists
        if not self.datadir.exists():
            raise ValueError(f"Data directory does not exist: {datadir}")
    
    def connect(self):
        """Get or create DuckDB connection"""
        if self.conn is None:
            self.conn = duckdb.connect(':memory:')
            # Configure thread count if specified
            if self.duckdb_threads is not None:
                self.conn.execute(f"SET threads TO {self.duckdb_threads}")
        return self.conn
    
    def close(self):
        """Close DuckDB connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def discover_columns(self) -> Dict[str, Dict[str, str]]:
        """
        Discover available columns from all CSV types.
        Returns dict: {csv_type: {COLUMN_UPPER: actual_column_name}}
        """
        if self.available_columns:
            return self.available_columns
            
        conn = self.connect()

        # CSV file patterns in priority order
        csv_patterns = {
            'samples': 'xcapture_samples_*.csv',
            'syscend': 'xcapture_syscend_*.csv',
            'iorqend': 'xcapture_iorqend_*.csv',
            'kstacks': 'xcapture_kstacks_*.csv',
            'ustacks': 'xcapture_ustacks_*.csv'
        }

        for csv_type, pattern in csv_patterns.items():
            self.available_columns[csv_type] = {}
            self.schema_info[csv_type] = []

            describe_result = None
            active_pattern = pattern
            reader = 'read_csv_auto'

            csv_files = self.get_csv_files(pattern)
            if csv_files:
                describe_result = self._try_describe(conn, reader, pattern)

            if not describe_result:
                parquet_pattern = pattern.replace('.csv', '.parquet')
                parquet_files = self.get_csv_files(parquet_pattern)
                if parquet_files:
                    reader = 'read_parquet'
                    active_pattern = parquet_pattern
                    describe_result = self._try_describe(conn, reader, parquet_pattern)

            if describe_result:
                columns = describe_result
                self.available_columns[csv_type] = {
                    col_name.lower(): col_name for col_name, *_ in columns
                }
                self.schema_info[csv_type] = [(col_name, col_type) for col_name, col_type, *_ in columns]
                self.csv_metadata[csv_type] = {
                    'pattern': active_pattern,
                    'column_count': len(columns),
                    'columns': [col[0] for col in columns],
                    'format': reader.replace('read_', '')
                }
            else:
                self.csv_metadata[csv_type] = {
                    'pattern': pattern,
                    'column_count': 0,
                    'columns': [],
                    'format': None
                }

        return self.available_columns

    def _try_describe(self, conn, reader: str, pattern: str):
        """Attempt to DESCRIBE the given glob pattern using the provided reader."""
        escaped = str(self.datadir / pattern).replace("'", "''")
        try:
            query = f"DESCRIBE SELECT * FROM {reader}('{escaped}') LIMIT 0"
            result = conn.execute(query).fetchall()
            if result:
                return result
        except Exception:
            return None
        return None

    def get_schema_info(self) -> Dict[str, List[Tuple[str, str]]]:
        """Return discovered schema information per CSV type."""
        if not self.schema_info:
            self.discover_columns()
        return self.schema_info
    
    def get_csv_files(self, pattern: str) -> List[Path]:
        """List CSV files matching pattern"""
        return sorted(self.datadir.glob(pattern))
    
    def get_time_range(self, csv_type: str = 'samples') -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Get min/max timestamps from data.
        Returns (min_timestamp, max_timestamp) or (None, None) if no data.
        """
        conn = self.connect()
        
        # Get the CSV pattern for the type
        patterns = {
            'samples': 'xcapture_samples_*.csv',
            'syscend': 'xcapture_syscend_*.csv',
            'iorqend': 'xcapture_iorqend_*.csv',
            'kstacks': 'xcapture_kstacks_*.csv',
            'ustacks': 'xcapture_ustacks_*.csv'
        }
        
        pattern = patterns.get(csv_type, 'xcapture_samples_*.csv')
        csv_path = str(self.datadir / pattern)
        
        try:
            # Determine timestamp column based on CSV type
            timestamp_col = 'TIMESTAMP' if csv_type == 'samples' else 'SYSC_ENTER_TIME'
            
            query = f"""
            SELECT 
                MIN({timestamp_col}) as min_time,
                MAX({timestamp_col}) as max_time
            FROM read_csv_auto('{csv_path}')
            WHERE {timestamp_col} IS NOT NULL
            """
            
            result = conn.execute(query).fetchone()
            if result and result[0] and result[1]:
                return (result[0], result[1])
        except Exception:
            pass
            
        return (None, None)
    
    def validate_columns(self, columns: List[str], csv_type: str = None) -> List[str]:
        """
        Validate and map column names (case-insensitive).
        Returns list of actual column names.
        """
        # Ensure columns are discovered
        if not self.available_columns:
            self.discover_columns()
        
        validated = []
        
        for col in columns:
            col_lower = col.lower()
            found = False
            
            if csv_type and csv_type in self.available_columns:
                # Look in specific CSV type first
                if col_lower in self.available_columns[csv_type]:
                    validated.append(self.available_columns[csv_type][col_lower])
                    found = True
            
            if not found:
                # Look in all CSV types
                for csv_cols in self.available_columns.values():
                    if col_lower in csv_cols:
                        validated.append(csv_cols[col_lower])
                        found = True
                        break
            
            if not found:
                # Use original column name if not found
                validated.append(col)
        
        return validated
    
    def get_available_values(self, column: str, csv_type: str = 'samples', 
                           where_clause: str = "1=1", limit: int = 100) -> List[Any]:
        """
        Get distinct values for a column with optional filters.
        Useful for drill-down suggestions.
        """
        conn = self.connect()
        
        # Get the CSV pattern
        patterns = {
            'samples': 'xcapture_samples_*.csv',
            'syscend': 'xcapture_syscend_*.csv',
            'iorqend': 'xcapture_iorqend_*.csv',
            'kstacks': 'xcapture_kstacks_*.csv',
            'ustacks': 'xcapture_ustacks_*.csv'
        }
        
        pattern = patterns.get(csv_type, 'xcapture_samples_*.csv')
        csv_path = str(self.datadir / pattern)
        
        # Validate column name
        validated_cols = self.validate_columns([column], csv_type)
        if validated_cols:
            column = validated_cols[0]
        
        try:
            query = f"""
            SELECT DISTINCT {column} as value, COUNT(*) as count
            FROM read_csv_auto('{csv_path}')
            WHERE ({where_clause})
            AND {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY count DESC
            LIMIT {limit}
            """
            
            result = conn.execute(query).fetchall()
            return [row[0] for row in result]
        except Exception as e:
            print(f"Error getting values for {column}: {e}", file=sys.stderr)
            return []
    
    def get_partitions_info(self) -> Dict[str, str]:
        """
        Read partitions file to map device numbers to names.
        Returns dict: {major:minor -> device_name}
        """
        partitions_file = Path('/proc/partitions')
        device_map = {}

        if not partitions_file.exists():
            return device_map

        try:
            with open(partitions_file, 'r') as f:
                # Skip header line
                next(f)
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        major = parts[0]
                        minor = parts[1]
                        name = parts[3]
                        device_map[f"{major}:{minor}"] = name
        except Exception:
            pass

        return device_map
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.close()
