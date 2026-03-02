#!/usr/bin/env python3
"""
Cursor position management for xtop TUI.
Helps maintain cursor position across data refreshes and column changes.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass
import logging


@dataclass
class CursorState:
    """Stores cursor state for restoration after refresh"""
    row: int
    column: int
    column_name: Optional[str] = None
    cell_value: Optional[str] = None
    
    def __repr__(self) -> str:
        return f"CursorState(row={self.row}, col={self.column}, col_name={self.column_name})"


class CursorManager:
    """Manages cursor position persistence across table updates"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize cursor manager"""
        self.logger = logger
        self._saved_state: Optional[CursorState] = None
        self._column_history: List[str] = []
    
    def save_position(self, table, display_columns: List[str]) -> Optional[CursorState]:
        """
        Save current cursor position from table
        
        Args:
            table: DataTable widget
            display_columns: Current list of display column names
            
        Returns:
            Saved cursor state or None if no position
        """
        try:
            if not table or not table.cursor_coordinate:
                return None
            
            cursor_coord = table.cursor_coordinate
            state = CursorState(
                row=cursor_coord.row,
                column=cursor_coord.column
            )
            
            # Try to save column name for better restoration
            if display_columns and cursor_coord.column < len(display_columns):
                state.column_name = display_columns[cursor_coord.column]
            
            # Try to save cell value for finding similar row
            try:
                if cursor_coord.row < table.row_count:
                    # This is tricky as we'd need the actual data
                    # For now, just save position
                    pass
            except:
                pass
            
            self._saved_state = state
            
            if self.logger:
                self.logger.debug(f"Saved cursor state: {state}")
            
            return state
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to save cursor position: {e}")
            return None
    
    def restore_position(self, table, display_columns: List[str], 
                         prefer_state: Optional[CursorState] = None) -> bool:
        """
        Restore cursor position to table
        
        Args:
            table: DataTable widget
            display_columns: Current list of display column names
            prefer_state: Optional specific state to restore (uses saved if not provided)
            
        Returns:
            True if position was restored, False otherwise
        """
        state = prefer_state or self._saved_state
        if not state:
            return False
        
        try:
            if not table or table.row_count == 0 or not table.columns:
                return False
            
            # Determine target column
            target_col = state.column
            
            # Try to find column by name if available
            if state.column_name and display_columns:
                target_col = self._find_column_index(
                    state.column_name, 
                    display_columns, 
                    state.column
                )
            
            # Ensure indices are within bounds
            target_row = min(state.row, table.row_count - 1)
            target_col = min(target_col, len(table.columns) - 1)
            
            # Move cursor
            table.move_cursor(row=target_row, column=target_col)
            
            if self.logger:
                self.logger.debug(f"Restored cursor to row={target_row}, col={target_col}")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to restore cursor position: {e}")
            return False
    
    def _find_column_index(self, column_name: str, display_columns: List[str], 
                           default_index: int) -> int:
        """
        Find column index by name, handling variations
        
        Args:
            column_name: Column name to find
            display_columns: List of current display columns
            default_index: Default index if not found
            
        Returns:
            Column index
        """
        # Direct match
        if column_name in display_columns:
            return display_columns.index(column_name)
        
        # Case-insensitive match
        column_lower = column_name.lower()
        for i, col in enumerate(display_columns):
            if col.lower() == column_lower:
                return i
        
        # Try matching with underscore/dot variations
        column_normalized = column_name.replace('.', '_').lower()
        for i, col in enumerate(display_columns):
            if col.replace('.', '_').lower() == column_normalized:
                return i
        
        # Try prefix matching for columns like sc.p99_us
        if '.' in column_name:
            base_name = column_name.split('.', 1)[1]
            for i, col in enumerate(display_columns):
                if col == base_name or (col.endswith(base_name)):
                    return i
        
        return default_index
    
    def track_column_navigation(self, column_name: str):
        """Track column navigation for smart restoration"""
        self._column_history.append(column_name)
        # Keep only last 10 columns
        if len(self._column_history) > 10:
            self._column_history = self._column_history[-10:]
    
    def get_preferred_column(self, available_columns: List[str]) -> Optional[str]:
        """Get preferred column based on navigation history"""
        if not self._column_history:
            return None
        
        # Try to find most recently used column that's still available
        for col in reversed(self._column_history):
            if col in available_columns:
                return col
        
        return None
    
    def clear(self):
        """Clear saved state and history"""
        self._saved_state = None
        self._column_history.clear()