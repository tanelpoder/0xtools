#!/usr/bin/env python3
"""
Modal dialog for displaying pretty-printed JSON data.
Used for viewing extra_info column contents in a readable format.
"""

import json
import logging
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Static, RichLog
from textual.screen import ModalScreen
from textual.binding import Binding
from typing import Any, Optional


class JSONViewerModal(ModalScreen[None]):
    """Modal screen for displaying pretty-printed JSON data"""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close"),
    ]
    
    CSS = """
    JSONViewerModal {
        align: center middle;
    }
    
    #json-container {
        width: 80%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #json-header {
        height: 3;
        background: $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    
    #json-title {
        text-style: bold;
        color: $text;
    }
    
    ScrollableContainer {
        height: 1fr;
        overflow-y: auto;
        overflow-x: auto;
    }
    
    RichLog {
        height: auto;
        background: $surface;
        padding: 1;
        width: auto;
    }
    
    .json-footer {
        height: 2;
        padding: 0 1;
        margin-top: 1;
        dock: bottom;
    }
    
    .dim {
        opacity: 0.6;
    }
    
    .error {
        color: $error;
        text-style: bold;
    }
    """
    
    def __init__(self, 
                 column_name: str,
                 json_data: str,
                 row_context: Optional[dict] = None,
                 **kwargs):
        """Initialize JSON viewer modal
        
        Args:
            column_name: Name of the column being viewed (usually 'extra_info')
            json_data: JSON string to display
            row_context: Optional full row data for additional context
        """
        super().__init__(**kwargs)
        self.column_name = column_name
        self.json_data = json_data
        self.row_context = row_context or {}
        self.logger = logging.getLogger('xtop.json_viewer')
    
    def compose(self) -> ComposeResult:
        """Build the JSON viewer UI"""
        with Container(id="json-container"):
            with Vertical(id="json-header"):
                # Build context display from row data
                context_display = self._build_context_display()
                title = f"JSON Viewer: {self.column_name}"
                if context_display:
                    title += f" | {context_display}"
                yield Label(title, id="json-title")
            
            # Use scrollable container for JSON content
            with ScrollableContainer():
                # Use RichLog without markup for clean JSON display
                # The highlight=True will provide basic syntax highlighting
                json_log = RichLog(highlight=True, markup=False, auto_scroll=False, wrap=False)
                
                # Parse and format the JSON
                formatted_json = self._format_json()
                
                # Write the formatted JSON to the log
                if formatted_json:
                    json_log.write(formatted_json)
                else:
                    json_log.write("Invalid or empty JSON data", classes="error")
                
                yield json_log
            
            with Horizontal(classes="json-footer"):
                yield Label("Press [ESC] or [Q] to close", classes="dim")
    
    def _format_json(self) -> Optional[str]:
        """Parse and pretty-print the JSON data
        
        Returns:
            Formatted JSON string, or None if invalid
        """
        if not self.json_data or self.json_data == '-':
            return None
        
        try:
            # Parse the JSON string
            json_obj = json.loads(self.json_data)
            
            # Pretty-print with indentation
            formatted = json.dumps(json_obj, indent=2, sort_keys=False, ensure_ascii=False)
            
            # Return the clean formatted JSON
            # RichLog with highlight=True will provide basic syntax highlighting
            return formatted
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON: {e}")
            # Try to show the raw data with error information
            return f"JSON Parse Error: {str(e)}\n\nRaw data:\n{self.json_data}"
        except Exception as e:
            self.logger.error(f"Unexpected error formatting JSON: {e}")
            return f"Error: {str(e)}\n\nRaw data:\n{self.json_data}"
    
    def _build_context_display(self) -> str:
        """Build a context display from row data
        
        Returns:
            String showing key context fields from the row
        """
        if not self.row_context:
            return ""
        
        # Pick important context fields to show
        context_fields = []
        
        # Priority fields for context
        important_fields = ['tid', 'comm', 'exe', 'state', 'syscall', 'filename']
        
        for field in important_fields:
            if field in self.row_context:
                value = self.row_context[field]
                if value and str(value) != '-':
                    # Truncate long values
                    str_value = str(value)
                    if len(str_value) > 20:
                        str_value = str_value[:17] + "..."
                    context_fields.append(f"{field}={str_value}")
        
        # Limit to first 3 fields to keep title reasonable
        return " | ".join(context_fields[:3])