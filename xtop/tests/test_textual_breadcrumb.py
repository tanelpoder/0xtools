#!/usr/bin/env python3
"""
Test Textual TUI breadcrumb display
"""

from textual.app import App, ComposeResult
from textual.widgets import Label, DataTable
from textual.containers import Vertical

class BreadcrumbTest(App):
    """Test breadcrumb display"""
    
    CSS = """
    .breadcrumb {
        height: 3;
        padding: 1;
        background: blue;
        border: solid white;
        color: white;
    }
    
    DataTable {
        height: 100%;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create test layout"""
        with Vertical():
            yield Label("Filters: USERNAME=test | Path: top > test", 
                       id="breadcrumb", 
                       classes="breadcrumb")
            yield DataTable()
    
    def on_mount(self) -> None:
        """Initialize"""
        # Add some test data to table
        table = self.query_one(DataTable)
        table.add_column("Column1")
        table.add_column("Column2")
        table.add_row("Value1", "Value2")
        
        # Update breadcrumb
        breadcrumb = self.query_one("#breadcrumb", Label)
        breadcrumb.update("Filters: USERNAME=postgres AND STATE=SLEEP | Path: top > filtered")

if __name__ == "__main__":
    app = BreadcrumbTest()
    app.run()
