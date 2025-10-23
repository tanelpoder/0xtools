#!/usr/bin/env python3
"""Value filter modal with search and include/exclude toggles for xtop TUI."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option


@dataclass
class ValueEntry:
    """Represents a filterable value in the modal."""

    key: str
    value: Any
    display: str
    count: int
    state: str = "none"  # one of: none, include, exclude


_STATE_LABEL = {
    "none": "[ ]",
    "include": "[+]",
    "exclude": "[-]",
}


def _ensure_sequence(values: Optional[Any]) -> List[Any]:
    if values is None:
        return []
    if isinstance(values, (list, tuple, set)):
        return list(values)
    return [values]


class ValueFilterModal(ModalScreen):
    """Modal that lets the user search values and toggle include/exclude filters."""

    CSS = """
    ValueFilterModal {
        align: center middle;
    }

    #value-filter-container {
        background: $panel;
        border: thick $primary;
        padding: 1;
        width: 70;
        height: 24;
        max-height: 90%;
    }

    #value-filter-title {
        text-align: center;
        text-style: bold;
        margin: 0 0 1 0;
        height: 1;
    }

    #value-filter-search {
        text-align: center;
        color: $text-muted;
        height: 1;
    }

    #value-filter-instructions {
        text-align: center;
        color: $text-muted;
        height: 2;
        margin-bottom: 1;
    }

    OptionList {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(
        self,
        column_name: str,
        entries: List[ValueEntry],
        initial_include: Optional[Any] = None,
        initial_exclude: Optional[Any] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.column_name = column_name
        self.entries: Dict[str, ValueEntry] = {entry.key: entry for entry in entries}
        self.search_pattern = ""
        self.option_list: Optional[OptionList] = None
        self.filtered_keys: List[str] = []
        self._last_highlight_key: Optional[str] = None

        include_values = _ensure_sequence(initial_include)
        exclude_values = _ensure_sequence(initial_exclude)
        for entry in self.entries.values():
            if entry.value in include_values:
                entry.state = "include"
            elif entry.value in exclude_values:
                entry.state = "exclude"

    def compose(self) -> ComposeResult:
        with Container(id="value-filter-container"):
            yield Label(f"Filter {self.column_name}", id="value-filter-title")
            yield Label("Type to search, BACKSPACE to clear", id="value-filter-search")
            yield Label(
                "SPACE cycles include/exclude, ENTER applies, ESC cancels",
                id="value-filter-instructions",
            )
            option_list = OptionList()
            option_list.focus()
            self.option_list = option_list
            yield option_list

    def on_mount(self) -> None:
        self._refresh_options()

    def _refresh_options(self) -> None:
        if not self.option_list:
            return

        current_key = None
        if (
            self.option_list.highlighted is not None
            and 0 <= self.option_list.highlighted < len(self.filtered_keys)
        ):
            current_key = self.filtered_keys[self.option_list.highlighted]

        if self._last_highlight_key is not None:
            current_key = self._last_highlight_key
            self._last_highlight_key = None

        self.option_list.clear_options()
        pattern = self.search_pattern.lower()
        self.filtered_keys = []

        for entry in self._filtered_entries(pattern):
            label = f"{_STATE_LABEL[entry.state]} {entry.display}"
            if entry.count:
                label += f" ({entry.count})"
            self.filtered_keys.append(entry.key)
            self.option_list.add_option(Option(label, id=entry.key))

        try:
            search_label = self.query_one("#value-filter-search", Label)
            if self.search_pattern:
                search_label.update(
                    f"Search: '{self.search_pattern}' ({len(self.filtered_keys)} matches)"
                )
            else:
                search_label.update("Type to search, BACKSPACE to clear")
        except Exception:
            pass

        if self.filtered_keys:
            if current_key and current_key in self.filtered_keys:
                self.option_list.highlighted = self.filtered_keys.index(current_key)
            elif self.option_list.highlighted is None or self.option_list.highlighted >= len(self.filtered_keys):
                self.option_list.highlighted = 0

    def _filtered_entries(self, pattern: str) -> List[ValueEntry]:
        entries = list(self.entries.values())
        if not pattern:
            return entries
        return [entry for entry in entries if pattern in entry.display.lower()]

    def _toggle_current(self) -> None:
        if not self.option_list or self.option_list.highlighted is None:
            return
        if not self.filtered_keys:
            return

        key = self.filtered_keys[self.option_list.highlighted]
        entry = self.entries.get(key)
        if not entry:
            return

        entry.state = {
            "none": "include",
            "include": "exclude",
            "exclude": "none",
        }[entry.state]
        self._last_highlight_key = key
        self._refresh_options()

    def _accept(self) -> None:
        includes = [entry.value for entry in self.entries.values() if entry.state == "include"]
        excludes = [entry.value for entry in self.entries.values() if entry.state == "exclude"]
        self.dismiss((includes, excludes))

    def _clear_search_last(self) -> None:
        if self.search_pattern:
            self.search_pattern = self.search_pattern[:-1]
            self._refresh_options()

    def _append_search(self, char: str) -> None:
        self.search_pattern += char
        self._refresh_options()

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._toggle_current()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
            return

        if event.key == "enter":
            event.stop()
            self._accept()
            return

        if event.key == "space":
            event.stop()
            self._toggle_current()
            return

        if event.key == "backspace":
            event.stop()
            self._clear_search_last()
            return

        if event.character and event.character.isprintable():
            event.stop()
            self._append_search(event.character)
            return

        # Allow other keys (like arrow navigation) to propagate to OptionList
