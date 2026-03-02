#!/usr/bin/env python3
"""Integration tests ensuring queries tolerate missing optional columns."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from core import XCaptureDataSource, QueryEngine, QueryParams

SAMPLE_CSV = """TIMESTAMP,TID,SYSC_SEQ_NUM,IORQ_SEQ_NUM,STATE,USERNAME,COMM,FILENAME,EXTRA_INFO,CONNECTION,KSTACK_HASH,USTACK_HASH
2025-10-04 04:00:01,1001,1,1,SLEEP,tanel,sysbench,foo.txt,"{""connection"":""127.0.0.1:5432""}",127.0.0.1:5432,1,10
2025-10-04 04:00:02,1002,2,2,DISK,mysql,connection,sbtest1.ibd,"{""connection"":""10.0.0.1->10.0.0.2:1234""}",10.0.0.1->10.0.0.2:1234,2,20
"""

SYSCEND_CSV = """TID,SYSC_SEQ_NUM,DURATION_NS
1001,1,100000
1002,2,200000
"""

IORQEND_CSV = """INSERT_TID,IORQ_SEQ_NUM,DURATION_NS,BYTES
1002,2,300000,4096
"""

KSTACKS_CSV = """KSTACK_HASH
1
"""

USTACKS_CSV = """USTACK_HASH
2
"""

PARTITIONS_TXT = """# partition text intentionally minimal"""


def test_query_with_missing_optional_columns():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / 'xcapture_samples_2025-10-04.04.csv').write_text(SAMPLE_CSV)
        (tmp_path / 'xcapture_syscend_2025-10-04.04.csv').write_text(SYSCEND_CSV)
        (tmp_path / 'xcapture_iorqend_2025-10-04.04.csv').write_text(IORQEND_CSV)
        (tmp_path / 'xcapture_kstacks_2025-10-04.04.csv').write_text(KSTACKS_CSV)
        (tmp_path / 'xcapture_ustacks_2025-10-04.04.csv').write_text(USTACKS_CSV)
        (tmp_path / 'partitions').write_text(PARTITIONS_TXT)

        data_source = XCaptureDataSource(str(tmp_path))
        engine = QueryEngine(data_source)

        params = QueryParams(
            group_cols=['state', 'kstack_hash'],
            where_clause='1=1',
            limit=10,
        )

        result = engine.execute_with_params(
            params,
            latency_columns=['sc.p95_us', 'io.p95_us', 'kstack_hash', 'devname'],
        )

        assert result.row_count > 0
        row = result.data[0]
        keys_map = {key.lower(): key for key in row.keys()}
        assert 'kstack_hash' in keys_map
        kstack_key = keys_map['kstack_hash']
        assert str(row[kstack_key]) in {'None', '-', '1', '2'}
