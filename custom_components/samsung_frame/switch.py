"""Art Mode switch for Samsung Frame TV."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FrameConfigEntry
from .api import FrameTVError
from .entity import FrameEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FrameArtModeSwitch(entry.runtime_data)])


class FrameArtModeSwitch(FrameEntity, SwitchEntity):
    """On = showing art, off = TV mode (or TV powered off)."""

    _attr_translation_key = "art_mode"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "art_mode")

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.power_on and data.art_mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.set_art_mode(True)
        except FrameTVError as err:
            raise HomeAssistantError(f"Could not enter Art Mode: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.set_art_mode(False)
        except FrameTVError as err:
            raise HomeAssistantError(f"Could not leave Art Mode: {err}") from err
