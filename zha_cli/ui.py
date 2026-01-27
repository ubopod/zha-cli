"""Terminal GUI using rich."""

from __future__ import annotations

import asyncio
import os
import re
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from zha_cli.coordinator_probe import DetectedCoordinator

console = Console()

# Menu navigation constants
MENU_BACK = -1
MENU_HOME = -2
MENU_CANCEL = 0

# Number of visible options in the menu
VISIBLE_OPTIONS = 3

# Box drawing characters (rounded corners)
BOX_TL = "╭"  # Top left
BOX_TR = "╮"  # Top right
BOX_BL = "╰"  # Bottom left
BOX_BR = "╯"  # Bottom right
BOX_H = "─"  # Horizontal
BOX_V = "│"  # Vertical
BOX_LT = "├"  # Left T
BOX_RT = "┤"  # Right T


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags from text to get visible content."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def _visible_len(text: str) -> int:
    """Get the visible length of text (excluding Rich markup)."""
    return len(_strip_rich_markup(text))


def _fit_text(text: str, width: int) -> str:
    """Truncate and pad text to exact visible width, preserving Rich markup."""
    stripped = _strip_rich_markup(text)
    visible_len = len(stripped)

    if visible_len <= width:
        # Just need to pad - add spaces after the text
        return text + " " * (width - visible_len)
    else:
        # Need to truncate - strip markup and truncate for safety
        return stripped[:width]


def _get_terminal_size() -> tuple[int, int]:
    """Get terminal width and height."""
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24


def _render_small_box(text: str, width: int = 5, highlight: bool = True) -> list[str]:
    """Render a small rounded box with text centered."""
    inner = text.center(width - 2)
    style = "bold yellow" if highlight else "dim"
    return [
        f"[{style}]{BOX_TL}{BOX_H * (width - 2)}{BOX_TR}[/{style}]",
        f"[{style}]{BOX_V}{inner}{BOX_V}[/{style}]",
        f"[{style}]{BOX_BL}{BOX_H * (width - 2)}{BOX_BR}[/{style}]",
    ]


def _render_option_box(text: str, width: int, highlighted: bool = False) -> list[str]:
    """Render an option inside a rounded box."""
    inner_width = width - 6
    # Use _fit_text to handle Rich markup correctly
    display_text = _fit_text(text, inner_width)

    if highlighted:
        start = "[bold cyan]"
        end = "[/bold cyan]"
    else:
        start = ""
        end = ""

    return [
        f"  {start}{BOX_TL}{BOX_H * (width - 4)}{BOX_TR}{end}  ",
        f"  {start}{BOX_V} {display_text} {BOX_V}{end}  ",
        f"  {start}{BOX_BL}{BOX_H * (width - 4)}{BOX_BR}{end}  ",
    ]


def _render_empty_option_slot(width: int) -> list[str]:
    """Render empty space for an option slot."""
    # Match the visual width of _render_option_box (width + 2 for padding alignment)
    slot_width = width + 2
    return [
        " " * slot_width,
        " " * slot_width,
        " " * slot_width,
    ]


def _render_menu_box(
    title: str,
    options: list[str],
    scroll_offset: int,
    show_back: bool,
    show_home: bool,
    box_width: int = 54,
) -> None:
    """Render the menu box with controls."""
    clear_screen()

    term_width, term_height = _get_terminal_size()

    # Calculate dimensions
    btn_width = 5
    total_width = btn_width + 2 + box_width + 2 + btn_width

    left_margin = max(0, (term_width - total_width) // 2)
    # Height: title(3) + separator(1) + options(3*3) + padding(2) + bottom(1) = ~16 lines
    top_margin = max(0, (term_height - 20) // 2)

    prefix = " " * left_margin
    btn_spacer = " " * btn_width

    # Print top margin
    console.print("\n" * top_margin, end="")

    # Prepare visible options
    total_options = len(options)
    visible_opts = options[scroll_offset : scroll_offset + VISIBLE_OPTIONS]
    while len(visible_opts) < VISIBLE_OPTIONS:
        visible_opts.append(None)  # type: ignore

    can_scroll_up = scroll_offset > 0
    can_scroll_down = scroll_offset + VISIBLE_OPTIONS < total_options

    # === Main box top border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_TL}{BOX_H * (box_width - 2)}{BOX_TR}")

    # === Title row ===
    title_text = title[: box_width - 4].center(box_width - 2)
    console.print(
        f"{prefix}{btn_spacer}  {BOX_V}[bold cyan]{title_text}[/bold cyan]{BOX_V}"
    )

    # === Separator ===
    console.print(f"{prefix}{btn_spacer}  {BOX_LT}{BOX_H * (box_width - 2)}{BOX_RT}")

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Option rows with side controls ===
    for i, opt in enumerate(visible_opts):
        # Prepare the option box (3 lines)
        if opt is not None:
            opt_box = _render_option_box(
                f"{scroll_offset + i + 1}. {opt}", box_width - 4
            )
            left_btn = _render_small_box(str(i + 1), btn_width, highlight=True)
        else:
            opt_box = _render_empty_option_slot(box_width - 4)
            left_btn = [" " * btn_width] * 3

        # Right side buttons (u for first row, d for third row)
        if i == 0:
            right_btn = _render_small_box("u", btn_width, highlight=can_scroll_up)
        elif i == 2:
            right_btn = _render_small_box("d", btn_width, highlight=can_scroll_down)
        else:
            right_btn = [" " * btn_width] * 3

        # Print all 3 lines for this option
        for line_idx in range(3):
            console.print(
                f"{prefix}{left_btn[line_idx]}  "
                f"{BOX_V}{opt_box[line_idx]}{BOX_V}  "
                f"{right_btn[line_idx]}"
            )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Navigation buttons ===
    if show_back:
        back_btn = _render_small_box("b", 8, highlight=True)
    else:
        back_btn = [" " * 8] * 3

    if show_home:
        home_btn = _render_small_box("h", 8, highlight=True)
    else:
        home_btn = [" " * 8] * 3

    nav_spacing = box_width - 8
    for line_idx in range(3):
        console.print(
            f"{prefix}{back_btn[line_idx]}{' ' * nav_spacing}{home_btn[line_idx]}"
        )

    # === Scroll indicator ===
    if total_options > VISIBLE_OPTIONS:
        indicator = f"[dim]({scroll_offset + 1}-{min(scroll_offset + VISIBLE_OPTIONS, total_options)} of {total_options})[/dim]"
        indicator_padding = " " * ((total_width - 20) // 2)
        console.print(f"{prefix}{indicator_padding}{indicator}")

    console.print()


def prompt_menu(
    title: str,
    options: list[str],
    show_back: bool = False,
    show_home: bool = False,
) -> int:
    """Display a menu and get user choice.

    Returns:
        Positive int (1-N) for option selection
        MENU_BACK (-1) if back selected
        MENU_HOME (-2) if home selected
        MENU_CANCEL (0) if cancelled (Ctrl+C)
    """
    scroll_offset = 0
    total_options = len(options)

    while True:
        _render_menu_box(title, options, scroll_offset, show_back, show_home)

        try:
            console.print("  [dim]Enter choice:[/dim] ", end="")
            response = input().strip().lower()

            if response == "b" and show_back:
                return MENU_BACK
            if response == "h" and show_home:
                return MENU_HOME

            if response == "u":
                if scroll_offset > 0:
                    scroll_offset -= 1
                continue
            if response == "d":
                if scroll_offset + VISIBLE_OPTIONS < total_options:
                    scroll_offset += 1
                continue

            if response in ("1", "2", "3"):
                visible_idx = int(response) - 1
                actual_idx = scroll_offset + visible_idx
                if actual_idx < total_options:
                    return actual_idx + 1
                continue

            try:
                choice = int(response)
                if 1 <= choice <= total_options:
                    return choice
            except ValueError:
                pass

        except KeyboardInterrupt:
            return MENU_CANCEL
        except EOFError:
            return MENU_CANCEL


def _render_loading_box(message: str, spinner_char: str, box_width: int = 54) -> None:
    """Render a centered loading box with spinner."""
    clear_screen()

    term_width, term_height = _get_terminal_size()
    left_margin = max(0, (term_width - box_width) // 2)
    top_margin = max(0, (term_height - 10) // 2)

    prefix = " " * left_margin
    inner_width = box_width - 4

    console.print("\n" * top_margin, end="")

    # Top border
    console.print(f"{prefix}{BOX_TL}{BOX_H * (box_width - 2)}{BOX_TR}")

    # Empty row
    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Message row (centered)
    msg_text = message[: inner_width - 2].center(inner_width)
    console.print(f"{prefix}{BOX_V} [cyan]{msg_text}[/cyan] {BOX_V}")

    # Empty row
    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Spinner row (centered)
    spinner_text = spinner_char.center(inner_width)
    console.print(f"{prefix}{BOX_V} [bold yellow]{spinner_text}[/bold yellow] {BOX_V}")

    # Empty row
    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Bottom border
    console.print(f"{prefix}{BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")


class LoadingSpinner:
    """A loading spinner context manager that displays in a centered box."""

    SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str) -> None:
        self.message = message
        self._task: asyncio.Task | None = None
        self._running = False

    async def _animate(self) -> None:
        """Animate the spinner."""
        idx = 0
        while self._running:
            _render_loading_box(self.message, self.SPINNER_CHARS[idx])
            idx = (idx + 1) % len(self.SPINNER_CHARS)
            await asyncio.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation."""
        self._running = True
        self._task = asyncio.create_task(self._animate())

    async def stop(self) -> None:
        """Stop the spinner animation."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class SpinnerContext:
    """Synchronous context manager for spinner (renders once)."""

    def __init__(self, message: str) -> None:
        self.message = message
        self._task_desc = message

    def __enter__(self) -> "SpinnerContext":
        _render_loading_box(self.message, "⠋")
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def add_task(self, description: str) -> None:
        """Update the task description (compatibility method)."""
        self._task_desc = description
        _render_loading_box(description, "⠋")


def spinner(message: str) -> SpinnerContext:
    """Return a spinner context manager for loading screens."""
    return SpinnerContext(message)


def print_header(title: str) -> None:
    """Print a styled header (clears screen)."""
    clear_screen()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  [green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  [yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"  [cyan]→[/cyan] {message}")


def print_coordinators_table(coordinators: list[DetectedCoordinator]) -> None:
    """Display coordinators in a table."""
    table = Table(title="Detected Coordinators", box=None)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Port", style="green")
    table.add_column("Type", style="yellow")

    for idx, coord in enumerate(coordinators, 1):
        table.add_row(str(idx), coord.port, coord.radio_type.pretty_name)

    console.print()
    console.print(table)
    console.print()


def print_devices_table(devices: list[dict[str, Any]]) -> None:
    """Display devices in a table."""
    table = Table(title="Paired Devices", box=None)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Model", style="yellow")
    table.add_column("Status", style="blue")

    for idx, device in enumerate(devices, 1):
        name = device["name"] or device["model"] or str(device["ieee"])
        status = "[green]●[/green]" if device["available"] else "[red]●[/red]"
        table.add_row(str(idx), name, device["model"] or "-", status)

    console.print()
    console.print(table)
    console.print()


def print_entities_table(entities: list[dict[str, Any]]) -> None:
    """Display entities in a table."""
    table = Table(title="Controllable Entities", box=None)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("State", style="yellow")

    for idx, entity in enumerate(entities, 1):
        state_str = _format_entity_state(entity)
        name = entity.get("fallback_name") or entity.get("unique_id", "Unknown")
        table.add_row(str(idx), name, state_str)

    console.print()
    console.print(table)
    console.print()


def _format_entity_state(entity: dict[str, Any]) -> str:
    """Format entity state for display."""
    state = entity.get("state", {})
    if "state" in state:
        return "[green]ON[/green]" if state["state"] else "[red]OFF[/red]"
    if "on" in state:
        return "[green]ON[/green]" if state["on"] else "[red]OFF[/red]"
    return "[dim]Unknown[/dim]"


def prompt_confirm(message: str, default: bool = True) -> bool:
    """Prompt for confirmation in a centered box."""
    box_width = 54
    term_width, term_height = _get_terminal_size()
    left_margin = max(0, (term_width - box_width) // 2)
    top_margin = max(0, (term_height - 10) // 2)

    clear_screen()
    prefix = " " * left_margin
    inner_width = box_width - 4

    console.print("\n" * top_margin, end="")
    console.print(f"{prefix}{BOX_TL}{BOX_H * (box_width - 2)}{BOX_TR}")
    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Message (word wrap)
    words = message.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= inner_width - 2:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines[:2]:
        console.print(f"{prefix}{BOX_V} {line.center(inner_width)} {BOX_V}")

    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Y/N buttons
    yes_btn = _render_small_box("y", 5, highlight=default)
    no_btn = _render_small_box("n", 5, highlight=not default)
    btn_spacing = inner_width - 16

    for i in range(3):
        console.print(
            f"{prefix}{BOX_V}   {yes_btn[i]}{' ' * btn_spacing}{no_btn[i]}   {BOX_V}"
        )

    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")
    console.print(f"{prefix}{BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")
    console.print()

    try:
        console.print(f"{prefix}  [dim]Enter choice (y/n):[/dim] ", end="")
        response = input().strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def prompt_int(message: str, default: int | None = None) -> int:
    """Prompt for an integer."""
    default_str = f" [{default}]" if default is not None else ""
    console.print(f"  {message}{default_str}: ", end="")

    try:
        response = input().strip()
        if not response and default is not None:
            return default
        return int(response)
    except (ValueError, KeyboardInterrupt, EOFError):
        return default if default is not None else 0


def prompt_str(message: str, default: str | None = None) -> str:
    """Prompt for a string."""
    default_str = f" [{default}]" if default else ""
    console.print(f"  {message}{default_str}: ", end="")

    try:
        response = input().strip()
        return response if response else (default or "")
    except (KeyboardInterrupt, EOFError):
        return default or ""


def show_message(title: str, message: str, wait: bool = True) -> None:
    """Show a message in a centered box."""
    box_width = 54
    term_width, term_height = _get_terminal_size()
    left_margin = max(0, (term_width - box_width) // 2)
    top_margin = max(0, (term_height - 10) // 2)

    clear_screen()
    prefix = " " * left_margin
    inner_width = box_width - 4

    console.print("\n" * top_margin, end="")
    console.print(f"{prefix}{BOX_TL}{BOX_H * (box_width - 2)}{BOX_TR}")

    # Title
    title_text = title[: inner_width - 2].center(inner_width)
    console.print(f"{prefix}{BOX_V} [bold cyan]{title_text}[/bold cyan] {BOX_V}")

    console.print(f"{prefix}{BOX_LT}{BOX_H * (box_width - 2)}{BOX_RT}")
    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # Word wrap message
    words = message.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= inner_width - 2:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines[:3]:
        console.print(f"{prefix}{BOX_V} {line.ljust(inner_width)} {BOX_V}")

    # Pad remaining lines
    for _ in range(3 - len(lines[:3])):
        console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    console.print(f"{prefix}{BOX_V}{' ' * (box_width - 2)}{BOX_V}")
    console.print(f"{prefix}{BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    if wait:
        console.print()
        console.print(f"{prefix}  [dim]Press Enter to continue...[/dim]")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
