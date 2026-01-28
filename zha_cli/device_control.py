"""Device control for the ZHA CLI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from zha.application import Platform
from zha.application.platforms import PlatformEntity

if TYPE_CHECKING:
    from zha.zigbee.device import Device

_LOGGER = logging.getLogger(__name__)

# Platforms that support on/off control
CONTROLLABLE_PLATFORMS = {Platform.SWITCH, Platform.LIGHT}

# Platforms that are monitorable (read-only sensors and status)
MONITORABLE_PLATFORMS = {
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
}


class DeviceController:
    """Controls device entities."""

    @staticmethod
    def get_controllable_entities(device: Device) -> list[PlatformEntity]:
        """Get entities that can be controlled (on/off).

        Args:
            device: The ZHA device.

        Returns:
            List of entities that support turn_on/turn_off.

        """
        entities: list[PlatformEntity] = []

        for (platform, _unique_id), entity in device.platform_entities.items():
            if platform in CONTROLLABLE_PLATFORMS:
                entities.append(entity)

        return entities

    @staticmethod
    def get_all_entities(device: Device) -> list[PlatformEntity]:
        """Get all entities for a device.

        Args:
            device: The ZHA device.

        Returns:
            List of all platform entities.

        """
        return list(device.platform_entities.values())

    @staticmethod
    def get_monitorable_entities(device: Device) -> list[PlatformEntity]:
        """Get entities that can be monitored (sensors, binary sensors, etc.).

        Args:
            device: The ZHA device.

        Returns:
            List of entities that report state but can't be controlled.

        """
        entities: list[PlatformEntity] = []

        for (platform, _unique_id), entity in device.platform_entities.items():
            if platform in MONITORABLE_PLATFORMS:
                entities.append(entity)

        return entities

    @staticmethod
    def format_entity_state(entity: PlatformEntity) -> str:
        """Format entity state for display.

        Args:
            entity: The entity to format.

        Returns:
            Human-readable state string.

        """
        platform = entity.PLATFORM

        # Binary sensor
        if platform == Platform.BINARY_SENSOR:
            is_on = entity.state.get("state", False)
            return "Detected" if is_on else "Clear"

        # Regular sensor - use native_value property directly
        if platform == Platform.SENSOR:
            value = getattr(entity, "native_value", None)
            if value is not None:
                unit = getattr(entity, "native_unit_of_measurement", "") or ""
                return f"{value} {unit}".strip()
            return "—"

        # Device tracker
        if platform == Platform.DEVICE_TRACKER:
            connected = entity.state.get("connected")
            if connected is not None:
                return str(connected)
            return "—"

        # Event - show last event type
        if platform == Platform.EVENT:
            event_type = entity.state.get("event_type")
            if event_type is not None:
                return f"Last: {event_type}"
            return "No events"

        # Fallback - show raw state or dash
        state = entity.state
        if not state:
            return "—"
        return str(state)

    @staticmethod
    async def refresh_entity(entity: PlatformEntity) -> None:
        """Refresh entity state from device.

        Args:
            entity: The entity to refresh.

        """
        if hasattr(entity, "async_update"):
            await entity.async_update()

    @staticmethod
    def get_display_name(entity: PlatformEntity) -> str:
        """Get a user-friendly display name for an entity.

        Uses fallback_name if available, otherwise generates a name from
        device_class or platform type.

        Args:
            entity: The entity to get a name for.

        Returns:
            Human-readable display name.

        """
        # 1. Use fallback_name if available and not "None"
        if entity.fallback_name and entity.fallback_name != "None":
            return entity.fallback_name

        # 2. Use device_class if available (title-cased)
        device_class = getattr(entity, "device_class", None)
        if device_class:
            # Handle enum values or strings
            class_name = (
                device_class.value
                if hasattr(device_class, "value")
                else str(device_class)
            )
            return class_name.replace("_", " ").title()

        # 3. Fall back to platform type
        platform = entity.PLATFORM
        if hasattr(platform, "value"):
            return platform.value.replace("_", " ").title()
        return str(platform).title()

    @staticmethod
    async def turn_on(entity: PlatformEntity) -> None:
        """Turn on an entity.

        Args:
            entity: The entity to turn on.

        """
        if not hasattr(entity, "async_turn_on"):
            raise ValueError(f"Entity {entity.unique_id} does not support turn_on")

        _LOGGER.info("Turning on entity: %s", entity.unique_id)
        await entity.async_turn_on()
        _LOGGER.info("Entity turned on: %s", entity.unique_id)

    @staticmethod
    async def turn_off(entity: PlatformEntity) -> None:
        """Turn off an entity.

        Args:
            entity: The entity to turn off.

        """
        if not hasattr(entity, "async_turn_off"):
            raise ValueError(f"Entity {entity.unique_id} does not support turn_off")

        _LOGGER.info("Turning off entity: %s", entity.unique_id)
        await entity.async_turn_off()
        _LOGGER.info("Entity turned off: %s", entity.unique_id)

    @staticmethod
    async def toggle(entity: PlatformEntity) -> None:
        """Toggle an entity.

        Args:
            entity: The entity to toggle.

        """
        state = entity.state
        # Switch uses "state" key, Light uses "on" key
        is_on = state.get("state") if "state" in state else state.get("on", False)

        if is_on:
            await DeviceController.turn_off(entity)
        else:
            await DeviceController.turn_on(entity)

    @staticmethod
    def get_entity_info(entity: PlatformEntity) -> dict[str, Any]:
        """Get information about an entity.

        Args:
            entity: The entity to get info for.

        Returns:
            Dictionary with entity information.

        """
        return {
            "unique_id": entity.unique_id,
            "platform": entity.PLATFORM,
            "fallback_name": entity.fallback_name,
            "display_name": DeviceController.get_display_name(entity),
            "state": entity.state,
            "available": getattr(entity, "available", True),
        }
