#!/usr/bin/env python3
"""
Navigation state management for interactive drill-down/back-out functionality.
Tracks navigation history and enables context-aware data exploration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import copy


_NAV_PREFIX_DISPLAY = {
    'sc': 'SC',
    'io': 'IO',
}

_NAV_LATENCY_SUFFIX_LABELS = {
    'min_lat_us': 'Min Lat (us)',
    'avg_lat_us': 'Avg Lat (us)',
    'max_lat_us': 'Max Lat (us)',
    'p50_us': 'P50 (us)',
    'p95_us': 'P95 (us)',
    'p99_us': 'P99 (us)',
    'p999_us': 'P999 (us)',
    'avg_lat_ms': 'Avg Lat (ms)',
}

_NAV_UNIT_SUFFIXES = {
    'us': 'us',
    'ms': 'ms',
    's': 's',
}

_NAV_LABEL_OVERRIDES: Dict[str, str] = {
    f"{prefix}.{suffix}": f"{prefix_label} {suffix_label}"
    for prefix, prefix_label in _NAV_PREFIX_DISPLAY.items()
    for suffix, suffix_label in _NAV_LATENCY_SUFFIX_LABELS.items()
}
_NAV_LABEL_OVERRIDES.update({
    'sclat_histogram': 'SC Latency Histogram',
    'iolat_histogram': 'IO Latency Histogram',
})


@dataclass
class NavigationFrame:
    """Single frame in navigation history"""

    filters: Dict[str, List[Any]] = field(default_factory=dict)
    exclude_filters: Dict[str, List[Any]] = field(default_factory=dict)
    group_cols: List[str] = field(default_factory=list)
    sort_col: str = "samples"
    sort_desc: bool = True
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)

    def to_where_clause(self) -> str:
        """Convert filters to SQL WHERE clause"""
        conditions: List[str] = []

        def qualify_column(col: str) -> str:
            """Qualify ambiguous columns with table alias"""
            if "." in col:
                return col  # Already qualified
            return col

        def _format_value(value: Any) -> str:
            if value is None:
                return "NULL"
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                return "'" + escaped + "'"
            return str(value)

        # Handle include filters (= / IN)
        for col, values in self.filters.items():
            if not values:
                continue
            qualified_col = qualify_column(col)
            if len(values) == 1:
                value = values[0]
                if value is None:
                    conditions.append(f"{qualified_col} IS NULL")
                else:
                    conditions.append(f"{qualified_col} = {_format_value(value)}")
            else:
                formatted = [_format_value(v) for v in values if v is not None]
                if len(formatted) != len(values):
                    # Separate NULL handling: column IS NULL OR column IN (...)
                    non_null = [v for v in values if v is not None]
                    clauses = []
                    if non_null:
                        formatted_non_null = ", ".join(_format_value(v) for v in non_null)
                        clauses.append(f"{qualified_col} IN ({formatted_non_null})")
                    if any(v is None for v in values):
                        clauses.append(f"{qualified_col} IS NULL")
                    conditions.append("(" + " OR ".join(clauses) + ")")
                else:
                    values_str = ", ".join(formatted)
                    conditions.append(f"{qualified_col} IN ({values_str})")

        # Handle exclude filters (!= / NOT IN)
        for col, values in self.exclude_filters.items():
            if not values:
                continue
            qualified_col = qualify_column(col)
            if len(values) == 1:
                value = values[0]
                if value is None:
                    conditions.append(f"{qualified_col} IS NOT NULL")
                else:
                    conditions.append(f"{qualified_col} != {_format_value(value)}")
            else:
                non_null = [v for v in values if v is not None]
                clauses = []
                if non_null:
                    formatted = ", ".join(_format_value(v) for v in non_null)
                    clauses.append(f"{qualified_col} NOT IN ({formatted})")
                if any(v is None for v in values):
                    clauses.append(f"{qualified_col} IS NOT NULL")
                conditions.append("(" + " AND ".join(clauses) + ")")

        return " AND ".join(conditions) if conditions else "1=1"

    def get_breadcrumb(self) -> str:
        """Get human-readable description of this frame"""
        if self.description:
            return self.description

        parts = []
        for col, values in self.filters.items():
            label = self.labels.get(col, col)
            if not values:
                continue
            summary = NavigationState._format_values_short(values)
            if len(values) == 1:
                parts.append(f"{label}={summary}")
            else:
                parts.append(f"{label} in {summary}")

        for col, values in self.exclude_filters.items():
            label = self.labels.get(col, col)
            if not values:
                continue
            summary = NavigationState._format_values_short(values)
            if len(values) == 1:
                parts.append(f"{label}!={summary}")
            else:
                parts.append(f"{label} not in {summary}")

        return " | ".join(parts) if parts else "All data"


class NavigationState:
    """Manages drill-down/back-out navigation state"""
    
    _PREFIX_DISPLAY = _NAV_PREFIX_DISPLAY
    _LATENCY_SUFFIX_LABELS = _NAV_LATENCY_SUFFIX_LABELS
    _UNIT_SUFFIXES = _NAV_UNIT_SUFFIXES
    _LABEL_OVERRIDES = _NAV_LABEL_OVERRIDES

    def __init__(self):
        """Initialize navigation state"""
        self.history: List[NavigationFrame] = []
        self.current_frame: Optional[NavigationFrame] = None
        self.max_history = 100  # Prevent unlimited history growth
        self.grouping_history: List[List[str]] = []  # Track grouping changes for undo

    @staticmethod
    def _canonical(column: str) -> str:
        """Normalize column keys for consistent comparisons."""
        if column is None:
            raise ValueError("Column name cannot be None")
        return str(column).strip().lower()

    @staticmethod
    def _normalize_values(values: Any) -> List[Any]:
        """Ensure filter values are stored as lists."""
        if values is None:
            return []
        if isinstance(values, list):
            return list(values)
        if isinstance(values, (tuple, set)):
            return list(values)
        return [values]

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a value for human-readable display."""
        if value is None:
            return "NULL"
        if isinstance(value, str):
            return f"'{value}'" if ' ' in value else value
        return str(value)

    @classmethod
    def _format_values_short(cls, values: List[Any]) -> str:
        """Short display for a list of values."""
        if not values:
            return "[]"
        if len(values) == 1:
            return cls._format_value(values[0])
        if len(values) <= 3:
            formatted = ", ".join(cls._format_value(v) for v in values)
            return f"[{formatted}]"
        preview = ", ".join(cls._format_value(v) for v in values[:3])
        remaining = len(values) - 3
        return f"[{preview}, ... +{remaining} more]"

    @classmethod
    def _format_label(cls, column: str) -> str:
        """Return a human-readable label for the provided column name."""
        if column is None:
            return ""

        raw = str(column).strip()
        if not raw:
            return raw

        key = raw.lower()

        override = cls._LABEL_OVERRIDES.get(key)
        if override:
            return override

        if "." in key:
            prefix, suffix = key.split(".", 1)
            prefix_display = cls._PREFIX_DISPLAY.get(prefix, prefix.upper())

            suffix_label = cls._LATENCY_SUFFIX_LABELS.get(suffix)
            if suffix_label:
                return f"{prefix_display} {suffix_label}"

            parts = suffix.split("_")
            words = []
            unit: Optional[str] = None

            for part in parts:
                if part in cls._UNIT_SUFFIXES:
                    unit = cls._UNIT_SUFFIXES[part]
                    continue

                if part.isalpha():
                    words.append(part.capitalize())
                else:
                    words.append(part.upper())

            if words and unit:
                return f"{prefix_display} {' '.join(words)} ({unit})"
            if words:
                return f"{prefix_display} {' '.join(words)}"
            if unit:
                return f"{prefix_display} ({unit})"
            return prefix_display

        return raw
    
    def reset(self, group_cols: Optional[List[str]] = None):
        """Reset navigation to initial state"""
        self.history.clear()
        self.grouping_history.clear()
        # Standardize group columns to lowercase
        group_cols_lower = [self._canonical(col) for col in (group_cols or [])]
        self.current_frame = NavigationFrame(
            filters={},
            exclude_filters={},
            group_cols=group_cols_lower,
            description="All data"
        )
    
    def drill_down(
        self,
        column: str,
        value: Any,
        new_group_cols: Optional[List[str]] = None,
        exclude: bool = False,
    ) -> NavigationFrame:
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
        new_labels = copy.deepcopy(self.current_frame.labels)

        column_key = self._canonical(column)
        values = self._normalize_values(value)
        display_label = self._format_label(column)

        if exclude:
            # If we're excluding a value, remove any include filter for the same column
            # to avoid contradictions like STATE=SLEEP AND STATE!=SLEEP
            if column_key in new_filters:
                del new_filters[column_key]
            new_exclude_filters[column_key] = values
            new_labels[column_key] = display_label
            desc = f"Excluded {display_label}!={self._format_values_short(values)}"
        else:
            # If we're including a value, remove any exclude filter for the same column
            if column_key in new_exclude_filters:
                del new_exclude_filters[column_key]
            new_filters[column_key] = values
            new_labels[column_key] = display_label
            desc = f"Filtered by {display_label}={self._format_values_short(values)}"
        
        # Use new group columns or keep existing
        if new_group_cols is not None:
            group_cols = [self._canonical(col) for col in new_group_cols]
        else:
            group_cols = list(self.current_frame.group_cols)
        
        # Keep the filtered column in group_cols to remain visible
        # (it will show the same value for all rows, which is expected)
        
        self.current_frame = NavigationFrame(
            filters=new_filters,
            exclude_filters=new_exclude_filters,
            group_cols=group_cols,
            sort_col=self.current_frame.sort_col,
            sort_desc=self.current_frame.sort_desc,
            description=desc,
            labels=new_labels,
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

        if (
            col not in self.current_frame.filters
            and col not in self.current_frame.exclude_filters
        ):
            self.current_frame.labels.pop(col, None)

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
        for col, values in self.current_frame.filters.items():
            if not values:
                continue
            label = self.current_frame.labels.get(col, col)
            summary = self._format_values_short(values)
            if len(values) == 1:
                filter_parts.append(f"{label}={summary}")
            else:
                filter_parts.append(f"{label} in {summary}")

        # Exclude filters
        for col, values in self.current_frame.exclude_filters.items():
            if not values:
                continue
            label = self.current_frame.labels.get(col, col)
            summary = self._format_values_short(values)
            if len(values) == 1:
                filter_parts.append(f"{label}!={summary}")
            else:
                filter_parts.append(f"{label} not in {summary}")

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
        new_group_cols = [self._canonical(col) for col in new_group_cols]
        
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
            key = self._canonical(column)
            self.current_frame.filters[key] = self._normalize_values(value)
            self.current_frame.exclude_filters.pop(key, None)
            self.current_frame.labels[key] = self._format_label(column)

    def remove_filter(self, column: str):
        """Remove a filter from current frame"""
        if self.current_frame:
            key = self._canonical(column)
            self.current_frame.filters.pop(key, None)
            self.current_frame.exclude_filters.pop(key, None)
            if (
                key not in self.current_frame.filters
                and key not in self.current_frame.exclude_filters
            ):
                self.current_frame.labels.pop(key, None)

    def apply_value_filters(
        self,
        column: str,
        include_values: Optional[List[Any]] = None,
        exclude_values: Optional[List[Any]] = None,
    ) -> bool:
        """Apply include/exclude filters for a column in one navigation step.

        Returns True when filters changed, False otherwise.
        """
        if self.current_frame is None:
            return False

        include_list = self._normalize_values(include_values)
        exclude_list = self._normalize_values(exclude_values)

        key = self._canonical(column)
        display_label = self._format_label(column)

        new_filters = copy.deepcopy(self.current_frame.filters)
        new_excludes = copy.deepcopy(self.current_frame.exclude_filters)
        new_labels = copy.deepcopy(self.current_frame.labels)

        if include_list:
            new_filters[key] = include_list
            new_excludes.pop(key, None)
            new_labels[key] = display_label
        else:
            new_filters.pop(key, None)

        if exclude_list:
            new_excludes[key] = exclude_list
            new_filters.pop(key, None)
            new_labels[key] = display_label
        else:
            new_excludes.pop(key, None)

        if key not in new_filters and key not in new_excludes:
            new_labels.pop(key, None)

        if (
            new_filters == self.current_frame.filters
            and new_excludes == self.current_frame.exclude_filters
        ):
            return False

        # Push history frame for undo/back-out
        self.history.append(copy.deepcopy(self.current_frame))
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

        if include_list and exclude_list:
            description = (
                f"Updated filters on {display_label} "
                f"(include {self._format_values_short(include_list)}, "
                f"exclude {self._format_values_short(exclude_list)})"
            )
        elif include_list:
            description = (
                f"Included {display_label}="
                f"{self._format_values_short(include_list)}"
            )
        elif exclude_list:
            description = (
                f"Excluded {display_label}!="
                f"{self._format_values_short(exclude_list)}"
            )
        else:
            description = f"Cleared filters on {display_label}"

        self.current_frame = NavigationFrame(
            filters=new_filters,
            exclude_filters=new_excludes,
            group_cols=self.current_frame.group_cols,
            sort_col=self.current_frame.sort_col,
            sort_desc=self.current_frame.sort_desc,
            description=description,
            labels=new_labels,
        )

        return True
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current navigation state"""
        return {
            'depth': self.get_depth(),
            'can_back_out': self.can_back_out(),
            'current_filters': self.get_current_filters(),
            'current_group_cols': self.get_current_group_cols(),
            'breadcrumb': self.get_breadcrumb_path()
        }
