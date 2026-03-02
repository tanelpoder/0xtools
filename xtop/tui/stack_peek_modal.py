#!/usr/bin/env python3
"""
Stack trace peek modal for displaying full stack traces.
"""

from textual.screen import ModalScreen
from textual.widgets import Static, Label
from textual.containers import Container, VerticalScroll
from textual.app import ComposeResult
from textual import events
from typing import Optional


class StackPeekModal(ModalScreen):
    """Modal screen for displaying full stack traces"""
    
    CSS = """
    StackPeekModal {
        align: center middle;
    }
    
    #stack-container {
        background: $panel;
        border: thick $primary;
        padding: 1;
        width: 80;
        height: 80%;
        max-height: 40;
    }
    
    #stack-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    
    #stack-hash {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    
    #stack-content {
        height: 1fr;
        overflow-y: auto;
        padding: 0 2;
    }
    
    #stack-footer {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }
    
    .stack-frame {
        margin: 0;
        padding: 0 1;
    }
    
    .stack-frame:hover {
        background: $secondary;
    }
    """
    
    def __init__(self, stack_hash: str, is_kernel: bool, stack_trace: Optional[str] = None):
        """Initialize stack peek modal
        
        Args:
            stack_hash: The stack hash identifier
            is_kernel: True for kernel stack, False for userspace stack
            stack_trace: The full stack trace string (semicolon-separated)
        """
        super().__init__()
        self.stack_hash = stack_hash
        self.is_kernel = is_kernel
        self.stack_trace = stack_trace
        self.stack_type = "Kernel" if is_kernel else "Userspace"
    
    def compose(self) -> ComposeResult:
        """Create the UI"""
        with Container(id="stack-container"):
            yield Label(f"{self.stack_type} Stack Trace", id="stack-title")
            yield Label(f"Hash: {self.stack_hash}", id="stack-hash")
            
            with VerticalScroll(id="stack-content"):
                if self.stack_trace:
                    # Split the stack trace by semicolon and display each frame
                    frames = self.stack_trace.split(';')
                    for i, frame in enumerate(frames):
                        frame = frame.strip()
                        if frame:
                            # Add frame number and indentation for readability
                            frame_text = f"{i:2d}: {frame}"
                            yield Static(frame_text, classes="stack-frame")
                else:
                    yield Static("No stack trace available", classes="stack-frame")
            
            yield Label("[Press ESC to close]", id="stack-footer")
    
    def on_key(self, event: events.Key) -> None:
        """Handle key events"""
        if event.key == "escape":
            event.stop()  # Stop event propagation
            self.dismiss()