#!/usr/bin/env python3
"""
Navigation state management for interactive drill-down/back-out functionality.
Tracks navigation history and enables context-aware data exploration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import copy


@dataclass
class NavigationFrame:
    """Single frame in navigation history"""
    # Removed query_type - always dynamic now
    filters: Dict[str, Any]
    exclude_filters: Dict[str, Any] = field(default_factory=dict)  # For != conditions
    group_cols: List[str] = field(default_factory=list)
    sort_col: str = "samples"
    sort_desc: bool = True
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""
    
    def to_where_clause(self) -> str:
        """Convert filters to SQL WHERE clause"""
        conditions = []
        
        def qualify_column(col: str) -> str:
            """Qualify ambiguous columns with table alias"""
            # For dynamic queries, don't qualify columns - they're handled in query builder
            # Handle columns that might have source prefixes
            if '.' in col:
                return col  # Already qualified
            # Don't qualify columns - the query builder will handle proper qualification
            return col
        
        # Handle include filters (=)
        for col, value in self.filters.items():
            qualified_col = qualify_column(col)
            if value is None:
                conditions.append(f"{qualified_col} IS NULL")
            elif isinstance(value, str):
                # Escape single quotes in string values
                escaped_value = value.replace("'", "''")
                conditions.append(f"{qualified_col} = '{escaped_value}'")
            elif isinstance(value, (list, tuple)):
                # Handle IN clauses
                if all(isinstance(v, str) for v in value):
                    escaped_values = [v.replace("'", "''") for v in value]
                    values_str = "', '".join(escaped_values)
                    conditions.append(f"{qualified_col} IN ('{values_str}')")
                else:
                    values_str = ", ".join(str(v) for v in value)
                    conditions.append(f"{qualified_col} IN ({values_str})")
            else:
                conditions.append(f"{qualified_col} = {value}")
        
        # Handle exclude filters (!=)
        for col, value in self.exclude_filters.items():
            qualified_col = qualify_column(col)
            if value is None:
                conditions.append(f"{qualified_col} IS NOT NULL")
            elif isinstance(value, str):
                # Escape single quotes in string values
                escaped_value = value.replace("'", "''")
                conditions.append(f"{qualified_col} != '{escaped_value}'")
            elif isinstance(value, (list, tuple)):
                # Handle NOT IN clauses
                if all(isinstance(v, str) for v in value):
                    escaped_values = [v.replace("'", "''") for v in value]
                    values_str = "', '".join(escaped_values)
                    conditions.append(f"{qualified_col} NOT IN ('{values_str}')")
                else:
                    values_str = ", ".join(str(v) for v in value)
                    conditions.append(f"{qualified_col} NOT IN ({values_str})")
            else:
                conditions.append(f"{qualified_col} != {value}")
        
        return " AND ".join(conditions) if conditions else "1=1"
    
    def get_breadcrumb(self) -> str:
        """Get human-readable description of this frame"""
        if self.description:
            return self.description
        
        # Auto-generate description from filters
        parts = []
        for col, value in self.filters.items():
            if isinstance(value, (list, tuple)):
                parts.append(f"{col} in [{len(value)} values]")
            else:
                parts.append(f"{col}={value}")
        
        for col, value in self.exclude_filters.items():
            if isinstance(value, (list, tuple)):
                parts.append(f"{col} not in [{len(value)} values]")
            else:
                parts.append(f"{col}!={value}")
        
        if parts:
            return f"{self.query_type}: " + ", ".join(parts)
        else:
            return f"{self.query_type}: All data"


class NavigationState:
    """Manages drill-down/back-out navigation state"""
    
    def __init__(self):
        """Initialize navigation state"""
        self.history: List[NavigationFrame] = []
        self.current_frame: Optional[NavigationFrame] = None
        self.max_history = 100  # Prevent unlimited history growth
        self.grouping_history: List[List[str]] = []  # Track grouping changes for undo
    
    def reset(self, group_cols: Optional[List[str]] = None):
        """Reset navigation to initial state"""
        self.history.clear()
        # Standardize group columns to lowercase
        group_cols_lower = [col.lower() for col in (group_cols or [])]
        self.current_frame = NavigationFrame(
            filters={},
            group_cols=group_cols_lower,
            description="Initial view"
        )
    
    def drill_down(self, column: str, value: Any, 
                  new_group_cols: Optional[List[str]] = None,
                  exclude: bool = False) -> NavigationFrame:
        """
        Add filter and push current state to history.
        
        Args:
            column: Column to filter on
            value: Value to filter for (or exclude)
            new_group_cols: Optional new grouping columns
            exclude: If True, add as exclude filter (!=)
            
        Returns:
            New navigation frame
        """
        if self.current_frame is None:
            raise ValueError("No current frame to drill down from")
        
        # Push current frame to history
        self.history.append(copy.deepcopy(self.current_frame))
        
        # Trim history if too long
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        
        # Create new frame with additional filter
        new_filters = copy.deepcopy(self.current_frame.filters)
        new_exclude_filters = copy.deepcopy(self.current_frame.exclude_filters)
        
        if exclude:
            # If we're excluding a value, remove any include filter for the same column
            # to avoid contradictions like STATE=SLEEP AND STATE!=SLEEP
            if column in new_filters:
                del new_filters[column]
            new_exclude_filters[column] = value
            desc = f"Excluded {column}!={value}"
        else:
            # If we're including a value, remove any exclude filter for the same column
            if column in new_exclude_filters:
                del new_exclude_filters[column]
            new_filters[column] = value
            desc = f"Filtered by {column}={value}"
        
        # Use new group columns or keep existing
        group_cols = new_group_cols if new_group_cols is not None else self.current_frame.group_cols
        
        # Keep the filtered column in group_cols to remain visible
        # (it will show the same value for all rows, which is expected)
        
        self.current_frame = NavigationFrame(
            filters=new_filters,
            exclude_filters=new_exclude_filters,
            group_cols=group_cols,
            sort_col=self.current_frame.sort_col,
            sort_desc=self.current_frame.sort_desc,
            description=desc
        )
        
        return self.current_frame
    
    def back_out(self) -> Optional[NavigationFrame]:
        """
        Pop from history and restore previous state.
        
        Returns:
            Previous navigation frame or None if at root
        """
        if not self.history:
            return None
        
        # Restore previous frame
        self.current_frame = self.history.pop()
        return self.current_frame
    
    def remove_last_filter(self) -> bool:
        """
        Remove only the last WHERE filter (rightmost).
        Does not affect GROUP BY columns.
        
        Returns:
            True if a filter was removed, False if no filters to remove
        """
        if not self.current_frame:
            return False
        
        # Get all filters (both include and exclude)
        all_filters = []
        for col, val in self.current_frame.filters.items():
            all_filters.append(('include', col, val))
        for col, val in self.current_frame.exclude_filters.items():
            all_filters.append(('exclude', col, val))
        
        if not all_filters:
            return False
        
        # Remove the last filter (rightmost)
        filter_type, col, _ = all_filters[-1]
        
        if filter_type == 'include':
            if col in self.current_frame.filters:
                del self.current_frame.filters[col]
        else:  # exclude
            if col in self.current_frame.exclude_filters:
                del self.current_frame.exclude_filters[col]
        
        return True
    
    def get_breadcrumb_path(self) -> str:
        """
        Get full navigation path for display.
        
        Returns:
            Breadcrumb string like "All data > USERNAME=postgres > SYSCALL=pread64"
        """
        parts = []
        
        # Add history frames
        for frame in self.history:
            parts.append(frame.get_breadcrumb())
        
        # Add current frame
        if self.current_frame:
            parts.append(self.current_frame.get_breadcrumb())
        
        return " > ".join(parts) if parts else "No navigation"
    
    def get_current_filters(self) -> Dict[str, Any]:
        """Get current active filters"""
        if self.current_frame:
            return self.current_frame.filters
        return {}
    
    def get_filter_display(self) -> str:
        """Get human-readable filter display for breadcrumbs"""
        if not self.current_frame:
            return "No filters applied"
        
        filter_parts = []
        
        # Include filters
        for col, val in self.current_frame.filters.items():
            # Format the value appropriately
            if isinstance(val, str) and ' ' in val:
                filter_parts.append(f"{col}='{val}'")
            else:
                filter_parts.append(f"{col}={val}")
        
        # Exclude filters
        for col, val in self.current_frame.exclude_filters.items():
            # Format the value appropriately
            if isinstance(val, str) and ' ' in val:
                filter_parts.append(f"{col}!='{val}'")
            else:
                filter_parts.append(f"{col}!={val}")
        
        return " AND ".join(filter_parts) if filter_parts else "No filters applied"
    
    def get_current_where_clause(self) -> str:
        """Get current WHERE clause for SQL"""
        if self.current_frame:
            return self.current_frame.to_where_clause()
        return "1=1"
    
    def get_current_group_cols(self) -> List[str]:
        """Get current grouping columns"""
        if self.current_frame:
            return self.current_frame.group_cols
        return []
    
    def can_back_out(self) -> bool:
        """Check if back-out is possible"""
        return len(self.history) > 0
    
    def get_depth(self) -> int:
        """Get current navigation depth"""
        return len(self.history) + (1 if self.current_frame else 0)
    
    def change_query_type(self, new_query_type: str, 
                         default_group_cols: Optional[List[str]] = None):
        """
        Change query type while preserving filters.
        
        Args:
            new_query_type: New query type (top, sclathist, etc.)
            default_group_cols: Default grouping columns for new query type
        """
        if self.current_frame is None:
            self.reset(new_query_type, default_group_cols)
            return
        
        # Keep filters but change query type
        self.current_frame.query_type = new_query_type
        if default_group_cols is not None:
            self.current_frame.group_cols = default_group_cols
        self.current_frame.description = f"Changed to {new_query_type} view"
    
    def update_grouping(self, new_group_cols: List[str], create_history: bool = True):
        """
        Update grouping columns, optionally creating a new history frame.
        
        Args:
            new_group_cols: New grouping columns to use
            create_history: If True, push current state to history (for back-out)
        """
        if not self.current_frame:
            return
        
        # Standardize column names to lowercase
        new_group_cols = [col.lower() for col in new_group_cols]
        
        # Save current grouping to history if different
        if self.current_frame.group_cols != new_group_cols:
            self.grouping_history.append(copy.deepcopy(self.current_frame.group_cols))
            
            # Trim grouping history if too long
            if len(self.grouping_history) > self.max_history:
                self.grouping_history = self.grouping_history[-self.max_history:]
        
        # If creating history, push current frame
        if create_history and self.current_frame.group_cols != new_group_cols:
            self.history.append(copy.deepcopy(self.current_frame))
            
            # Trim history if too long
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
        
        # Update current frame's grouping
        self.current_frame.group_cols = new_group_cols
        self.current_frame.description = f"Grouped by {', '.join(new_group_cols)}"
    
    def undo_last_grouping(self) -> bool:
        """
        Undo the last grouping change.
        
        Returns:
            True if grouping was undone, False if no grouping history
        """
        if not self.grouping_history or not self.current_frame:
            return False
        
        # Restore previous grouping
        self.current_frame.group_cols = self.grouping_history.pop()
        return True
    
    def add_filter(self, column: str, value: Any):
        """Add a filter without creating new navigation frame"""
        if self.current_frame:
            self.current_frame.filters[column] = value
    
    def remove_filter(self, column: str):
        """Remove a filter from current frame"""
        if self.current_frame:
            if column in self.current_frame.filters:
                del self.current_frame.filters[column]
            if column in self.current_frame.exclude_filters:
                del self.current_frame.exclude_filters[column]
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current navigation state"""
        return {
            'depth': self.get_depth(),
            'can_back_out': self.can_back_out(),
            'current_query_type': self.current_frame.query_type if self.current_frame else None,
            'current_filters': self.get_current_filters(),
            'current_group_cols': self.get_current_group_cols(),
            'breadcrumb': self.get_breadcrumb_path()
        }