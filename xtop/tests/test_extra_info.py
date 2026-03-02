from pathlib import Path
from datetime import datetime
from core.data_source import XCaptureDataSource
from core.query_engine import QueryEngine, QueryParams

# Get some data with extra_info
ds = XCaptureDataSource(Path('/home/tanel/dev/0xtools-next/xcapture/out'))
engine = QueryEngine(ds)

# Try a simpler query to check for extra_info
query = """
SELECT state, extra_info, COUNT(*) as cnt
FROM read_csv_auto('/home/tanel/dev/0xtools-next/xcapture/out/xcapture_samples_*.csv')
WHERE extra_info IS NOT NULL AND extra_info \!= '-' AND extra_info \!= ''
GROUP BY state, extra_info
LIMIT 10
"""

result = engine.execute(query)
if result.row_count > 0:
    print(f'Found {result.row_count} rows with extra_info data')
    for row in result.data:
        extra = row['extra_info']
        print(f"State: {row['state']}, Count: {row['cnt']}")
        print(f"Extra_info: {extra[:100] if len(extra) > 100 else extra}")
        print("-" * 40)
else:
    print('No extra_info data found in the dataset')
    print('The extra_info column appears to be empty in this dataset')
