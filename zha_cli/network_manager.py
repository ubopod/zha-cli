"""Network management for the ZHA CLI."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from zha.application.gateway import Gateway
from zha.application.helpers import CoordinatorConfiguration, ZHAConfiguration, ZHAData

if TYPE_CHECKING:
    from zha_cli.coordinator_probe import DetectedCoordinator

_LOGGER = logging.getLogger(__name__)

# Default data directory for persistent storage
DEFAULT_DATA_DIR = Path.home() / ".zha-cli"


class NetworkManager:
    """Manages the Zigbee network lifecycle."""

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize the network manager.

        Args:
            data_dir: Directory for persistent storage. Defaults to ~/.zha-cli
        """
        self._gateway: Gateway | None = None
        self._coordinator: DetectedCoordinator | None = None
        self._data_dir = data_dir or DEFAULT_DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def gateway(self) -> Gateway | None:
        """Return the current gateway."""
        return self._gateway

    @property
    def coordinator(self) -> DetectedCoordinator | None:
        """Return the current coordinator."""
        return self._coordinator

    @property
    def is_running(self) -> bool:
        """Return True if the network is running."""
        return self._gateway is not None and not self._gateway.shutting_down

    def _get_database_path(self, coordinator: DetectedCoordinator) -> Path:
        """Get the database path for a coordinator.

        Uses a hash of the port path to create a unique filename.
        This ensures devices persist when reconnecting to the same coordinator.
        """
        # Create a short hash from the port path for the filename
        port_hash = hashlib.md5(coordinator.port.encode()).hexdigest()[:12]
        # Use a readable name based on the port
        port_name = coordinator.port.replace("/", "_").replace("\\", "_")
        db_name = f"zigbee_{port_name}_{port_hash}.db"
        return self._data_dir / db_name

    async def start_network(self, coordinator: DetectedCoordinator) -> Gateway:
        """Start the Zigbee network with the specified coordinator.

        Creates a ZHAData configuration and initializes the gateway.

        Args:
            coordinator: The detected coordinator to use.

        Returns:
            The initialized Gateway instance.

        Raises:
            Exception: If the gateway fails to initialize.

        """
        if self._gateway is not None:
            _LOGGER.warning("Network already running, shutting down first")
            await self.shutdown()

        # Get persistent database path for this coordinator
        db_path = self._get_database_path(coordinator)

        _LOGGER.info(
            "Starting network with %s at %s (%d baud), database: %s",
            coordinator.radio_type.pretty_name,
            coordinator.port,
            coordinator.baudrate,
            db_path,
        )

        # Create the configuration with persistent database
        coordinator_config = CoordinatorConfiguration(
            path=coordinator.port,
            baudrate=coordinator.baudrate,
            radio_type=coordinator.radio_type.name,
        )

        zha_config = ZHAConfiguration(
            coordinator_configuration=coordinator_config,
            database_path=str(db_path),
        )

        zha_data = ZHAData(config=zha_config)

        # Create and initialize the gateway
        self._gateway = await Gateway.async_from_config(zha_data)
        await self._gateway.async_initialize()

        self._coordinator = coordinator

        _LOGGER.info("Network started successfully")
        return self._gateway

    async def shutdown(self) -> None:
        """Shut down the Zigbee network."""
        if self._gateway is None:
            _LOGGER.debug("No network to shut down")
            return

        _LOGGER.info("Shutting down network")
        await self._gateway.shutdown()
        self._gateway = None
        self._coordinator = None
        _LOGGER.info("Network shut down successfully")

    def get_devices(self) -> list[dict]:
        """Get all paired devices.

        Returns:
            List of device info dictionaries.

        """
        if self._gateway is None:
            return []

        devices = []
        for device in self._gateway.devices.values():
            # Skip the coordinator
            if device.is_coordinator:
                continue

            devices.append(
                {
                    "ieee": device.ieee,
                    "nwk": device.nwk,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "name": device.name,
                    "available": device.available,
                    "device": device,
                }
            )

        return devices
