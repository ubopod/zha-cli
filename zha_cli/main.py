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
        self._running = True

    async def run(self) -> None:
        """Run the main CLI loop."""
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

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
        auto_restored = False
        selection_complete = False

        while self._running and not selection_complete:
            # Only run detection if we don't already have coordinators
            # (e.g., skip when navigating back from device menu)
            if not self._detected_coordinators:
                await self._detect_coordinators_with_spinner()

            if not self._detected_coordinators:
                title = "◆ No Coordinators Found"
                options = ["Retry detection", "Settings"]
                choice = ui.prompt_menu(title, options, show_back=True, show_home=True)
                if choice in (0, MENU_BACK, MENU_HOME):
                    self._running = False
                    return
                elif choice == 2:
                    await self._settings_menu()
                # choice == 1 means retry, loop continues
            else:
                # Auto-restore network if exactly one coordinator has existing network
                if not auto_restored:
                    coords_with_network = [
                        c
                        for c in self._detected_coordinators
                        if self._network_manager.has_existing_network(c)
                    ]
                    if len(coords_with_network) == 1:
                        coord = coords_with_network[0]
                        # Skip if already running on this coordinator
                        current = self._network_manager.coordinator
                        if not (
                            current is not None
                            and current.port == coord.port
                            and self._network_manager.is_running
                        ):
                            await self._auto_restore_network(coord)
                        auto_restored = True

                result = await self._select_coordinator_menu()
                if result == "retry":
                    # Clear coordinators to trigger re-detection
                    self._detected_coordinators = []
                    continue
                elif result == "settings":
                    continue
                selection_complete = True

    async def _auto_restore_network(self, coordinator: DetectedCoordinator) -> None:
        """Auto-restore a network without selecting it for UI navigation."""
        async with ui.spinner("◆ Zigbee") as spin:
            try:
                gateway = await self._network_manager.start_network(coordinator)
                self._pairing_manager = DevicePairingManager(gateway)
                devices = self._network_manager.get_devices()
                spin.set_status(f"Restored! {len(devices)} device(s)")
                await asyncio.sleep(0.5)  # Brief pause to show status
            except Exception as exc:
                _LOGGER.exception("Network restore failed")
                ui.show_message("Error", f"Failed to restore network: {exc}")

    async def _detect_coordinators_with_spinner(self) -> None:
        """Detect coordinators with a loading spinner.

        Preserves the currently connected coordinator since its port
        cannot be probed while the network is running.
        """
        # Remember the currently connected coordinator (its port is locked)
        current_coord = self._network_manager.coordinator

        error_msg = None
        async with ui.spinner("◆ Zigbee"):
            try:
                detected = await discover_coordinators()
            except Exception as exc:
                _LOGGER.exception("Error detecting coordinators")
                error_msg = str(exc)
                detected = []

        if error_msg:
            ui.show_message("Error", f"Detection failed: {error_msg}")

        # If we have a connected coordinator, ensure it's in the list
        if current_coord is not None and self._network_manager.is_running:
            # Check if the current coordinator was detected
            current_in_list = any(c.port == current_coord.port for c in detected)
            if not current_in_list:
                # Prepend the connected coordinator so it appears first
                detected.insert(0, current_coord)

        self._detected_coordinators = detected

    async def _select_coordinator_menu(self) -> str:
        """Display coordinator selection menu.

        Returns:
            "selected" if a coordinator was selected
            "retry" if retry detection was chosen
            "exit" if user wants to exit
        """
        # Check which coordinator is currently connected (if any)
        current_coord = self._network_manager.coordinator

        # Build options with network status indicators
        options = []
        for coord in self._detected_coordinators:
            is_connected = (
                current_coord is not None and coord.port == current_coord.port
            )
            has_network = self._network_manager.has_existing_network(coord)

            if is_connected:
                status = "connected"
            elif has_network:
                status = "saved"
            else:
                status = "new"
            options.append(ui.format_coordinator_option(coord.port, status))

        retry_idx = len(options)
        options.append("Retry detection")
        settings_idx = len(options)
        options.append("Settings")

        title = "◆ Zigbee Coordinators"
        choice = ui.prompt_menu(title, options, show_back=True, show_home=True)

        if choice in (0, MENU_BACK, MENU_HOME):
            self._running = False
            return "exit"
        elif 1 <= choice <= len(self._detected_coordinators):
            selected = self._detected_coordinators[choice - 1]

            # Start network if not already running on this coordinator
            if current_coord is None or selected.port != current_coord.port:
                await self._ensure_network_started(selected)

            return "selected"
        elif choice == retry_idx + 1:
            return "retry"
        elif choice == settings_idx + 1:
            await self._settings_menu()
            return "settings"
        else:
            return "retry"

    async def _settings_menu(self) -> None:
        """Display settings menu."""
        saved_count = self._network_manager.get_saved_network_count()

        options = [
            f"Delete all saved networks ({saved_count} saved)",
        ]

        choice = ui.prompt_menu("◆ Settings", options, show_back=True, show_home=True)

        if choice in (0, MENU_BACK):
            return
        elif choice == MENU_HOME:
            self._running = False
            return
        elif choice == 1:
            await self._delete_all_networks()

    async def _delete_all_networks(self) -> None:
        """Delete all saved network databases."""
        saved_count = self._network_manager.get_saved_network_count()
        if saved_count == 0:
            ui.show_message("Info", "No saved networks to delete")
            return

        confirm = ui.prompt_confirm(
            f"Delete ALL {saved_count} saved network(s)? This cannot be undone.",
            default=False,
        )
        if confirm is None:  # Home pressed
            self._running = False
            return
        if not confirm:
            return

        # Shutdown current network if running
        if self._network_manager.is_running:
            await self._network_manager.shutdown()
            self._pairing_manager = None

        deleted = self._network_manager.delete_all_networks()
        ui.show_message("Success", f"Deleted {deleted} saved network(s)")

    async def _ensure_network_started(self, coordinator: DetectedCoordinator) -> bool:
        """Ensure the network is started, auto-starting if needed.

        Returns True if network is running, False if start failed.
        """
        # Check if we need to switch coordinators
        current_coord = self._network_manager.coordinator
        if self._network_manager.is_running:
            if current_coord is not None and current_coord.port == coordinator.port:
                # Already running on correct coordinator
                return True
            else:
                # Different coordinator - shut down current first
                await self._network_manager.shutdown()

        # Check if we're restoring an existing network
        has_existing = self._network_manager.has_existing_network(coordinator)

        async with ui.spinner("◆ Zigbee") as spin:
            try:
                gateway = await self._network_manager.start_network(coordinator)
                self._pairing_manager = DevicePairingManager(gateway)
                devices = self._network_manager.get_devices()
                status = "Restored" if has_existing else "Started"
                spin.set_status(f"{status}! {len(devices)} device(s)")
                await asyncio.sleep(0.5)  # Brief pause to show status
            except Exception as exc:
                _LOGGER.exception("Network start failed")
                ui.show_message("Error", f"Failed to start network: {exc}")
                return False

        return True

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        self._running = False

    async def _cleanup(self) -> None:
        """Clean up resources."""
        await self._network_manager.shutdown()
        # Clear screen on exit to leave terminal clean
        ui.clear_screen()

    async def _main_menu(self) -> None:
        """Display and handle the main menu (device management)."""
        # If network isn't running (e.g., after a reset), go back to coordinator flow
        if not self._network_manager.is_running:
            await self._coordinator_entry_flow()
            return

        devices = self._network_manager.get_devices()

        # Build menu options: devices first, then actions
        options: list[str] = []
        if devices:
            for device in devices:
                name = device["name"] or device["model"] or str(device["ieee"])
                options.append(ui.format_device_option(name, device["available"]))

        # Add action options
        pair_idx = len(options)
        options.append("Pair new device")
        reset_idx = len(options)
        options.append("Reset network")

        title = "◆ Zigbee"
        choice = ui.prompt_menu(title, options, show_back=True, show_home=True)

        if choice in (0, MENU_HOME):
            self._running = False
        elif choice == MENU_BACK:
            # Back goes to coordinator selection (keep network running)
            await self._coordinator_entry_flow()
        elif devices and choice <= len(devices):
            # Device selected
            await self._control_device_direct(devices[choice - 1])
        elif choice == pair_idx + 1:
            await self._pair_device()
        elif choice == reset_idx + 1:
            await self._reset_network()

    async def _reset_network(self) -> None:
        """Reset the network completely, deleting all paired devices."""
        confirm = ui.prompt_confirm(
            "This will DELETE all paired devices. Are you sure?", default=False
        )
        if confirm is None:  # Home pressed
            self._running = False
            return
        if not confirm:
            return

        coordinator = self._network_manager.coordinator
        async with ui.spinner("◆ Zigbee") as spin:
            await self._network_manager.reset(coordinator)
            self._pairing_manager = None
            spin.set_status("Network reset complete")
            await asyncio.sleep(0.5)

    async def _pair_device(self) -> None:
        """Enable pairing mode to add new devices."""
        options = ["Start pairing (30 seconds)", "Start pairing (60 seconds)"]
        choice = ui.prompt_menu(
            "◆ Pair Device", options, show_back=True, show_home=True
        )

        if choice in (0, MENU_BACK):
            return
        if choice == MENU_HOME:
            self._running = False
            return

        duration = 30 if choice == 1 else 60

        if self._pairing_manager is None:
            ui.show_message("◆ Error", "Pairing manager not initialized")
            return

        pairing_manager = self._pairing_manager

        # Track newly paired devices
        new_devices: list[dict[str, Any]] = []

        try:
            async with ui.spinner("◆ Pairing Mode", "Waiting for device...") as spin:
                await pairing_manager.enable_pairing(duration)

                # Set up event handlers to update spinner status
                def on_joined(event: Any) -> None:
                    spin.set_status("Device joining...")

                def on_initialized(event: Any) -> None:
                    try:
                        info = event.device_info
                        device_name = info.model or info.manufacturer or "Device"
                        spin.set_status(f"Found: {device_name}")
                        # Only track truly new devices (not re-initialized existing ones)
                        if getattr(event, "new_join", True):
                            new_devices.append(
                                {
                                    "ieee": str(info.ieee),
                                    "manufacturer": info.manufacturer,
                                    "model": info.model,
                                }
                            )
                    except Exception as exc:
                        _LOGGER.exception("Error in on_initialized callback: %s", exc)

                unsubscribe = pairing_manager.subscribe_to_events(
                    on_joined=on_joined,
                    on_initialized=on_initialized,
                )

                try:
                    await asyncio.sleep(duration)
                except asyncio.CancelledError:
                    pass
                finally:
                    unsubscribe()
                    await pairing_manager.disable_pairing()

            # Prompt for names for each new device
            for device in new_devices:
                await self._prompt_device_name(device)

        except Exception as exc:
            ui.show_message("◆ Error", f"Pairing failed: {exc}")
            _LOGGER.exception("Pairing failed")

    async def _prompt_device_name(self, device_info: dict[str, Any]) -> None:
        """Prompt the user to name a newly paired device."""
        ieee = device_info["ieee"]
        manufacturer = device_info.get("manufacturer")
        model = device_info.get("model")

        # Suggest a default name based on model or manufacturer
        default_name = model or manufacturer or "New Device"

        name = ui.prompt_device_name(
            title="◆ Name Device",
            manufacturer=manufacturer,
            model=model,
            default=default_name,
        )

        if name:
            self._network_manager.set_device_name(ieee, name)

    async def _wait_for_entities(
        self, ieee: str, name: str, max_wait: float = 10.0
    ) -> list | None:
        """Wait for device entities to be available.

        Newly paired devices may take time to initialize. This method polls
        for entities up to max_wait seconds before giving up.

        Returns:
            List of controllable entities, or None if device not found/no entities.
        """
        poll_interval = 1.0
        elapsed = 0.0

        # Check once before showing spinner
        fresh_info = self._network_manager.get_device_by_ieee(ieee)
        if fresh_info is None:
            ui.show_message("Error", "Device no longer available")
            return None

        device = fresh_info["device"]
        entities = DeviceController.get_controllable_entities(device)
        if entities:
            return entities
        # Check if device has monitorable entities (sensors)
        sensors = DeviceController.get_monitorable_entities(device)
        if sensors:
            return (
                entities  # Return empty controllable list; device menu handles sensors
            )

        # No entities yet - show animated spinner while polling
        async with ui.spinner(f"◆ {name}"):
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                fresh_info = self._network_manager.get_device_by_ieee(ieee)
                if fresh_info is None:
                    return None  # Will show error after spinner exits

                device = fresh_info["device"]
                entities = DeviceController.get_controllable_entities(device)
                if entities:
                    return entities
                # Check for monitorable entities (sensors)
                sensors = DeviceController.get_monitorable_entities(device)
                if sensors:
                    return entities  # Return empty controllable list; device menu handles sensors

        # Timed out - show diagnostic info
        fresh_info = self._network_manager.get_device_by_ieee(ieee)
        if fresh_info is None:
            ui.show_message("Error", "Device no longer available")
            return None

        device = fresh_info["device"]
        all_entities = DeviceController.get_all_entities(device)
        if all_entities:
            msg = f"Device has {len(all_entities)} entities but none are supported"
        else:
            msg = "No entities found after waiting. Device may need more time."
        ui.show_message(name, msg)
        return None

    async def _control_device_direct(self, device_info: dict[str, Any]) -> None:
        """Control a specific device."""
        ieee = str(device_info["ieee"])
        manufacturer = device_info.get("manufacturer")
        model = device_info.get("model")

        # Prompt for name if device doesn't have a custom name yet
        if not device_info.get("custom_name"):
            default_name = model or manufacturer or "Device"
            new_name = ui.prompt_device_name(
                title="◆ Name Device",
                manufacturer=manufacturer,
                model=model,
                default=default_name,
            )
            if new_name:
                self._network_manager.set_device_name(ieee, new_name)
                device_info["name"] = new_name
                device_info["custom_name"] = new_name

        name = device_info["name"] or model or ieee

        # Wait for entities to be available (device may still be initializing)
        entities = await self._wait_for_entities(ieee, name)
        if entities is None:
            return

        while True:
            # Fetch fresh device reference to ensure entities are current
            fresh_info = self._network_manager.get_device_by_ieee(ieee)
            if fresh_info is None:
                ui.show_message("Error", "Device no longer available")
                return

            device = fresh_info["device"]

            # Get controllable and monitorable entities
            entities = DeviceController.get_controllable_entities(device)
            sensors = DeviceController.get_monitorable_entities(device)

            if not entities and not sensors:
                # Show diagnostic info
                all_entities = DeviceController.get_all_entities(device)
                if all_entities:
                    msg = f"Device has {len(all_entities)} entities but none are supported"
                else:
                    msg = "No entities found. Device may still be initializing."
                ui.show_message(name, msg)
                return

            # Build options: controllable entities first
            options: list[str] = []
            entity_infos = [DeviceController.get_entity_info(e) for e in entities]
            # Only show entity names if there are multiple controllable entities
            show_entity_names = len(entity_infos) > 1
            for info in entity_infos:
                state = info.get("state", {})
                # Switch uses "state" key, Light uses "on" key
                is_on = state.get("state") if "state" in state else state.get("on")
                entity_name = None
                if show_entity_names:
                    entity_name = info.get("display_name", "Unknown")
                options.append(ui.format_entity_option(entity_name, is_on))

            # Add sensors option if there are monitorable entities
            sensors_idx = -1
            if sensors:
                sensors_idx = len(options)
                options.append(f"View sensors ({len(sensors)})")

            # Add rename option at the end
            rename_idx = len(options)
            options.append("Rename device")

            choice = ui.prompt_menu(
                f"◆ {name}", options, show_back=True, show_home=True
            )

            if choice in (0, MENU_BACK):
                return
            if choice == MENU_HOME:
                self._running = False
                return

            if choice == rename_idx + 1:
                # Rename device
                new_name = ui.prompt_device_name(
                    title="◆ Rename Device",
                    manufacturer=manufacturer,
                    model=model,
                    default=name,
                )
                if new_name and new_name != name:
                    self._network_manager.set_device_name(ieee, new_name)
                    name = new_name
                continue

            if sensors_idx >= 0 and choice == sensors_idx + 1:
                # View sensors
                await self._view_sensors(device, name)
                continue

            # Toggle the selected entity
            if choice <= len(entities):
                selected_entity = entities[choice - 1]
                try:
                    await DeviceController.toggle(selected_entity)
                except Exception as exc:
                    ui.show_message("Error", f"Control failed: {exc}")
                    _LOGGER.exception("Control failed")

    async def _view_sensors(self, device: Any, device_name: str) -> None:
        """View sensor values for a device."""
        # Get sensors once at start
        sensors = DeviceController.get_monitorable_entities(device)

        if not sensors:
            ui.show_message(f"◆ {device_name}", "No sensors available")
            return

        # Refresh all sensors on entry
        async with ui.spinner(f"◆ {device_name}", status="Reading sensors..."):
            for sensor in sensors:
                await DeviceController.refresh_entity(sensor)

        while True:
            # Build options showing sensor names and values
            options: list[str] = []
            for sensor in sensors:
                info = DeviceController.get_entity_info(sensor)
                sensor_name = info.get("display_name", "Unknown")
                value = DeviceController.format_entity_state(sensor)
                options.append(ui.format_sensor_option(sensor_name, value))

            # Add refresh option
            refresh_idx = len(options) + 1
            options.append("Refresh readings")

            choice = ui.prompt_menu(
                f"◆ {device_name} Sensors", options, show_back=True, show_home=True
            )

            if choice in (0, MENU_BACK):
                return
            if choice == MENU_HOME:
                self._running = False
                return

            # Refresh readings on explicit request
            if choice == refresh_idx:
                async with ui.spinner(
                    f"◆ {device_name}", status="Refreshing sensors..."
                ):
                    for sensor in sensors:
                        await DeviceController.refresh_entity(sensor)
            # Loop back to show updated values


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
