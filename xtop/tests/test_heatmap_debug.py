#\!/usr/bin/env python3
import logging
import sys
from pathlib import Path

# Set up logging  
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, str(Path.cwd()))

from core.heatmap import LatencyHeatmap, HeatmapConfig
from datetime import datetime
from core.data_source import XCaptureDataSource
from core.query_engine import QueryEngine

# Get actual data
ds = XCaptureDataSource(Path('/home/tanel/dev/0xtools-next/xcapture/out'))
engine = QueryEngine(ds)

# Run a time-series histogram query
query = engine.query_builder.build_histogram_drill_down_query(
    histogram_type='sclat',
    where_clause="state = 'RUN'",
    low_time=datetime.fromisoformat('2025-08-11T16:25:00'),
    high_time=datetime.fromisoformat('2025-08-11T16:26:00'),
    time_granularity='HH:MI'
)

conn = ds.connect()
result = conn.execute(query).fetchall()

# Convert to heatmap data format
heatmap_data = []
for row in result[:20]:  # Limit for testing
    heatmap_data.append({
        'HH': row[0],
        'MI': row[1],
        'lat_bucket_us': row[2],
        'cnt': row[3]
    })

print(f"Data has {len(heatmap_data)} rows")
unique_buckets = set(d['lat_bucket_us'] for d in heatmap_data)
print(f"Unique buckets in data: {sorted(unique_buckets)}")

# Generate heatmap
config = HeatmapConfig(width=20, height=15, use_color=False)
heatmap = LatencyHeatmap(config)

result_str = heatmap.generate_timeseries_heatmap(heatmap_data, palette='blue')

# Check what's in the heatmap
print("\nHeatmap output:")
for line in result_str.split('\n'):
    if '│' in line and ('μs' in line or 'ms' in line or 's │' in line):
        print(line)
