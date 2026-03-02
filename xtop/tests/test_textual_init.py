#!/usr/bin/env python3
"""
Test Textual TUI initialization and debug blank screen issue
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, TabbedContent, TabPane
from textual.containers import Container, Horizontal, Vertical
import logging

LABEL_WIDTH = 11

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/tmp/test_textual_init.log'
)
logger = logging.getLogger('test_init')

class TestInitApp(App):
    """Test initialization order"""
    
    CSS = """
    #breadcrumb {
        height: 4;
        padding: 1;
        margin: 0 1;
        border: solid green;
        background: $boost;
        color: $text;
    }
    
    DataTable {
        height: 100%;
        border: solid blue;
    }
    
    TabbedContent {
        height: 100%;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        logger.info("compose() called")
        
        yield Header()
        yield Static(
            "AvgThreads: (initialising)\n"
            f"{'TimeRange:'.ljust(LABEL_WIDTH)} Detecting...\n"
            f"{'Window:'.ljust(LABEL_WIDTH)} Pending...\n"
            f"{'Filters:'.ljust(LABEL_WIDTH)} No filters applied\n"
            f"{'Path:'.ljust(LABEL_WIDTH)} Loading...",
            id="breadcrumb",
        )
        
        with TabbedContent(id="tabs"):
            with TabPane("Main", id="tab-0"):
                yield DataTable(id="table-0")
                    
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize when app is mounted"""
        logger.info("on_mount() called")
        
        # Check if widgets exist
        try:
            breadcrumb = self.query_one("#breadcrumb", Static)
            logger.info(f"Found breadcrumb: {breadcrumb}")
            breadcrumb.update(
                "AvgThreads: test\n"
                f"{'TimeRange:'.ljust(LABEL_WIDTH)} Test\n"
                f"{'Window:'.ljust(LABEL_WIDTH)} Test window\n"
                f"{'Filters:'.ljust(LABEL_WIDTH)} Test filter\n"
                f"{'Path:'.ljust(LABEL_WIDTH)} Test path"
            )
            logger.info("Updated breadcrumb text")
        except Exception as e:
            logger.error(f"Failed to find breadcrumb: {e}")
        
        try:
            table = self.query_one("#table-0", DataTable)
            logger.info(f"Found table: {table}")
            
            # Add some test data
            table.add_column("Col1", key="col1")
            table.add_column("Col2", key="col2")
            table.add_row("Value1", "Value2")
            table.add_row("Value3", "Value4")
            logger.info("Added test data to table")
        except Exception as e:
            logger.error(f"Failed to find table: {e}")
        
        # Test tab switching
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            logger.info(f"Found tabs: {tabs}")
            logger.info(f"Active tab: {tabs.active}")
        except Exception as e:
            logger.error(f"Failed to find tabs: {e}")

if __name__ == "__main__":
    print("Testing Textual initialization...")
    print("Check /tmp/test_textual_init.log for debug output")
    print("")
    print("If you see data in the table and breadcrumb, the initialization is working.")
    print("Press Ctrl+C to exit.")
    
    app = TestInitApp()
    app.run()
