"""Remote entity: send any KEY_* to the Frame TV."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_HOLD_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
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
    async_add_entities([FrameRemote(entry.runtime_data)])


class FrameRemote(FrameEntity, RemoteEntity):
    """Navigation / key remote."""

    _attr_translation_key = "remote"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "remote")

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.power_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.turn_off()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        hold = kwargs.get(ATTR_HOLD_SECS) or None
        try:
            for _ in range(repeats):
                for key in command:
                    await self.coordinator.api.send_key(key, hold=hold)
                    await asyncio.sleep(delay)
        except FrameTVError as err:
            raise HomeAssistantError(f"Frame TV command failed: {err}") from err
