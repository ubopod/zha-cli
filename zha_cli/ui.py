"""Terminal GUI using rich."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
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


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def _get_terminal_size() -> tuple[int, int]:
    """Get terminal width and height."""
    size = os.get_terminal_size()
    return size.columns, size.lines


def _render_menu_box(
    title: str,
    options: list[str],
    scroll_offset: int,
    show_back: bool,
    show_home: bool,
    box_width: int = 50,
) -> None:
    """Render the menu box with controls."""
    clear_screen()

    term_width, term_height = _get_terminal_size()

    # Calculate centering
    left_margin = max(0, (term_width - box_width - 12) // 2)  # 12 for side controls
    top_margin = max(0, (term_height - 12) // 2)  # 12 for box height approx

    # Print top margin
    console.print("\n" * top_margin, end="")

    # Prepare visible options (max 3)
    total_options = len(options)
    visible_opts = options[scroll_offset : scroll_offset + VISIBLE_OPTIONS]

    # Pad to always show 3 slots
    while len(visible_opts) < VISIBLE_OPTIONS:
        visible_opts.append("")

    can_scroll_up = scroll_offset > 0
    can_scroll_down = scroll_offset + VISIBLE_OPTIONS < total_options

    # Build the box content
    inner_width = box_width - 4  # Account for borders and padding

    # Top border
    prefix = " " * left_margin
    console.print(f"{prefix}      ┌{'─' * (box_width - 2)}┐")

    # Title row
    title_text = title[:inner_width].center(inner_width)
    console.print(f"{prefix}      │ [bold cyan]{title_text}[/bold cyan] │")

    # Separator
    console.print(f"{prefix}      ├{'─' * (box_width - 2)}┤")

    # Option rows with side controls
    for i, opt in enumerate(visible_opts):
        opt_num = scroll_offset + i + 1
        left_ctrl = f"[bold yellow][{i + 1}][/bold yellow]" if opt else "   "

        if i == 0:
            right_ctrl = (
                "[bold cyan][u][/bold cyan]" if can_scroll_up else "[dim][u][/dim]"
            )
        elif i == 2:
            right_ctrl = (
                "[bold cyan][d][/bold cyan]" if can_scroll_down else "[dim][d][/dim]"
            )
        else:
            right_ctrl = "   "

        if opt:
            # Format option text
            opt_display = f"{opt_num}. {opt}"
            if len(opt_display) > inner_width:
                opt_display = opt_display[: inner_width - 3] + "..."
            opt_display = opt_display.ljust(inner_width)
        else:
            opt_display = " " * inner_width

        console.print(f"{prefix} {left_ctrl}  │ {opt_display} │  {right_ctrl}")

    # Bottom border
    console.print(f"{prefix}      └{'─' * (box_width - 2)}┘")

    # Navigation row
    back_text = "[bold yellow][b][/bold yellow] Back" if show_back else "      "
    home_text = "[bold yellow][h][/bold yellow] Home" if show_home else "      "

    nav_spacing = box_width - 12  # Space between back and home
    console.print(f"{prefix} {back_text}{' ' * nav_spacing}{home_text}")

    # Scroll indicator
    if total_options > VISIBLE_OPTIONS:
        indicator = f"[dim]({scroll_offset + 1}-{min(scroll_offset + VISIBLE_OPTIONS, total_options)} of {total_options})[/dim]"
        console.print(f"{prefix}      {indicator}")

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

            # Navigation shortcuts
            if response == "b" and show_back:
                return MENU_BACK
            if response == "h" and show_home:
                return MENU_HOME

            # Scroll controls
            if response == "u":
                if scroll_offset > 0:
                    scroll_offset -= 1
                continue
            if response == "d":
                if scroll_offset + VISIBLE_OPTIONS < total_options:
                    scroll_offset += 1
                continue

            # Number selection (1, 2, 3 for visible options)
            if response in ("1", "2", "3"):
                visible_idx = int(response) - 1
                actual_idx = scroll_offset + visible_idx
                if actual_idx < total_options:
                    return actual_idx + 1  # Return 1-indexed
                continue

            # Direct number input for any option
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


def spinner(message: str) -> Progress:
    """Return a spinner context manager for loading screens."""
    clear_screen()
    return Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        console=console,
        transient=True,
    )


def print_header(title: str) -> None:
    """Print a styled header."""
    clear_screen()
    console.print()
    console.print(Panel(title, style="bold blue"))


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
        table.add_row(
            str(idx),
            coord.port,
            coord.radio_type.pretty_name,
        )

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
        table.add_row(
            str(idx),
            name,
            device["model"] or "-",
            status,
        )

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
    """Prompt for confirmation."""
    clear_screen()
    default_str = "Y/n" if default else "y/N"
    console.print()
    console.print(f"  {message} [{default_str}]: ", end="")

    try:
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
    """Show a message in a box."""
    clear_screen()

    term_width, term_height = _get_terminal_size()
    box_width = 50
    left_margin = max(0, (term_width - box_width) // 2)
    top_margin = max(0, (term_height - 8) // 2)

    prefix = " " * left_margin

    console.print("\n" * top_margin, end="")
    console.print(f"{prefix}┌{'─' * (box_width - 2)}┐")

    inner_width = box_width - 4
    title_text = title[:inner_width].center(inner_width)
    console.print(f"{prefix}│ [bold cyan]{title_text}[/bold cyan] │")

    console.print(f"{prefix}├{'─' * (box_width - 2)}┤")

    # Word wrap message
    words = message.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 <= inner_width:
            current_line = f"{current_line} {word}".strip()
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    for line in lines[:3]:  # Max 3 lines
        console.print(f"{prefix}│ {line.ljust(inner_width)} │")

    console.print(f"{prefix}└{'─' * (box_width - 2)}┘")

    if wait:
        console.print(f"{prefix}  [dim]Press Enter to continue...[/dim]")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
