#!/usr/bin/env python3
"""
Utilities for column management and display in xtop.
Provides functions to build unified column lists with source labels.
"""

from typing import Dict, List, Tuple, Set


def get_unified_column_list(columns_by_source: Dict[str, List[str]], 
                           query_engine=None) -> List[Tuple[str, str, str]]:
    """
    Build a unified, alphabetically sorted list of all columns with source labels.
    
    Args:
        columns_by_source: Dictionary mapping source names to column lists
        query_engine: Optional query engine for accessing DATA_SOURCES metadata
        
    Returns:
        List of tuples: (column_name, display_name, column_id)
        where display_name includes the source label like "filename (samples)"
    """
    # Define computed/derived columns
    computed_columns = {
        'YYYY': 'timestamp',
        'MM': 'timestamp', 
        'DD': 'timestamp',
        'HH': 'timestamp',
        'MI': 'timestamp',
        'SS': 'timestamp',
        'S10': 'timestamp',
        'comm2': 'samples',  # derived from COMM in samples
        'filenamesum': 'samples',  # derived from FILENAME in samples
        'KSTACK_CURRENT_FUNC': 'kstacks',  # derived from kstacks
        'USTACK_CURRENT_FUNC': 'ustacks'   # derived from ustacks
    }
    
    # Map source names to shorter display names
    source_display_map = {
        'samples': 'samples',
        'syscend': 'syscall',
        'iorqend': 'iorq',
        'kstacks': 'kstack',
        'ustacks': 'ustack',
        'partitions': 'partition'
    }
    
    # Build complete column list with source info
    all_columns = []
    seen_columns = set()
    
    # Process columns from each source
    for source, columns in columns_by_source.items():
        source_label = source_display_map.get(source, source)
        
        for col in columns:
            col_lower = col.lower()
            
            # Skip if we've already added this column
            if col_lower in seen_columns:
                continue
                
            # Determine if this is a regular or derived column
            if col in computed_columns:
                # It's a computed column - show both source and that it's derived
                base_source = computed_columns[col]
                if base_source == 'timestamp':
                    display_name = f"{col_lower} (time)"
                else:
                    base_label = source_display_map.get(base_source, base_source)
                    display_name = f"{col_lower} ({base_label}, derived)"
            else:
                # Regular column from this source
                display_name = f"{col_lower} ({source_label})"
            
            # Use the column name as the ID (will be prefixed if needed)
            col_id = col
            
            all_columns.append((col, display_name, col_id))
            seen_columns.add(col_lower)
    
    # Add computed columns that weren't in any source
    for col, base_source in computed_columns.items():
        col_lower = col.lower()
        if col_lower not in seen_columns:
            if base_source == 'timestamp':
                display_name = f"{col_lower} (time)"
            else:
                base_label = source_display_map.get(base_source, base_source)
                display_name = f"{col_lower} (derived)"
            
            all_columns.append((col, display_name, col))
            seen_columns.add(col_lower)
    
    # Sort alphabetically by display name (which starts with column name)
    all_columns.sort(key=lambda x: x[1].lower())
    
    return all_columns


def filter_columns_by_pattern(columns: List[Tuple[str, str, str]], 
                             pattern: str) -> List[Tuple[str, str, str]]:
    """
    Filter columns by a search pattern (case-insensitive substring match).
    
    Args:
        columns: List of column tuples from get_unified_column_list
        pattern: Search pattern to filter by
        
    Returns:
        Filtered list of columns matching the pattern
    """
    if not pattern:
        return columns
    
    pattern_lower = pattern.lower()
    filtered = []
    
    for col_name, display_name, col_id in columns:
        # Check if pattern appears in the column name (not the source label)
        # Extract just the column name part from display_name
        col_part = display_name.split(' (')[0]
        if pattern_lower in col_part:
            filtered.append((col_name, display_name, col_id))
    
    return filtered