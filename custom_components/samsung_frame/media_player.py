"""Media player for Samsung Frame TV."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import FrameConfigEntry
from .api import FrameTVError
from .entity import FrameEntity

SUPPORTED = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FrameMediaPlayer(entry.runtime_data)])


class FrameMediaPlayer(FrameEntity, MediaPlayerEntity):
    """The TV as a media player."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = SUPPORTED

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "media_player")

    @property
    def state(self) -> MediaPlayerState:
        data = self.coordinator.data
        if not data or not data.power_on:
            return MediaPlayerState.OFF
        if data.art_mode:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        data = self.coordinator.data
        return data.volume / 100 if data and data.volume is not None else None

    @property
    def is_volume_muted(self) -> bool | None:
        data = self.coordinator.data
        return data.muted if data else None

    @property
    def source_list(self) -> list[str]:
        return [*self.coordinator.inputs, *self.coordinator.apps]

    @property
    def source(self) -> str | None:
        data = self.coordinator.data
        if not data or not data.power_on:
            return None
        if data.art_mode:
            return "Art Mode"
        return data.app or self.coordinator.active_input()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if linked := self.coordinator.smartthings_entity:
            # Repaint as soon as SmartThings reports an input change.
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [linked], self._on_smartthings_change
                )
            )

    @callback
    def _on_smartthings_change(self, _event: Event) -> None:
        self.async_write_ha_state()

    @property
    def app_name(self) -> str | None:
        data = self.coordinator.data
        return data.app if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "art_mode": bool(data and data.art_mode),
            "inputs": list(self.coordinator.inputs),
            "apps": {name: app_id for name, (app_id, _) in self.coordinator.apps.items()},
        }

    async def _run(self, coro) -> None:
        try:
            await coro
        except FrameTVError as err:
            raise HomeAssistantError(f"Frame TV command failed: {err}") from err

    async def async_turn_on(self) -> None:
        await self._run(self.coordinator.turn_on())

    async def async_turn_off(self) -> None:
        await self._run(self.coordinator.turn_off())

    async def async_volume_up(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_VOLUP"))
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_VOLDOWN"))
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        await self._run(self.coordinator.set_volume(round(volume * 100)))

    async def async_mute_volume(self, mute: bool) -> None:
        await self._run(self.coordinator.set_mute(mute))

    async def async_select_source(self, source: str) -> None:
        try:
            await self._run(self.coordinator.select_source(source))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_play(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_PLAY"))

    async def async_media_pause(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_PAUSE"))

    async def async_media_stop(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_STOP"))

    async def async_media_next_track(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_FF"))

    async def async_media_previous_track(self) -> None:
        await self._run(self.coordinator.api.send_key("KEY_REWIND"))

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """media_content_type: app (id or name) | key (KEY_*)."""
        if media_type == MediaType.APP:
            names = self.coordinator.apps
            if media_id in names:
                await self._run(self.coordinator.select_source(media_id))
            else:
                await self._run(self.coordinator.api.launch_app(media_id))
        elif media_type == "key":
            await self._run(self.coordinator.api.send_key(media_id))
        else:
            raise HomeAssistantError(f"Unsupported media type {media_type}")
