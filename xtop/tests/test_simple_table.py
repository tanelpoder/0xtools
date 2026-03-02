#!/usr/bin/env python3
"""
Test simple DataTable in Textual to verify it's working
"""

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, Static, TabbedContent, TabPane

class SimpleTableApp(App):
    """Test simple table"""
    
    CSS = """
    DataTable {
        height: 100%;
        border: solid green;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create layout"""
        yield Header()
        yield Static("Test Table App")
        
        with TabbedContent():
            with TabPane("Test Tab", id="tab-0"):
                yield DataTable(id="test-table")
                
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize table with test data"""
        table = self.query_one("#test-table", DataTable)
        
        # Add columns
        table.add_column("Col1", key="col1")
        table.add_column("Col2", key="col2") 
        table.add_column("Col3", key="col3")
        
        # Add test data
        for i in range(10):
            table.add_row(f"Row {i}", f"Value {i}", f"Data {i}")
        
        # Focus the table
        table.focus()
        
        # Log what we did
        print(f"Added {len(table.columns)} columns and {table.row_count} rows")

if __name__ == "__main__":
    app = SimpleTableApp()
    app.run()