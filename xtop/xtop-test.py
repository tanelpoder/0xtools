#!/usr/bin/env python3
"""
Text-based testing interface for XTOP.
Provides plaintext output for automated testing without TUI.
"""

import argparse
import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from tabulate import tabulate

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.data_source import XCaptureDataSource
from core.query_engine import QueryEngine, QueryParams
from core.query_builder import QueryBuilder


class XtopTester:
    """Test harness for XTOP queries without TUI"""
    
    def __init__(self, datadir: Path, use_materialized: bool = False, duckdb_threads: Optional[int] = None):
        """Initialize test harness"""
        self.datadir = datadir
        self.data_source = XCaptureDataSource(datadir, duckdb_threads=duckdb_threads)
        self.query_engine = QueryEngine(self.data_source, use_materialized)
        self.logger = logging.getLogger('xtop.test')
    
    def run_query(self, 
                  group_cols: Optional[List[str]] = None,
                  latency_cols: Optional[List[str]] = None,
                  where_clause: str = "1=1",
                  low_time: Optional[datetime] = None,
                  high_time: Optional[datetime] = None,
                  limit: int = 30,
                  peek: bool = False) -> Dict[str, Any]:
        """
        Run a query and return results.
        
        Args:
            group_cols: Columns to group by
            latency_cols: Latency/percentile columns to include
            where_clause: WHERE clause conditions
            low_time: Start time for data
            high_time: End time for data
            limit: Row limit
            peek: Whether to also run peek queries for peekable columns
            
        Returns:
            Dictionary with 'main' results and optionally 'peek' results
        """
        results = {}
        
        # Build query parameters
        params = QueryParams(
            group_cols=group_cols or [],
            where_clause=where_clause,
            low_time=low_time,
            high_time=high_time,
            limit=limit
        )
        
        # Execute main query
        try:
            self.logger.info(f"Executing dynamic query")
            self.logger.info(f"Group columns: {group_cols}")
            self.logger.info(f"Latency columns: {latency_cols}")
            
            result = self.query_engine.execute_with_params(
                params,
                debug=True,
                latency_columns=latency_cols
            )
            
            results['main'] = {
                'data': result.data,
                'columns': result.columns,
                'row_count': result.row_count,
                'execution_time': result.execution_time
            }
            
            self.logger.info(f"Query returned {result.row_count} rows in {result.execution_time:.3f}s")
            
        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            results['main'] = {
                'error': str(e),
                'data': [],
                'columns': [],
                'row_count': 0
            }
        
        # Run peek queries if requested
        if peek:
            results['peek'] = self._run_peek_queries(
                group_cols, latency_cols, where_clause, low_time, high_time
            )
        
        return results
    
    def _run_peek_queries(self, 
                         group_cols: Optional[List[str]],
                         latency_cols: Optional[List[str]],
                         where_clause: str,
                         low_time: Optional[datetime],
                         high_time: Optional[datetime]) -> Dict[str, Any]:
        """Run peek queries for peekable columns"""
        peek_results = {}
        
        # Identify peekable columns
        peekable_cols = []
        
        # Check group columns
        if group_cols:
            for col in group_cols:
                if self._is_peekable(col):
                    peekable_cols.append(col)
        
        # Check latency columns
        if latency_cols:
            for col in latency_cols:
                if self._is_peekable(col):
                    peekable_cols.append(col)
        
        # Run peek queries
        for col in peekable_cols:
            self.logger.info(f"Running peek query for column: {col}")
            
            try:
                if 'histogram' in col.lower() or col.endswith('_HISTOGRAM'):
                    # Run histogram peek query
                    peek_result = self._run_histogram_peek(
                        col, where_clause, low_time, high_time
                    )
                elif 'stack' in col.lower():
                    # Run stack trace peek query
                    peek_result = self._run_stack_peek(col)
                else:
                    peek_result = {'type': 'unsupported', 'column': col}
                
                peek_results[col] = peek_result
                
            except Exception as e:
                self.logger.error(f"Peek query failed for {col}: {e}")
                peek_results[col] = {'error': str(e)}
        
        return peek_results
    
    def _is_peekable(self, column: str) -> bool:
        """Check if a column is peekable"""
        col_lower = column.lower()
        return ('histogram' in col_lower or 
                col_lower.endswith('_hist') or
                'stack' in col_lower or
                col_lower in ['kstack_hash', 'ustack_hash', 'kstack_syms', 'ustack_syms'])
    
    def _run_histogram_peek(self, 
                           column: str,
                           where_clause: str,
                           low_time: Optional[datetime],
                           high_time: Optional[datetime]) -> Dict[str, Any]:
        """Run histogram peek query"""
        hist_builder = HistogramQueryBuilder(
            datadir=self.datadir,
            use_materialized=self.query_engine.use_materialized
        )
        
        # Determine histogram type
        if 'sclat' in column.lower() or column == 'SCLAT_HISTOGRAM':
            query = hist_builder.build_syscall_histogram(
                where_clause, low_time, high_time
            )
            hist_type = 'syscall'
        elif 'iolat' in column.lower() or column == 'IOLAT_HISTOGRAM':
            query = hist_builder.build_io_histogram(
                where_clause, low_time, high_time
            )
            hist_type = 'io'
        else:
            # Try to determine from context
            hist_type = hist_builder.determine_histogram_type(
                column, where_clause, 'dynamic'
            )
            if hist_type == 'syscall':
                query = hist_builder.build_syscall_histogram(
                    where_clause, low_time, high_time
                )
            else:
                query = hist_builder.build_io_histogram(
                    where_clause, low_time, high_time
                )
        
        # Execute query
        conn = self.data_source.conn
        df = conn.execute(query).fetch_df()
        
        return {
            'type': 'histogram',
            'histogram_type': hist_type,
            'data': df.to_dict('records') if not df.empty else [],
            'row_count': len(df)
        }
    
    def _run_stack_peek(self, column: str) -> Dict[str, Any]:
        """Run stack trace peek query"""
        # For stack traces, we would typically look up the full trace
        # For now, return a placeholder
        return {
            'type': 'stack_trace',
            'column': column,
            'note': 'Stack trace lookup not yet implemented in test mode'
        }
    
    def print_results(self, results: Dict[str, Any], format: str = 'grid'):
        """
        Print results in plaintext table format.
        
        Args:
            results: Query results dictionary
            format: Table format (grid, simple, plain, html, etc.)
        """
        # Print main results
        if 'main' in results:
            main = results['main']
            
            if 'error' in main:
                print(f"ERROR: {main['error']}", file=sys.stderr)
                return
            
            print("\n=== MAIN QUERY RESULTS ===")
            print(f"Rows: {main['row_count']}, Time: {main.get('execution_time', 0):.3f}s\n")
            
            if main['data']:
                # Convert to table format
                headers = main['columns']
                rows = []
                for row_dict in main['data']:
                    row = [row_dict.get(col, '') for col in headers]
                    rows.append(row)
                
                # Print table
                print(tabulate(rows, headers=headers, tablefmt=format))
            else:
                print("No data returned")
        
        # Print peek results
        if 'peek' in results and results['peek']:
            print("\n=== PEEK QUERY RESULTS ===")
            
            for col, peek_result in results['peek'].items():
                print(f"\n--- Peek: {col} ---")
                
                if 'error' in peek_result:
                    print(f"ERROR: {peek_result['error']}")
                    continue
                
                if peek_result['type'] == 'histogram':
                    print(f"Histogram Type: {peek_result['histogram_type']}")
                    print(f"Buckets: {peek_result['row_count']}")
                    
                    if peek_result['data']:
                        # Format histogram data
                        hist_headers = ['Bucket (μs)', 'Count', 'Est. Time (s)']
                        hist_rows = []
                        for item in peek_result['data']:
                            hist_rows.append([
                                item.get('bucket_us', 0),
                                item.get('count', 0),
                                f"{item.get('est_time_s', 0):.3f}"
                            ])
                        print(tabulate(hist_rows, headers=hist_headers, tablefmt='simple'))
                
                elif peek_result['type'] == 'stack_trace':
                    print(f"Stack trace column: {peek_result['column']}")
                    print(peek_result.get('note', ''))
                
                else:
                    print(f"Unsupported peek type: {peek_result.get('type')}")


def main():
    """Main entry point for test interface"""
    parser = argparse.ArgumentParser(description='XTOP Test Interface')
    
    # Use XCAPTURE_DATADIR environment variable as default, or None if not set
    default_datadir = os.environ.get('XCAPTURE_DATADIR')
    
    # Data source
    parser.add_argument('-d', '--datadir', type=str, default=default_datadir,
                       help='Data directory with xcapture CSV files (default: $XCAPTURE_DATADIR or required if not set)')
    
    # Query type removed - always uses dynamic queries
    
    # Columns
    parser.add_argument('-g', '--group', type=str, default='',
                       help='Comma-separated GROUP BY columns')
    parser.add_argument('-l', '--latency', type=str, default='',
                       help='Comma-separated latency/percentile columns')
    
    # Filters
    parser.add_argument('-w', '--where', type=str, default='1=1',
                       help='WHERE clause for filtering')
    parser.add_argument('--from', dest='from_time', type=str,
                       help='Start time (ISO format or relative like -1h)')
    parser.add_argument('--to', dest='to_time', type=str,
                       help='End time (ISO format or relative like now)')
    
    # Options
    parser.add_argument('--limit', type=int, default=30,
                       help='Maximum rows to return')
    parser.add_argument('--peek', action='store_true',
                       help='Also run peek queries for histogram/stack columns')
    parser.add_argument('--format', type=str, default='grid',
                       help='Table format (grid, simple, plain, html, etc.)')
    parser.add_argument('--materialize', action='store_true',
                       help='Use materialized tables instead of CSV')
    
    # Performance
    parser.add_argument('--duckdb-threads', type=int, default=None,
                       help='Number of DuckDB threads (1 for deterministic results, default: auto)')
    
    # Logging
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--debuglog', type=str,
                       help='Debug log file')
    
    args = parser.parse_args()
    
    # Check if datadir is provided (either via command line or environment variable)
    if not args.datadir:
        print("Error: Data directory not specified.", file=sys.stderr)
        print("Please either:", file=sys.stderr)
        print("  1. Set the XCAPTURE_DATADIR environment variable", file=sys.stderr)
        print("  2. Use the -d/--datadir command line option", file=sys.stderr)
        sys.exit(1)
    
    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    if args.debuglog:
        logging.basicConfig(
            level=log_level,
            format=log_format,
            filename=args.debuglog,
            filemode='w'
        )
    else:
        logging.basicConfig(
            level=log_level,
            format=log_format
        )
    
    # Parse columns (normalize to lowercase)
    group_cols = [c.strip().lower() for c in args.group.split(',') if c.strip()] if args.group else []
    latency_cols = [c.strip().lower() for c in args.latency.split(',') if c.strip()] if args.latency else []
    
    # Parse time range
    low_time = None
    high_time = None
    
    if args.from_time:
        if args.from_time.startswith('-'):
            # Relative time like -1h
            hours = int(args.from_time[1:-1])
            low_time = datetime.now() - timedelta(hours=hours)
        else:
            low_time = datetime.fromisoformat(args.from_time)
    
    if args.to_time:
        if args.to_time == 'now':
            high_time = datetime.now()
        else:
            high_time = datetime.fromisoformat(args.to_time)
    
    # Create tester
    datadir = Path(args.datadir)
    if not datadir.exists():
        print(f"Error: Data directory not found: {datadir}", file=sys.stderr)
        sys.exit(1)
    
    tester = XtopTester(datadir, use_materialized=args.materialize, 
                       duckdb_threads=args.duckdb_threads)
    
    # Run query
    results = tester.run_query(
        group_cols=group_cols,
        latency_cols=latency_cols,
        where_clause=args.where,
        low_time=low_time,
        high_time=high_time,
        limit=args.limit,
        peek=args.peek
    )
    
    # Print results
    tester.print_results(results, format=args.format)


if __name__ == '__main__':
    main()