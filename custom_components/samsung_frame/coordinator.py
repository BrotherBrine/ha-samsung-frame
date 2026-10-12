"""Polling coordinator and command helpers for a Samsung Frame TV."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import FrameTV, FrameTVError
from .const import (
    CONF_APPS,
    CONF_INPUTS,
    CONF_MAC,
    CONF_SMARTTHINGS_ENTITY,
    DEFAULT_APPS,
    DEFAULT_INPUTS,
    DOMAIN,
    INPUT_COMMAND_GRACE_SECONDS,
    SCAN_INTERVAL_SECONDS,
    TUNER_SOURCE_ALIASES,
    parse_mapping,
)

_LOGGER = logging.getLogger(__name__)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


@dataclass
class FrameState:
    """Snapshot of the TV."""

    reachable: bool = False
    power_on: bool = False
    art_mode: bool | None = None
    art_supported: bool = False
    volume: int | None = None
    muted: bool | None = None
    app: str | None = None
    info: dict = field(default_factory=dict)


class FrameCoordinator(DataUpdateCoordinator[FrameState]):
    """Polls the TV and exposes high level commands to entities."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FrameTV) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.current_input: str | None = None
        self._input_commanded_at = 0.0
        self._art_failures = 0

    # ------------------------------------------------------------- settings

    @property
    def apps(self) -> dict[str, tuple[str, bool]]:
        return parse_mapping(self.config_entry.options.get(CONF_APPS, DEFAULT_APPS))

    @property
    def inputs(self) -> dict[str, tuple[str, bool]]:
        return parse_mapping(self.config_entry.options.get(CONF_INPUTS, DEFAULT_INPUTS))

    @property
    def smartthings_entity(self) -> str | None:
        return self.config_entry.options.get(CONF_SMARTTHINGS_ENTITY) or None

    # ---------------------------------------------------------- active input

    def _smartthings_input(self) -> str | None:
        """Map the linked SmartThings entity's source onto one of our input names."""
        if not self.smartthings_entity:
            return None
        st = self.hass.states.get(self.smartthings_entity)
        raw = st and st.attributes.get("source")
        if not raw:
            return None
        norm = _norm(raw)
        for name, (key, _) in self.inputs.items():
            # "HDMI 1" / "KEY_HDMI1" both match SmartThings "HDMI1"
            if norm in (_norm(name), _norm(key.removeprefix("KEY_"))):
                return name
            if norm in TUNER_SOURCE_ALIASES and key.upper() == "KEY_TV":
                return name
        return str(raw)

    def active_input(self) -> str | None:
        """Best guess at the current input: a fresh command wins, then SmartThings."""
        recent = (
            self.current_input is not None
            and time.monotonic() - self._input_commanded_at < INPUT_COMMAND_GRACE_SECONDS
        )
        if recent:
            return self.current_input
        return self._smartthings_input() or self.current_input

    # --------------------------------------------------------------- polling

    async def _async_update_data(self) -> FrameState:
        info = await self.api.device_info()
        if not info:
            await self.api.close()
            return FrameState()

        device = info.get("device", {})
        state = FrameState(
            reachable=True,
            power_on=device.get("PowerState", "on").lower() == "on",
            art_supported=str(device.get("FrameTVSupport", "")).lower() == "true",
            info=device,
        )
        if not state.power_on:
            return state

        if state.art_supported:
            try:
                state.art_mode = await self.api.get_art_mode()
                self._art_failures = 0
            except FrameTVError as err:
                self._art_failures += 1
                # keep the last known value through brief hiccups
                if self.data and self._art_failures < 3:
                    state.art_mode = self.data.art_mode
                _LOGGER.debug("Art mode query failed: %s", err)

        state.volume, state.muted = await asyncio.gather(
            self.api.get_volume(), self.api.get_mute()
        )

        if not state.art_mode:
            apps = self.apps
            visible = await asyncio.gather(
                *(self.api.app_visible(app_id) for app_id, _ in apps.values())
            )
            state.app = next(
                (name for name, vis in zip(apps, visible, strict=True) if vis), None
            )
        return state

    # -------------------------------------------------------------- commands

    async def _refresh_soon(self, delay: float = 1.5) -> None:
        """Re-poll a little later without blocking the service call."""

        async def _later() -> None:
            await asyncio.sleep(delay)
            await self.async_request_refresh()

        self.config_entry.async_create_background_task(
            self.hass, _later(), f"{DOMAIN}_refresh"
        )

    async def turn_on(self) -> None:
        state = self.data
        if state and state.power_on:
            if state.art_mode:
                await self.set_art_mode(False)
            return
        mac = self.config_entry.data.get(CONF_MAC)
        if mac:
            await self.hass.async_add_executor_job(FrameTV.wake_on_lan, mac)
        if state and state.reachable:
            await self.api.send_key("KEY_POWER")
        await self._refresh_soon(4)

    async def turn_off(self) -> None:
        # A long press fully powers off a Frame; a short press only enters Art Mode.
        await self.api.send_key("KEY_POWER", hold=3)
        await self._refresh_soon(2)

    async def set_art_mode(self, on: bool) -> None:
        state = self.data
        if state and not state.power_on and on:
            # From standby the TV wakes straight into Art Mode with a short press.
            await self.turn_on()
            return
        try:
            await self.api.set_art_mode(on)
        except FrameTVError as err:
            _LOGGER.debug("Art API failed (%s), falling back to KEY_POWER", err)
            if state is None or state.art_mode != on:
                await self.api.send_key("KEY_POWER")
        if state:
            state.art_mode = on
            self.async_set_updated_data(state)
        await self._refresh_soon(3)

    async def select_source(self, source: str) -> None:
        if self.data and self.data.art_mode:
            await self.set_art_mode(False)
            await asyncio.sleep(1.5)
        if source in self.inputs:
            key, _ = self.inputs[source]
            await self.api.send_key(key)
            self.current_input = source
            self._input_commanded_at = time.monotonic()
        elif source in self.apps:
            app_id, native = self.apps[source]
            await self.api.launch_app(app_id, native)
            self.current_input = None
        else:
            raise ValueError(f"Unknown source {source}")
        await self._refresh_soon(3)

    async def set_volume(self, level: int) -> None:
        if not await self.api.set_volume(level):
            raise FrameTVError("Volume could not be set over UPnP")
        if self.data:
            self.data.volume = level
            self.async_set_updated_data(self.data)

    async def set_mute(self, mute: bool) -> None:
        if not await self.api.set_mute(mute):
            await self.api.send_key("KEY_MUTE")
        if self.data:
            self.data.muted = mute
            self.async_set_updated_data(self.data)
