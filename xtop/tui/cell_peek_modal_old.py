#!/usr/bin/env python3
"""
Modal dialog for displaying detailed cell information.
Used for peeking into complex data like histogram visualizations.
"""

import logging
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Static, DataTable, Button
from textual.screen import ModalScreen
from textual.binding import Binding
from typing import Dict, List, Tuple, Any, Optional
from .histogram_query_builder import HistogramQueryBuilder


class CellPeekModal(ModalScreen[None]):
    """Modal screen for displaying detailed cell information"""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
    ]
    
    CSS = """
    CellPeekModal {
        align: center middle;
    }
    
    #peek-container {
        width: 80%;
        height: 80%;
        max-width: 100;
        max-height: 40;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #peek-title {
        text-align: center;
        background: $primary;
        color: $text;
        padding: 0 1;
        margin-bottom: 1;
        dock: top;
    }
    
    #peek-content {
        height: 1fr;
        padding: 0 1;
    }
    
    #peek-table {
        margin: 1 0;
        height: 1fr;
    }
    
    .peek-footer {
        height: 3;
        align: center middle;
        margin-top: 1;
        dock: bottom;
    }
    """
    
    def __init__(self, 
                 title: str,
                 column_name: str,
                 cell_value: Any,
                 row_data: Optional[Dict[str, Any]] = None):
        """Initialize the cell peek modal
        
        Args:
            title: Title for the modal
            column_name: Name of the column being peeked
            cell_value: The cell value to display details for
            row_data: Optional full row data for context
        """
        super().__init__()
        self.title = title
        self.column_name = column_name
        self.cell_value = cell_value
        self.row_data = row_data or {}
    
    def compose(self) -> ComposeResult:
        """Compose the modal layout"""
        with Container(id="peek-container"):
            yield Label(f"{self.title}: {self.column_name}", id="peek-title")
            
            with ScrollableContainer(id="peek-content"):
                # Content will be added by subclasses or dynamically
                yield from self._compose_content()
            
            with Horizontal(classes="peek-footer"):
                yield Label("Press [ESC] or [Q] to close", classes="dim")
    
    def _compose_content(self) -> ComposeResult:
        """Override this method to provide specific content"""
        yield Label("No detailed view available for this cell type.")
    
    def action_dismiss(self) -> None:
        """Dismiss the modal"""
        self.dismiss(None)


class HistogramPeekModal(CellPeekModal):
    """Modal specifically for displaying histogram breakdown"""
    
    def __init__(self, 
                 column_name: str,
                 query_type: str,
                 datadir: str,
                 where_clause: str,
                 low_time: Any,
                 high_time: Any,
                 engine: Any,
                 histogram_data: Optional[str] = None):
        """Initialize histogram peek modal
        
        Args:
            column_name: Name of the histogram column
            query_type: Type of query (sclathist or iolathist)
            datadir: Data directory path
            where_clause: WHERE clause for filtering
            low_time: Start time for query
            high_time: End time for query
            engine: Query engine instance
            histogram_data: Optional histogram data string
        """
        self.query_type = query_type
        self.datadir = datadir
        self.where_clause = where_clause
        self.low_time = low_time
        self.high_time = high_time
        self.engine = engine
        self.histogram_data = histogram_data
        super().__init__("Latency Histogram Breakdown", column_name, None, None)
    
    def compose(self) -> ComposeResult:
        """Compose the modal layout - override to handle DataTable differently"""
        with Container(id="peek-container"):
            yield Label(f"{self.title}: {self.column_name}", id="peek-title")
            
            # Create the data table directly without ScrollableContainer
            # DataTable handles its own scrolling
            table = DataTable(id="peek-table", cursor_type="row")
            table.add_columns(
                "Latency Range",
                "Count", 
                "Est. Events/s",
                "Est. Time (s)",
                "Time %",
                "Visual"
            )
            
            # Run query and populate table
            self._run_histogram_query_and_populate(table)
            
            # Store reference to table for later focus
            self.data_table = table
            
            yield table
            
            with Horizontal(classes="peek-footer"):
                yield Label("Press [ESC] or [Q] to close, use arrows to navigate", classes="dim")
    
    def on_mount(self) -> None:
        """Set focus to the data table when modal is mounted"""
        if hasattr(self, 'data_table'):
            self.data_table.focus()
    
    def _parse_histogram_data(self) -> List[Tuple[int, int, float, float]]:
        """Parse histogram data string into structured format
        
        Returns:
            List of tuples (bucket_us, count, est_time_s, global_max)
        """
        if not self.histogram_data or self.histogram_data == '-':
            return []
        
        data = []
        try:
            # Limit parsing to prevent memory issues with huge strings
            items = self.histogram_data.split(',')
            max_items = 1000  # Safety limit
            
            for i, item in enumerate(items):
                if i >= max_items:
                    break
                    
                parts = item.split(':')
                if len(parts) >= 4:
                    bucket = int(parts[0])
                    count = int(parts[1])
                    est_time = float(parts[2])
                    global_max = float(parts[3])
                    
                    # Only include non-zero entries
                    if count > 0 or est_time > 0:
                        data.append((bucket, count, est_time, global_max))
        except Exception:
            return []
        
        return sorted(data, key=lambda x: x[0])
    
    def _run_histogram_query_and_populate(self, table: DataTable) -> None:
        """Run DuckDB query to get histogram data and populate table"""
        # Initialize histogram query builder
        hist_builder = HistogramQueryBuilder(
            datadir=self.datadir,
            use_materialized=getattr(self.engine, 'use_materialized', False)
        )
        
        # Determine histogram type and build query
        hist_type = hist_builder.determine_histogram_type(
            self.column_name, self.where_clause, self.query_type
        )
        
        if hist_type == 'syscall':
            query = hist_builder.build_syscall_histogram(
                self.where_clause, self.low_time, self.high_time
            )
        elif hist_type == 'io':
            query = hist_builder.build_io_histogram(
                self.where_clause, self.low_time, self.high_time
            )
        else:
            return
        
        try:
            # Execute query directly with DuckDB
            conn = self.engine.data_source.conn
            df = conn.execute(query).fetch_df()
            
            if df.empty:
                return
            
            # Calculate totals
            total_count = df['count'].sum()
            total_time = df['est_time_s'].sum()
            max_time = df['est_time_s'].max()
            
            # Add rows to table
            for _, row in df.iterrows():
                bucket_us = row['bucket_us']
                count = row['count']
                est_time = row['est_time_s']
                
                # Skip empty buckets
                if count == 0 and est_time == 0:
                    continue
                
                # Calculate percentage
                time_pct = (est_time / total_time * 100) if total_time > 0 else 0
                
                # Create visual bar
                bar_width = int((est_time / max_time) * 20) if max_time > 0 else 0
                visual_bar = "█" * bar_width + "▏" * (1 if bar_width == 0 and est_time > 0 else 0)
                
                # Calculate events per second
                est_events = (1000000000 / bucket_us * count) if bucket_us > 0 else 0
                
                table.add_row(
                    self._format_latency_range(bucket_us),
                    f"{count:>12,}",  # Right-align in 12 chars
                    f"{est_events:>14,.0f}",  # Right-align in 14 chars
                    f"{est_time:>12.3f}",  # Right-align in 12 chars
                    f"{time_pct:>7.1f}%",  # Right-align in 7 chars (plus %)
                    visual_bar
                )
            
            # Add summary row
            table.add_row(
                "─" * 15,
                "─" * 12,
                "─" * 14,
                "─" * 12,
                "─" * 8,
                "─" * 20,
                key="separator"
            )
            
            # Add totals
            table.add_row(
                "TOTAL",
                f"{total_count:>12,}",
                " " * 14 + "-",  # Right-align dash
                f"{total_time:>12.3f}",
                f"{100.0:>7.1f}%",
                "",
                key="total"
            )
        except Exception as e:
            # Log the error to debug log if available
            logger = logging.getLogger('xtop')
            logger.error(f"Error in histogram peek query: {str(e)}")
            logger.debug(f"Query that failed: {query if 'query' in locals() else 'Query not yet built'}")
            
            # Add error row
            table.add_row(
                f"Error: {str(e)}",
                "-", "-", "-", "-", "-"
            )
    
    def _format_latency_range(self, bucket_us: int) -> str:
        """Format bucket value into latency range string"""
        # Find the next power of 2
        from datetime import datetime, timedelta
        
        if self.low_time is None:
            low_time_str = (datetime.now() - timedelta(hours=1)).isoformat()
        elif isinstance(self.low_time, datetime):
            low_time_str = self.low_time.isoformat()
        else:
            low_time_str = str(self.low_time)
            
        if self.high_time is None:
            high_time_str = datetime.now().isoformat()
        elif isinstance(self.high_time, datetime):
            high_time_str = self.high_time.isoformat()
        else:
            high_time_str = str(self.high_time)
        
        return f"""
        WITH enriched_samples AS (
            SELECT
                t.*,
                -- Add computed columns that might be referenced in WHERE clause
                COALESCE(REGEXP_REPLACE(t.filename, '[0-9]+', '*', 'g'), '-') AS FILENAMESUM,
                CASE
                    WHEN t.filename IS NULL THEN '-'
                    WHEN REGEXP_MATCHES(t.filename, '\\.([^\\.]+)$') THEN REGEXP_EXTRACT(t.filename, '(\\.[^\\.]+)$', 1)
                    ELSE '-'
                END AS FEXT,
                CASE
                    WHEN t.comm LIKE 'ora_p%'
                    THEN regexp_replace(t.comm, '(?:p[0-9a-z]+_)', 'p*_', 'g')
                    ELSE regexp_replace(t.comm, '[0-9]+', '*', 'g')
                END AS COMM2,
                CASE 
                    WHEN t.extra_info LIKE '%"connection"%' 
                    THEN json_extract_string(t.extra_info, '$.connection')
                    ELSE '-'
                END AS CONNECTION
            FROM
                read_csv_auto('{self.datadir}/xcapture_samples_*.csv') AS t
        ),
        base_samples AS (
            SELECT
                t.tid,
                t.sysc_seq_num,
                sc.duration_ns AS SYSC_DURATION_NS,
                POWER(2, CEIL(LOG2(CASE WHEN sc.duration_ns <= 0 THEN NULL ELSE CEIL(sc.duration_ns / 1000) END)))::bigint AS bucket_us
            FROM
                enriched_samples AS t
            LEFT OUTER JOIN
                read_csv_auto('{self.datadir}/xcapture_syscend_*.csv') AS sc
                ON t.tid = sc.tid
                AND t.sysc_seq_num = sc.sysc_seq_num
            WHERE
                ({self.where_clause})
                AND t.timestamp >= TIMESTAMP '{low_time_str}'
                AND t.timestamp < TIMESTAMP '{high_time_str}'
                AND sc.duration_ns > 0
        )
        SELECT
            bucket_us,
            COUNT(*) as count,
            SUM(CASE 
                WHEN SYSC_DURATION_NS > 0 
                THEN (1000000000.0 / SYSC_DURATION_NS) * bucket_us / 1000000.0
                ELSE 0 
            END) as est_time_s
        FROM base_samples
        GROUP BY bucket_us
        ORDER BY bucket_us
        """
    
    def _build_iolat_histogram_query(self) -> str:
        """Build query for I/O latency histogram"""
        # Convert timestamps to ISO format if they are datetime objects
        from datetime import datetime, timedelta
        
        if self.low_time is None:
            low_time_str = (datetime.now() - timedelta(hours=1)).isoformat()
        elif isinstance(self.low_time, datetime):
            low_time_str = self.low_time.isoformat()
        else:
            low_time_str = str(self.low_time)
            
        if self.high_time is None:
            high_time_str = datetime.now().isoformat()
        elif isinstance(self.high_time, datetime):
            high_time_str = self.high_time.isoformat()
        else:
            high_time_str = str(self.high_time)
            
        return f"""
        WITH part AS ( -- block device id to name mapping
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
        ),
        enriched_samples AS (
            SELECT
                t.*,
                -- Add computed columns that might be referenced in WHERE clause
                COALESCE(REGEXP_REPLACE(t.filename, '[0-9]+', '*', 'g'), '-') AS FILENAMESUM,
                CASE
                    WHEN t.filename IS NULL THEN '-'
                    WHEN REGEXP_MATCHES(t.filename, '\\.([^\\.]+)$') THEN REGEXP_EXTRACT(t.filename, '(\\.[^\\.]+)$', 1)
                    ELSE '-'
                END AS FEXT,
                CASE
                    WHEN t.comm LIKE 'ora_p%'
                    THEN regexp_replace(t.comm, '(?:p[0-9a-z]+_)', 'p*_', 'g')
                    ELSE regexp_replace(t.comm, '[0-9]+', '*', 'g')
                END AS COMM2,
                CASE 
                    WHEN t.extra_info LIKE '%"connection"%' 
                    THEN json_extract_string(t.extra_info, '$.connection')
                    ELSE '-'
                END AS CONNECTION
            FROM
                read_csv_auto('{self.datadir}/xcapture_samples_*.csv') AS t
        ),
        joined_samples AS (
            SELECT
                t.*,
                io.duration_ns AS IORQ_DURATION_NS,
                io.dev_maj,
                io.dev_min,
                io.bytes AS IORQ_BYTES,
                io.iorq_flags AS IORQ_FLAGS,
                COALESCE(part.devname, '-') AS DEVNAME,
                POWER(2, CEIL(LOG2(CASE WHEN io.duration_ns <= 0 THEN NULL ELSE CEIL(io.duration_ns / 1000) END)))::bigint AS bucket_us
            FROM
                enriched_samples AS t
            LEFT OUTER JOIN
                read_csv_auto('{self.datadir}/xcapture_iorqend_*.csv') AS io
                ON t.tid = io.insert_tid
                AND t.iorq_seq_num = io.iorq_seq_num
            LEFT OUTER JOIN
                part
                ON io.dev_maj = part.dev_maj
                AND io.dev_min = part.dev_min
            WHERE
                t.timestamp >= TIMESTAMP '{low_time_str}'
                AND t.timestamp < TIMESTAMP '{high_time_str}'
                AND io.duration_ns > 0
        ),
        base_samples AS (
            SELECT
                tid,
                iorq_seq_num,
                IORQ_DURATION_NS,
                bucket_us
            FROM
                joined_samples
            WHERE
                ({self.where_clause})
        )
        SELECT
            bucket_us,
            COUNT(*) as count,
            SUM(CASE 
                WHEN IORQ_DURATION_NS > 0 
                THEN (1000000000.0 / IORQ_DURATION_NS) * bucket_us / 1000000.0
                ELSE 0 
            END) as est_time_s
        FROM base_samples
        GROUP BY bucket_us
        ORDER BY bucket_us
        """
    
    def _format_latency_range(self, bucket_us: int) -> str:
        """Format bucket value into latency range string"""
        # Find the next power of 2
        next_bucket = bucket_us * 2
        
        # Format both bounds
        def format_latency(us: int) -> str:
            if us >= 1000000:
                return f"{us/1000000:.0f}s"
            elif us >= 1000:
                return f"{us/1000:.0f}ms"
            else:
                return f"{us}μs"
        
        return f"{format_latency(bucket_us)} - {format_latency(next_bucket)}"
    
