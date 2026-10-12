"""Base entity for Samsung Frame TV."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, CONF_MODEL, DOMAIN
from .coordinator import FrameCoordinator


class FrameEntity(CoordinatorEntity[FrameCoordinator]):
    """Common device info for all Frame TV entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FrameCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        mac = entry.data.get(CONF_MAC)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer="Samsung",
            model=entry.data.get(CONF_MODEL),
            name=entry.title,
            configuration_url=f"http://{entry.data[CONF_HOST]}:8001/api/v2/",
        )

    @property
    def available(self) -> bool:
        # Stay available while off so the TV can still be turned on.
        return True
