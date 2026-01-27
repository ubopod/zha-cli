"""Main entry point for the ZHA CLI tool."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Any

from zha_cli import ui
from zha_cli.coordinator_probe import DetectedCoordinator, discover_coordinators
from zha_cli.device_control import DeviceController
from zha_cli.device_pairing import DevicePairingManager
from zha_cli.network_manager import NetworkManager
from zha_cli.ui import MENU_BACK, MENU_HOME

_LOGGER = logging.getLogger(__name__)


class ZHACli:
    """ZHA CLI application."""

    def __init__(self) -> None:
        """Initialize the CLI application."""
        self._network_manager = NetworkManager()
        self._pairing_manager: DevicePairingManager | None = None
        self._detected_coordinators: list[DetectedCoordinator] = []
        self._selected_coordinator: DetectedCoordinator | None = None
        self._running = True

    async def run(self) -> None:
        """Run the main CLI loop."""
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        ui.print_header("ZHA CLI - Zigbee Home Automation")

        # Run coordinator detection on entry
        await self._coordinator_entry_flow()

        try:
            while self._running:
                await self._main_menu()
        except KeyboardInterrupt:
            pass
        finally:
            await self._cleanup()

    async def _coordinator_entry_flow(self) -> None:
        """Handle coordinator detection and selection on entry."""
        previous_count = len(self._detected_coordinators)

        while self._running and not self._selected_coordinator:
            await self._detect_coordinators_with_spinner()

            if not self._detected_coordinators:
                # Check if this was a retry that found nothing new
                if previous_count == 0:
                    title = "No Coordinators Found"
                else:
                    title = "No New Coordinators Found"

                options = ["Retry detection"]
                choice = ui.prompt_menu(title, options, show_back=True, show_home=True)
                if choice in (0, MENU_BACK, MENU_HOME):
                    self._running = False
                    return
                # choice == 1 means retry, loop continues
                previous_count = 0
            else:
                result = await self._select_coordinator_menu()
                if result == "retry":
                    previous_count = len(self._detected_coordinators)
                    continue
                break

    async def _detect_coordinators_with_spinner(self) -> None:
        """Detect coordinators with a loading spinner."""
        with ui.spinner("Detecting coordinators...") as progress:
            progress.add_task("Scanning serial ports for Zigbee coordinators...")
            try:
                self._detected_coordinators = await discover_coordinators()
            except Exception as exc:
                ui.print_error(f"Error detecting coordinators: {exc}")
                self._detected_coordinators = []

    async def _select_coordinator_menu(self) -> str:
        """Display coordinator selection menu.

        Returns:
            "selected" if a coordinator was selected
            "retry" if retry detection was chosen
            "exit" if user wants to exit
        """
        ui.print_coordinators_table(self._detected_coordinators)

        if len(self._detected_coordinators) == 1:
            options = [
                f"Select {self._detected_coordinators[0].port}",
                "Retry detection",
            ]
            choice = ui.prompt_menu(
                "Coordinator Found", options, show_back=True, show_home=True
            )
            if choice in (0, MENU_BACK, MENU_HOME):
                self._running = False
                return "exit"
            elif choice == 1:
                self._selected_coordinator = self._detected_coordinators[0]
                await self._ensure_network_started()
                return "selected"
            else:
                return "retry"
        else:
            # Multiple coordinators found - list each one
            options = []
            for coord in self._detected_coordinators:
                options.append(f"Select {coord.port}")
            options.append("Retry detection")
            choice = ui.prompt_menu(
                "Coordinators Found", options, show_back=True, show_home=True
            )

            if choice in (0, MENU_BACK, MENU_HOME):
                self._running = False
                return "exit"
            elif 1 <= choice <= len(self._detected_coordinators):
                self._selected_coordinator = self._detected_coordinators[choice - 1]
                await self._ensure_network_started()
                return "selected"
            else:
                return "retry"

    async def _ensure_network_started(self) -> None:
        """Ensure the network is started, auto-starting if needed."""
        if self._network_manager.is_running:
            ui.print_success("Network is already running")
            devices = self._network_manager.get_devices()
            ui.print_info(f"Found {len(devices)} paired device(s)")
            return

        coordinator = self._selected_coordinator
        if coordinator is None:
            return

        ui.print_info(
            f"Starting network with {coordinator.radio_type.pretty_name} "
            f"at {coordinator.port}..."
        )

        with ui.spinner("Starting network...") as progress:
            progress.add_task("Initializing Zigbee network...")
            try:
                gateway = await self._network_manager.start_network(coordinator)
                self._pairing_manager = DevicePairingManager(gateway)
            except Exception as exc:
                ui.print_error(f"Failed to start network: {exc}")
                _LOGGER.exception("Network start failed")
                self._selected_coordinator = None
                return

        ui.print_success("Network started successfully!")
        devices = self._network_manager.get_devices()
        ui.print_info(f"Found {len(devices)} paired device(s)")

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        self._running = False

    async def _cleanup(self) -> None:
        """Clean up resources."""
        ui.print_info("Shutting down...")
        await self._network_manager.shutdown()
        ui.print_success("Goodbye!")

    async def _main_menu(self) -> None:
        """Display and handle the main menu (device management)."""
        # If network isn't running (e.g., after a reset), go back to coordinator flow
        if not self._network_manager.is_running:
            self._selected_coordinator = None
            await self._coordinator_entry_flow()
            return

        coordinator = self._selected_coordinator
        coord_info = f" - {coordinator.port}" if coordinator else ""

        devices = self._network_manager.get_devices()

        # Build menu options: devices first, then actions
        options: list[str] = []
        if devices:
            for device in devices:
                status = "[green]●[/green]" if device["available"] else "[red]●[/red]"
                name = device["name"] or device["model"] or str(device["ieee"])
                options.append(f"{status} {name}")

        # Add action options
        pair_idx = len(options)
        options.append("Pair new device")
        reset_idx = len(options)
        options.append("Reset network")

        title = f"Devices{coord_info}" if devices else f"No Devices{coord_info}"
        choice = ui.prompt_menu(title, options, show_back=True, show_home=True)

        if choice in (0, MENU_HOME):
            self._running = False
        elif choice == MENU_BACK:
            # Back goes to coordinator selection
            await self._network_manager.shutdown()
            self._selected_coordinator = None
            await self._coordinator_entry_flow()
        elif devices and choice <= len(devices):
            # Device selected
            await self._control_device_direct(devices[choice - 1])
        elif choice == pair_idx + 1:
            await self._pair_device()
        elif choice == reset_idx + 1:
            await self._reset_network()

    async def _reset_network(self) -> None:
        """Reset (shutdown) the network."""
        if not ui.prompt_confirm(
            "Are you sure you want to reset the network?", default=False
        ):
            return

        ui.print_info("Resetting network...")
        await self._network_manager.shutdown()
        self._pairing_manager = None
        ui.print_success("Network has been reset")

    async def _pair_device(self) -> None:
        """Enable pairing mode to add new devices."""
        options = ["Start pairing (30 seconds)", "Start pairing (60 seconds)"]
        choice = ui.prompt_menu(
            "Device Pairing", options, show_back=True, show_home=True
        )

        if choice in (0, MENU_BACK):
            return
        if choice == MENU_HOME:
            self._running = False
            return

        duration = 30 if choice == 1 else 60

        ui.print_info(f"Enabling pairing mode for {duration} seconds...")
        ui.print_info("Put your Zigbee device in pairing mode now")

        if self._pairing_manager is None:
            ui.print_error("Pairing manager not initialized")
            return

        pairing_manager = self._pairing_manager

        try:
            await pairing_manager.enable_pairing(duration)

            # Set up event handlers to show progress
            def on_joined(event: Any) -> None:
                ui.print_info(f"Device joined: {event.device_info.ieee}")

            def on_initialized(event: Any) -> None:
                ui.print_success(
                    f"Device initialized: {event.device_info.manufacturer} "
                    f"{event.device_info.model}"
                )

            unsubscribe = pairing_manager.subscribe_to_events(
                on_joined=on_joined,
                on_initialized=on_initialized,
            )

            ui.print_info("Waiting for devices... (Press Ctrl+C to stop early)")

            try:
                await asyncio.sleep(duration)
            except asyncio.CancelledError:
                pass
            finally:
                unsubscribe()
                await pairing_manager.disable_pairing()

            ui.print_success("Pairing mode ended")

        except Exception as exc:
            ui.print_error(f"Pairing error: {exc}")
            _LOGGER.exception("Pairing failed")

    async def _control_device_direct(self, device_info: dict[str, Any]) -> None:
        """Control a specific device."""
        device = device_info["device"]
        name = device_info["name"] or device_info["model"] or str(device_info["ieee"])

        while True:
            ui.print_header(f"Device: {name}")
            ui.print_info(f"Manufacturer: {device_info['manufacturer']}")
            ui.print_info(f"Model: {device_info['model']}")
            ui.print_info(f"IEEE: {device_info['ieee']}")

            # Get controllable entities
            entities = DeviceController.get_controllable_entities(device)

            if not entities:
                ui.print_warning("No controllable entities found for this device")
                ui.prompt_str("Press Enter to go back", default="")
                return

            # Show entities with control options
            entity_infos = [DeviceController.get_entity_info(e) for e in entities]
            ui.print_entities_table(entity_infos)

            # Build options: one per entity for toggle
            options: list[str] = []
            for i, entity in enumerate(entities):
                info = entity_infos[i]
                state = info.get("state", {})
                is_on = state.get("state") or state.get("on")
                status = "ON" if is_on else "OFF"
                entity_name = info.get("fallback_name") or info.get(
                    "unique_id", "Unknown"
                )
                options.append(f"Toggle {entity_name} ({status})")

            choice = ui.prompt_menu("Control", options, show_back=True, show_home=True)

            if choice in (0, MENU_BACK):
                return
            if choice == MENU_HOME:
                self._running = False
                return

            # Toggle the selected entity
            selected_entity = entities[choice - 1]
            try:
                await DeviceController.toggle(selected_entity)
                ui.print_success("Device toggled")
            except Exception as exc:
                ui.print_error(f"Control error: {exc}")
                _LOGGER.exception("Control failed")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.WARNING

    # Set up basic logging
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Reduce noise from libraries
    logging.getLogger("zigpy").setLevel(logging.WARNING)
    logging.getLogger("bellows").setLevel(logging.WARNING)
    logging.getLogger("zigpy_znp").setLevel(logging.WARNING)
    logging.getLogger("zigpy_deconz").setLevel(logging.WARNING)
    logging.getLogger("zigpy_xbee").setLevel(logging.WARNING)
    logging.getLogger("zigpy_zigate").setLevel(logging.WARNING)


def main() -> None:
    """Run the ZHA CLI application."""
    parser = argparse.ArgumentParser(
        description="ZHA CLI - Zigbee Home Automation management tool"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    cli = ZHACli()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(cli.run())

    sys.exit(0)


if __name__ == "__main__":
    main()
