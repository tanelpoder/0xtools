#!/usr/bin/env python3
"""Test avg_threads calculation"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.data_source import XCaptureDataSource
from core.query_builder import QueryBuilder

# Set data directory from environment variable or use default
XCAPTURE_DATADIR = os.environ.get('XCAPTURE_DATADIR', '/home/tanel/dev/0xtools-next/xcapture/out')
datadir = Path(XCAPTURE_DATADIR)
from_time = datetime.fromisoformat("2025-08-03T03:40:00")
to_time = datetime.fromisoformat("2025-08-03T04:07:00")

# Calculate expected time difference
time_diff_seconds = (to_time - from_time).total_seconds()
print(f"Time range: {from_time} to {to_time}")
print(f"Duration: {time_diff_seconds} seconds ({time_diff_seconds/60:.1f} minutes)")
print()

# Create data source and query builder
data_source = XCaptureDataSource(datadir, duckdb_threads=1)
query_builder = QueryBuilder(datadir, Path("sql/fragments"), use_materialized=False)

# Build a simple dynamic query
query = query_builder.build_dynamic_query(
    group_cols=['state'],
    where_clause="1=1",
    low_time=from_time,
    high_time=to_time,
    latency_columns=[],
    limit=5
)

print("Generated Query:")
print("-" * 60)
print(query)
print("-" * 60)
print()

# Execute the query
conn = data_source.connect()
result = conn.execute(query).fetch_df()

print("Query Results:")
print("-" * 60)
print(result.to_string())
print("-" * 60)
print()

# Check avg_threads calculation
if not result.empty:
    for idx, row in result.iterrows():
        samples = row['samples']
        avg_threads = row['avg_threads']
        expected_avg = samples / time_diff_seconds
        
        print(f"Row {idx}: STATE={row.get('STATE', row.get('state', 'N/A'))}")
        print(f"  Samples: {samples}")
        print(f"  Avg threads (actual): {avg_threads:.2f}")
        print(f"  Avg threads (expected): {expected_avg:.2f}")
        print(f"  Match: {'✓' if abs(avg_threads - expected_avg) < 0.01 else '✗'}")
        print()

data_source.close()