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

# Track whether screen has been initialized (first render needs full clear)
_screen_initialized = False

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


def _move_cursor_home() -> None:
    """Move cursor to top-left without clearing screen."""
    print("\033[H", end="", flush=True)


def _ensure_screen_ready() -> None:
    """Clear screen on first render, reposition cursor after.

    This provides smooth transitions between screens by only clearing
    the screen once at startup, then using cursor repositioning for
    subsequent renders.
    """
    global _screen_initialized
    if not _screen_initialized:
        clear_screen()
        _screen_initialized = True
    else:
        _move_cursor_home()


def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags and escape sequences to get visible content.

    Handles:
    - Rich markup tags like [bold], [/bold], [cyan], etc.
    - Rich escape sequences like \\[ which display as literal [
    """
    # First remove markup tags like [bold], [/bold], [cyan], etc.
    stripped = re.sub(r"\[/?[^\]]*\]", "", text)
    # Then convert Rich escape sequences: \[ -> [ (backslash-bracket displays as bracket)
    stripped = stripped.replace("\\[", "[")
    return stripped


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
    """Render an option box that merges with the main box's left border.

    Uses T-junctions (├) on top/bottom to connect to the main box's left edge.
    The left │ of the content row IS the main box's left border.
    """
    # Box merges with main box left border, 4 spaces right padding
    right_padding = 4
    box_width = width - right_padding  # total box width including borders
    horiz_width = box_width - 2  # horizontal line width (minus junction and corner)
    text_width = horiz_width - 2  # text area (minus spaces around text)

    display_text = _fit_text(text, text_width)

    if highlighted:
        start = "[bold cyan]"
        end = "[/bold cyan]"
    else:
        start = ""
        end = ""

    # Left T-junction merges with main box, rounded corners on right
    return [
        f"{start}{BOX_LT}{BOX_H * horiz_width}{BOX_TR}{end}{' ' * right_padding}",
        f"{start}{BOX_V} {display_text} {BOX_V}{end}{' ' * right_padding}",
        f"{start}{BOX_LT}{BOX_H * horiz_width}{BOX_BR}{end}{' ' * right_padding}",
    ]


def _render_empty_option_slot(width: int) -> list[str]:
    """Render empty space for an option slot.

    Includes the main box's left border │ since option rows don't print it separately.
    """
    # Start with │ (main box left border), then spaces to fill width
    inner_width = width - 1  # minus the left border
    return [
        f"{BOX_V}{' ' * inner_width}",
        f"{BOX_V}{' ' * inner_width}",
        f"{BOX_V}{' ' * inner_width}",
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
    _ensure_screen_ready()

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
        # Width is box_width - 1 because we add the right │ separately
        if opt is not None:
            opt_box = _render_option_box(
                f"{scroll_offset + i + 1}. {opt}", box_width - 1
            )
        else:
            opt_box = _render_empty_option_slot(box_width - 1)

        # Left buttons always visible (1, 2, 3), highlighted if option exists
        left_btn = _render_small_box(str(i + 1), btn_width, highlight=(opt is not None))

        # Right side buttons always visible (u on row 0, d on row 2)
        if i == 0:
            right_btn = _render_small_box("u", btn_width, highlight=can_scroll_up)
        elif i == 2:
            right_btn = _render_small_box("d", btn_width, highlight=can_scroll_down)
        else:
            right_btn = [" " * btn_width] * 3

        # Print all 3 lines for this option
        # Option box includes left border (├/│) that merges with main box
        for line_idx in range(3):
            console.print(
                f"{prefix}{left_btn[line_idx]}  "
                f"{opt_box[line_idx]}{BOX_V}  "
                f"{right_btn[line_idx]}"
            )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Navigation buttons (always visible, highlighted when active) ===
    back_btn = _render_small_box("b", 8, highlight=show_back)
    home_btn = _render_small_box("h", 8, highlight=show_home)

    # Center buttons under the main box, on either side of vertical center
    box_start = btn_width + 2  # Main box starts after left button area + gap
    box_center = box_start + box_width // 2
    nav_btn_width = 8
    btn_gap = 4  # Gap between the two buttons at center
    nav_start = box_center - nav_btn_width - btn_gap // 2

    for line_idx in range(3):
        console.print(
            f"{prefix}{' ' * nav_start}{back_btn[line_idx]}{' ' * btn_gap}{home_btn[line_idx]}"
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


def _render_loading_box(
    message: str,
    spinner_char: str,
    status: str | None = None,
    box_width: int = 54,
) -> None:
    """Render a loading box matching menu dimensions with placeholder buttons."""
    _ensure_screen_ready()

    term_width, term_height = _get_terminal_size()

    # Match menu dimensions exactly
    btn_width = 5
    total_width = btn_width + 2 + box_width + 2 + btn_width

    left_margin = max(0, (term_width - total_width) // 2)
    top_margin = max(0, (term_height - 20) // 2)

    prefix = " " * left_margin
    btn_spacer = " " * btn_width

    console.print("\n" * top_margin, end="")

    # === Main box top border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_TL}{BOX_H * (box_width - 2)}{BOX_TR}")

    # === Title row ===
    title_text = message[: box_width - 4].center(box_width - 2)
    console.print(
        f"{prefix}{btn_spacer}  {BOX_V}[bold cyan]{title_text}[/bold cyan]{BOX_V}"
    )

    # === Separator ===
    console.print(f"{prefix}{btn_spacer}  {BOX_LT}{BOX_H * (box_width - 2)}{BOX_RT}")

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Content area with centered spinner and status ===
    # 9 lines total for the 3 option slot area
    inner_width = box_width - 2
    # Prepare status text (truncate if needed)
    status_text = ""
    if status:
        status_text = status[: inner_width - 4].center(inner_width)

    for line_num in range(9):
        # Dimmed side buttons
        slot_idx = line_num // 3
        left_btn = _render_small_box(str(slot_idx + 1), btn_width, highlight=False)

        if slot_idx == 0:
            right_btn = _render_small_box("u", btn_width, highlight=False)
        elif slot_idx == 2:
            right_btn = _render_small_box("d", btn_width, highlight=False)
        else:
            right_btn = [" " * btn_width] * 3

        btn_line = line_num % 3

        # Line 3 (first line of middle slot) shows spinner
        if line_num == 3:
            padding = (inner_width - 1) // 2
            content = f"{' ' * padding}[bold yellow]{spinner_char}[/bold yellow]{' ' * (inner_width - padding - 1)}"
        # Line 5 (last line of middle slot) shows status
        elif line_num == 5 and status:
            content = f"[dim]{status_text}[/dim]"
        else:
            content = " " * inner_width

        console.print(
            f"{prefix}{left_btn[btn_line]}  "
            f"{BOX_V}{content}{BOX_V}  "
            f"{right_btn[btn_line]}"
        )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Dimmed navigation buttons ===
    back_btn = _render_small_box("b", 8, highlight=False)
    home_btn = _render_small_box("h", 8, highlight=False)

    box_start = btn_width + 2
    box_center = box_start + box_width // 2
    nav_btn_width = 8
    btn_gap = 4
    nav_start = box_center - nav_btn_width - btn_gap // 2

    for line_idx in range(3):
        console.print(
            f"{prefix}{' ' * nav_start}{back_btn[line_idx]}{' ' * btn_gap}{home_btn[line_idx]}"
        )


class LoadingSpinner:
    """Async context manager for animated loading spinner."""

    SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str, status: str | None = None) -> None:
        self.message = message
        self.status = status
        self._task: asyncio.Task | None = None
        self._running = False

    async def _animate(self) -> None:
        """Animate the spinner."""
        idx = 0
        while self._running:
            _render_loading_box(
                self.message,
                self.SPINNER_CHARS[idx],
                self.status,
            )
            idx = (idx + 1) % len(self.SPINNER_CHARS)
            await asyncio.sleep(0.1)

    async def __aenter__(self) -> "LoadingSpinner":
        """Start the spinner animation."""
        self._running = True
        self._task = asyncio.create_task(self._animate())
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Stop the spinner animation."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def update_message(self, message: str) -> None:
        """Update the spinner message (title)."""
        self.message = message

    def set_status(self, status: str | None) -> None:
        """Update the status text shown below the spinner."""
        self.status = status


def spinner(message: str, status: str | None = None) -> LoadingSpinner:
    """Return an async spinner context manager for loading screens."""
    return LoadingSpinner(message, status)


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
        name = entity.get("display_name", "Unknown")
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


def format_coordinator_option(port: str, status: str) -> str:
    """Format coordinator for menu display.

    Args:
        port: The serial port path.
        status: "connected", "saved", or "new".
    """
    if status == "connected":
        return f"[green]●[/green] {port} (connected)"
    elif status == "saved":
        return f"[yellow]●[/yellow] {port} (saved network)"
    else:
        return f"[dim]○[/dim] {port} (new)"


def format_device_option(name: str, available: bool) -> str:
    """Format device for menu display."""
    status = "[green]●[/green]" if available else "[red]●[/red]"
    return f"{status} {name}"


def format_entity_option(name: str | None, is_on: bool | None) -> str:
    """Format entity control option for menu display.

    Shows action-oriented text like "Turn off" or "Turn on".
    If name is provided (for multi-entity devices), includes the entity name.
    """
    if is_on is None:
        action = "Toggle"
        style = "dim"
    elif is_on:
        action = "Turn off"
        style = "green"
    else:
        action = "Turn on"
        style = "red"

    if name:
        return f"[{style}]{action}[/{style}] {name}"
    return f"[{style}]{action}[/{style}]"


def format_sensor_option(name: str, value: str) -> str:
    """Format sensor for menu display.

    Shows the sensor name and its current value.
    """
    return f"{name}: [cyan]{value}[/cyan]"


def prompt_confirm(message: str, default: bool = True, title: str = "Confirm") -> bool:
    """Prompt for confirmation using the standard menu layout."""
    box_width = 54
    btn_width = 5

    term_width, term_height = _get_terminal_size()
    total_width = btn_width + 2 + box_width + 2 + btn_width
    left_margin = max(0, (term_width - total_width) // 2)
    top_margin = max(0, (term_height - 20) // 2)

    _ensure_screen_ready()
    prefix = " " * left_margin
    btn_spacer = " " * btn_width
    inner_width = box_width - 2

    console.print("\n" * top_margin, end="")

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
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * inner_width}{BOX_V}")

    # Word wrap message
    text_width = inner_width - 4
    words = message.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= text_width:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    # === Content area: message text + Yes option ===
    for line_num in range(9):
        slot_idx = line_num // 3
        btn_line = line_num % 3

        # Side buttons (dimmed except slot 1 which has Yes)
        left_btn = _render_small_box(
            str(slot_idx + 1), btn_width, highlight=(slot_idx == 0)
        )

        if slot_idx == 0:
            right_btn = _render_small_box("u", btn_width, highlight=False)
        elif slot_idx == 2:
            right_btn = _render_small_box("d", btn_width, highlight=False)
        else:
            right_btn = [" " * btn_width] * 3

        if slot_idx == 0:
            # First slot: Yes option
            if btn_line == 0:
                opt_box = _render_option_box("1. Yes - Confirm", box_width - 1)
            console.print(
                f"{prefix}{left_btn[btn_line]}  "
                f"{opt_box[btn_line]}{BOX_V}  "
                f"{right_btn[btn_line]}"
            )
        elif slot_idx == 1:
            # Second slot: message text (centered)
            msg_line = lines[btn_line] if btn_line < len(lines) else ""
            content = msg_line.center(inner_width)
            console.print(
                f"{prefix}{left_btn[btn_line]}  "
                f"{BOX_V}{content}{BOX_V}  "
                f"{right_btn[btn_line]}"
            )
        else:
            # Third slot: cancel hint
            if btn_line == 1:
                hint = "[dim]Press b to cancel[/dim]".center(
                    inner_width + 13
                )  # +13 for markup
                content = hint
            else:
                content = " " * inner_width
            console.print(
                f"{prefix}{left_btn[btn_line]}  "
                f"{BOX_V}{content}{BOX_V}  "
                f"{right_btn[btn_line]}"
            )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * inner_width}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Navigation buttons (back highlighted for cancel) ===
    back_btn = _render_small_box("b", 8, highlight=True)
    home_btn = _render_small_box("h", 8, highlight=False)

    box_start = btn_width + 2
    box_center = box_start + box_width // 2
    nav_btn_width = 8
    btn_gap = 4
    nav_start = box_center - nav_btn_width - btn_gap // 2

    for line_idx in range(3):
        console.print(
            f"{prefix}{' ' * nav_start}{back_btn[line_idx]}{' ' * btn_gap}{home_btn[line_idx]}"
        )

    console.print()

    try:
        console.print("  [dim]Enter choice:[/dim] ", end="")
        response = input().strip().lower()
        if response in ("1", "y", "yes"):
            return True
        if response in ("b", "n", "no"):
            return False
        return default
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


def prompt_device_name(
    title: str, manufacturer: str | None, model: str | None, default: str | None = None
) -> str | None:
    """Prompt for a device name using the standard menu layout.

    Args:
        title: The title for the dialog.
        manufacturer: Device manufacturer.
        model: Device model.
        default: Default name suggestion.

    Returns:
        The entered name, or None if cancelled.
    """
    box_width = 54
    btn_width = 5

    term_width, term_height = _get_terminal_size()
    total_width = btn_width + 2 + box_width + 2 + btn_width
    left_margin = max(0, (term_width - total_width) // 2)
    top_margin = max(0, (term_height - 20) // 2)

    _ensure_screen_ready()
    prefix = " " * left_margin
    btn_spacer = " " * btn_width

    console.print("\n" * top_margin, end="")

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

    # Build info lines for display
    info_lines: list[str] = []
    if manufacturer:
        info_lines.append(f"Manufacturer: {manufacturer}")
    if model:
        info_lines.append(f"Model: {model}")
    if default:
        info_lines.append(f"Default: {default}")

    inner_width = box_width - 2

    # === Content area with plain text (no item borders) ===
    for line_num in range(9):
        slot_idx = line_num // 3
        btn_line = line_num % 3

        # Dimmed side buttons
        left_btn = _render_small_box(str(slot_idx + 1), btn_width, highlight=False)

        if slot_idx == 0:
            right_btn = _render_small_box("u", btn_width, highlight=False)
        elif slot_idx == 2:
            right_btn = _render_small_box("d", btn_width, highlight=False)
        else:
            right_btn = [" " * btn_width] * 3

        # Info text centered in the middle area
        if line_num < len(info_lines):
            content = info_lines[line_num].center(inner_width)
        else:
            content = " " * inner_width

        console.print(
            f"{prefix}{left_btn[btn_line]}  "
            f"{BOX_V}{content}{BOX_V}  "
            f"{right_btn[btn_line]}"
        )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * (box_width - 2)}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Navigation buttons (dimmed) ===
    back_btn = _render_small_box("b", 8, highlight=False)
    home_btn = _render_small_box("h", 8, highlight=False)

    box_start = btn_width + 2
    box_center = box_start + box_width // 2
    nav_btn_width = 8
    btn_gap = 4
    nav_start = box_center - nav_btn_width - btn_gap // 2

    for line_idx in range(3):
        console.print(
            f"{prefix}{' ' * nav_start}{back_btn[line_idx]}{' ' * btn_gap}{home_btn[line_idx]}"
        )

    console.print()

    try:
        console.print("  [dim]Enter name (or press Enter for default):[/dim] ", end="")
        response = input().strip()
        if response:
            return response
        return default
    except (KeyboardInterrupt, EOFError):
        return default


def show_message(title: str, message: str, wait: bool = True) -> None:
    """Show a message using the standard menu layout with plain text content."""
    box_width = 54
    btn_width = 5

    term_width, term_height = _get_terminal_size()
    total_width = btn_width + 2 + box_width + 2 + btn_width
    left_margin = max(0, (term_width - total_width) // 2)
    top_margin = max(0, (term_height - 20) // 2)

    _ensure_screen_ready()
    prefix = " " * left_margin
    btn_spacer = " " * btn_width
    inner_width = box_width - 2

    console.print("\n" * top_margin, end="")

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
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * inner_width}{BOX_V}")

    # Word wrap message
    text_width = inner_width - 4
    words = message.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= text_width:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    # === Content area with plain text (no item borders) ===
    for line_num in range(9):
        slot_idx = line_num // 3
        btn_line = line_num % 3

        # Dimmed side buttons
        left_btn = _render_small_box(str(slot_idx + 1), btn_width, highlight=False)

        if slot_idx == 0:
            right_btn = _render_small_box("u", btn_width, highlight=False)
        elif slot_idx == 2:
            right_btn = _render_small_box("d", btn_width, highlight=False)
        else:
            right_btn = [" " * btn_width] * 3

        # Message text centered in the middle area
        if line_num < len(lines):
            content = lines[line_num].center(inner_width)
        else:
            content = " " * inner_width

        console.print(
            f"{prefix}{left_btn[btn_line]}  "
            f"{BOX_V}{content}{BOX_V}  "
            f"{right_btn[btn_line]}"
        )

    # === Empty row for spacing ===
    console.print(f"{prefix}{btn_spacer}  {BOX_V}{' ' * inner_width}{BOX_V}")

    # === Main box bottom border ===
    console.print(f"{prefix}{btn_spacer}  {BOX_BL}{BOX_H * (box_width - 2)}{BOX_BR}")

    # === Navigation buttons (dimmed) ===
    back_btn = _render_small_box("b", 8, highlight=False)
    home_btn = _render_small_box("h", 8, highlight=False)

    box_start = btn_width + 2
    box_center = box_start + box_width // 2
    nav_btn_width = 8
    btn_gap = 4
    nav_start = box_center - nav_btn_width - btn_gap // 2

    for line_idx in range(3):
        console.print(
            f"{prefix}{' ' * nav_start}{back_btn[line_idx]}{' ' * btn_gap}{home_btn[line_idx]}"
        )

    if wait:
        console.print()
        console.print("  [dim]Press Enter to continue...[/dim]")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
