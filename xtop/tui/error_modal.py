#!/usr/bin/env python3
"""
Modal dialog for displaying error messages to the user.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Label, Static, Button
from textual.screen import ModalScreen
from textual.binding import Binding
from typing import Optional


class ErrorModal(ModalScreen[None]):
    """Modal screen for displaying error messages"""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("enter", "dismiss", "Close"),
    ]
    
    CSS = """
    ErrorModal {
        align: center middle;
    }
    
    #error-container {
        width: 70%;
        max-width: 80;
        max-height: 30;
        background: $error;
        border: thick $error;
        padding: 1;
    }
    
    #error-title {
        text-align: center;
        background: $error;
        color: $text;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
    }
    
    #error-message {
        padding: 1;
        margin-bottom: 1;
        background: $surface;
        border: solid $error;
    }
    
    #error-details {
        padding: 1;
        color: $text-muted;
        text-style: italic;
    }
    
    .error-footer {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    #ok-button {
        width: 16;
        align: center middle;
    }
    """
    
    def __init__(self, 
                 title: str = "Error",
                 error_message: str = "An error occurred",
                 details: Optional[str] = None):
        """Initialize the error modal
        
        Args:
            title: Title for the error modal
            error_message: Main error message to display
            details: Optional additional details or instructions
        """
        super().__init__()
        self.title = title
        self.error_message = error_message
        self.details = details
    
    def compose(self) -> ComposeResult:
        """Compose the modal layout"""
        with Container(id="error-container"):
            yield Label(f"⚠️ {self.title}", id="error-title")
            
            with Vertical():
                # Main error message
                yield Static(self.error_message, id="error-message")
                
                # Optional details
                if self.details:
                    yield Label(self.details, id="error-details")
                
                # Footer with button
                with Container(classes="error-footer"):
                    yield Button("OK [Enter/ESC]", id="ok-button", variant="error")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == "ok-button":
            self.dismiss(None)
    
    def action_dismiss(self) -> None:
        """Dismiss the modal"""
        self.dismiss(None)