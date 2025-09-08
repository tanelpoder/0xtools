#!/usr/bin/env python3
"""
Improved column selection modals for xtop TUI with better UX and selection indicators.
"""

from typing import List, Dict, Set, Optional, Tuple
from textual import events, on
from textual.app import ComposeResult
from textual.widgets import OptionList, Label
from textual.widgets.option_list import Option
from textual.containers import Container
from textual.screen import ModalScreen


class ImprovedColumnSelectionModal(ModalScreen):
    """Base class for improved column selection modals with live selection updates"""
    
    CSS = """
    ImprovedColumnSelectionModal {
        align: center middle;
    }
    
    #modal-container {
        background: $panel;
        border: thick $primary;
        padding: 1;
        width: 70;
        height: 24;
        max-height: 90%;
    }
    
    #modal-title {
        text-align: center;
        text-style: bold;
        margin: 0 0 1 0;
        height: 1;
    }
    
    #current-selection {
        margin: 0 0 1 0;
        color: $text-muted;
        height: 2;
    }
    
    #search-display {
        margin: 0 0 0 0;
        text-align: center;
        color: $text-muted;
        height: 1;
    }
    
    #instructions {
        margin: 0 0 1 0;
        text-align: center;
        color: $text-muted;
        height: 1;
    }
    
    OptionList {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """
    
    def __init__(self, 
                 title: str,
                 available_columns: List[Tuple[str, str, str]],
                 selected_columns: Set[str],
                 **kwargs):
        """
        Initialize improved column selection modal
        
        Args:
            title: Modal title
            available_columns: List of (col_name, display_name, col_id) tuples
            selected_columns: Set of currently selected column IDs
        """
        super().__init__(**kwargs)
        self.title = title
        self.all_columns = available_columns
        self.selected_columns = set(selected_columns)
        self.search_pattern = ""
        self._option_list = None
        self._saved_highlight = None
    
    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        with Container(id="modal-container"):
            yield Label(self.title, id="modal-title")
            yield Label(self._get_current_selection_text(), id="current-selection")
            yield Label("Type to search, BACKSPACE to clear", id="search-display")
            yield Label("Use SPACE to toggle, ENTER to apply, ESC to cancel", id="instructions")
            
            option_list = OptionList()
            self._option_list = option_list
            option_list.focus()
            yield option_list
    
    def on_mount(self) -> None:
        """Initialize the column list when mounted"""
        self.refresh_column_list()
    
    def _get_current_selection_text(self) -> str:
        """Get formatted text for current selection"""
        if self.selected_columns:
            # Sort and truncate if too many
            sorted_cols = sorted(self.selected_columns)
            if len(sorted_cols) > 5:
                display = ", ".join(sorted_cols[:5]) + f" (+{len(sorted_cols)-5} more)"
            else:
                display = ", ".join(sorted_cols)
            return f"Current: {display}"
        return "Current: None"
    
    def refresh_column_list(self, maintain_position: bool = True):
        """Refresh the column list based on search pattern"""
        from core.column_utils import filter_columns_by_pattern
        
        if not self._option_list:
            return
        
        # Save current highlight position
        if maintain_position and self._option_list.highlighted is not None:
            self._saved_highlight = self._option_list.highlighted
        
        # Clear and rebuild list
        self._option_list.clear_options()
        
        # Filter columns
        filtered = filter_columns_by_pattern(self.all_columns, self.search_pattern)
        
        # Add filtered columns
        for col_name, display_name, col_id in filtered:
            # Build option text with selection indicator
            checkbox = "[x]" if col_id in self.selected_columns else "[ ]"
            option_text = f"{checkbox} {display_name}"
            self._option_list.add_option(Option(option_text, id=col_id))
        
        # Restore highlight position if possible
        if maintain_position and self._saved_highlight is not None:
            if self._saved_highlight < len(self._option_list.options):
                self._option_list.highlighted = self._saved_highlight
        
        # Update search display
        self._update_search_display(len(filtered))
    
    def _update_search_display(self, match_count: int):
        """Update the search display label"""
        try:
            search_label = self.query_one("#search-display", Label)
            if self.search_pattern:
                search_label.update(f"Search: '{self.search_pattern}' ({match_count} matches)")
            else:
                search_label.update("Type to search, BACKSPACE to clear")
        except:
            pass
    
    def _toggle_current_selection(self):
        """Toggle the currently highlighted selection"""
        if not self._option_list:
            return
        
        highlighted_index = self._option_list.highlighted
        if highlighted_index is None:
            return
        
        try:
            option = self._option_list.get_option_at_index(highlighted_index)
            col_id = option.id
            
            # Skip headers
            if col_id.startswith('_header_'):
                return
            
            # Toggle selection
            if col_id in self.selected_columns:
                self.selected_columns.remove(col_id)
                new_checkbox = "[ ]"
            else:
                self.selected_columns.add(col_id)
                new_checkbox = "[x]"
            
            # Save scroll position
            current_scroll = self._option_list.scroll_offset
            
            # Refresh to update checkbox (no better way in current Textual API)
            self.refresh_column_list(maintain_position=True)
            
            # Restore scroll position
            if current_scroll:
                self._option_list.scroll_to(current_scroll.x, current_scroll.y, animate=False)
            
            # Update current selection display
            try:
                current_label = self.query_one("#current-selection", Label)
                current_label.update(self._get_current_selection_text())
            except:
                pass
            
        except Exception:
            pass
    
    def on_key(self, event: events.Key) -> None:
        """Handle keyboard input"""
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
        elif event.key == "enter":
            event.stop()
            self.dismiss(list(self.selected_columns))
        elif event.key == "space":
            event.stop()
            self._toggle_current_selection()
            event.prevent_default()
        elif event.key == "backspace":
            event.stop()
            if self.search_pattern:
                self.search_pattern = self.search_pattern[:-1]
                self.refresh_column_list(maintain_position=False)
        elif event.character and event.character.isprintable():
            event.stop()
            self.search_pattern += event.character
            self.refresh_column_list(maintain_position=False)


class GroupByColumnsModal(ImprovedColumnSelectionModal):
    """Modal for selecting GROUP BY columns with improved UX"""
    
    def __init__(self, available_columns: Dict[str, List[str]], 
                 current_columns: List[str], **kwargs):
        """
        Initialize GROUP BY column selection modal
        
        Args:
            available_columns: Dict mapping source to list of column names
            current_columns: Currently selected GROUP BY columns
        """
        # Build unified column list
        from core.column_utils import get_unified_column_list
        all_columns = get_unified_column_list(available_columns)
        
        # Convert current columns to set (case-insensitive)
        selected = set(col.lower() for col in current_columns)
        
        super().__init__(
            title="Select GROUP BY Columns",
            available_columns=all_columns,
            selected_columns=selected,
            **kwargs
        )


class LatencyColumnsModal(ImprovedColumnSelectionModal):
    """Modal for selecting latency/aggregate columns with improved UX"""
    
    def __init__(self, available_columns: Dict[str, List[str]], 
                 selected_columns: List[str], **kwargs):
        """
        Initialize latency column selection modal
        
        Args:
            available_columns: Dict of available latency columns
            selected_columns: Currently selected latency columns
        """
        # Build column list from available_columns
        all_columns = []
        for source, cols in available_columns.items():
            for col in cols:
                display_name = f"{col} ({source})"
                all_columns.append((col, display_name, col))
        
        # Sort alphabetically
        all_columns.sort(key=lambda x: x[1].lower())
        
        super().__init__(
            title="Select Latency/Aggregate Columns",
            available_columns=all_columns,
            selected_columns=set(selected_columns),
            **kwargs
        )