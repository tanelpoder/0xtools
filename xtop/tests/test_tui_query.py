#!/usr/bin/env python3
"""
Test TUI query execution without interactive terminal
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from core import XCaptureDataSource, QueryEngine, QueryParams

def test_query_execution():
    """Test query execution with debug logging"""
    
    # Setup logging
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger('test')
    
    try:
        # Initialize components
        logger.info("Initializing data source...")
        data_source = XCaptureDataSource('./out')
        
        logger.info("Initializing query engine...")
        query_engine = QueryEngine(data_source)
        
        # Get available time range
        logger.info("Getting available time range...")
        data_min, data_max = data_source.get_time_range()
        logger.info(f"Data time range: {data_min} to {data_max}")
        
        # Create query params
        params = QueryParams(
            query_type='top',
            where_clause='1=1',
            group_cols=['STATE', 'USERNAME', 'EXE', 'COMM', 'SYSCALL', 'FILENAME', 'EXTRA_INFO'],
            low_time=data_min,
            high_time=data_max,
            limit=10
        )
        
        logger.info(f"Executing query: {params.query_type}")
        
        # Execute query with debug enabled
        result = query_engine.execute_with_params(params, debug=True)
        
        logger.info(f"Query returned {result.row_count} rows")
        logger.info(f"Columns: {result.columns}")
        logger.info(f"Execution time: {result.execution_time:.3f}s")
        
        if result.row_count > 0:
            logger.info("First row:")
            for col, val in result.data[0].items():
                logger.info(f"  {col}: {val}")
        else:
            logger.warning("No data returned!")
            
        # Check available CSV files
        logger.info("\nChecking available CSV files:")
        for pattern in ['xcapture_samples_*.csv', 'xcapture_syscend_*.csv', 
                       'xcapture_iorqend_*.csv', 'xcapture_kstacks_*.csv']:
            files = list(data_source.datadir.glob(pattern))
            logger.info(f"  {pattern}: {len(files)} files")
            if files:
                logger.info(f"    First file: {files[0].name}")
                
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

if __name__ == "__main__":
    test_query_execution()