"""Samsung Frame TV integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FrameTV
from .const import CARD_URL, CARD_VERSION, CONF_SMARTTHINGS_ENTITY, CONF_TOKEN, DOMAIN
from .coordinator import FrameCoordinator

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type FrameConfigEntry = ConfigEntry[FrameCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled Lovelace card and load it on every dashboard."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL,
                str(Path(__file__).parent / "frontend" / "frame-tv-card.js"),
                cache_headers=False,
            )
        ]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FrameConfigEntry) -> bool:
    @callback
    def _save_token(token: str) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKEN: token}
        )

    api = FrameTV(
        async_get_clientsession(hass, verify_ssl=False),
        entry.data[CONF_HOST],
        token=entry.data.get(CONF_TOKEN),
        on_new_token=_save_token,
    )
    coordinator = FrameCoordinator(hass, entry, api)
    # The TV may simply be off, so don't fail setup if the first poll misses it.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Apps/inputs are read live, but the SmartThings link is subscribed once at
    # setup, so reload only when that option changes (not on token saves).
    linked = entry.options.get(CONF_SMARTTHINGS_ENTITY)

    async def _options_updated(hass: HomeAssistant, entry: FrameConfigEntry) -> None:
        if entry.options.get(CONF_SMARTTHINGS_ENTITY) != linked:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FrameConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.close()
    return unloaded
