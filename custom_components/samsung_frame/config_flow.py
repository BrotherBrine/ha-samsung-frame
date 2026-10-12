"""Config flow for Samsung Frame TV."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .api import FrameTV, FrameTVError, FrameTVUnauthorized
from .const import (
    CONF_APPS,
    CONF_INPUTS,
    CONF_MAC,
    CONF_MODEL,
    CONF_SMARTTHINGS_ENTITY,
    CONF_TOKEN,
    DEFAULT_APPS,
    DEFAULT_INPUTS,
    DOMAIN,
)


class FrameConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Frame TV: enter its IP, then accept the prompt on the TV."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str = "Frame TV"
        self._device: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            self._name = user_input.get(CONF_NAME) or "Frame TV"
            api = FrameTV(async_get_clientsession(self.hass, verify_ssl=False), self._host)
            info = await api.device_info(timeout=5)
            if not info:
                errors["base"] = "cannot_connect"
            else:
                self._device = info.get("device", {})
                unique = self._device.get("duid") or info.get("id") or self._host
                await self.async_set_unique_id(unique)
                self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
                return await self.async_step_pair()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_NAME, default="Frame TV"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = FrameTV(
                async_get_clientsession(self.hass, verify_ssl=False), self._host
            )
            try:
                token = await api.pair(timeout=30)
            except FrameTVUnauthorized:
                errors["base"] = "denied"
            except (FrameTVError, TimeoutError):
                errors["base"] = "pair_failed"
            else:
                mac = self._device.get("wifiMac")
                return self.async_create_entry(
                    title=self._name,
                    data={
                        CONF_HOST: self._host,
                        CONF_TOKEN: token,
                        CONF_MAC: format_mac(mac) if mac else None,
                        CONF_MODEL: self._device.get("modelName")
                        or self._device.get("model"),
                    },
                )

        return self.async_show_form(
            step_id="pair",
            description_placeholders={
                "model": self._device.get("modelName") or "Samsung TV"
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FrameOptionsFlow()


class FrameOptionsFlow(OptionsFlow):
    """Edit the app and input lists."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        multiline = TextSelector(TextSelectorConfig(multiline=True))
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_APPS, default=opts.get(CONF_APPS, DEFAULT_APPS)
                    ): multiline,
                    vol.Required(
                        CONF_INPUTS, default=opts.get(CONF_INPUTS, DEFAULT_INPUTS)
                    ): multiline,
                    # suggested_value (not default) so the field can be cleared
                    vol.Optional(
                        CONF_SMARTTHINGS_ENTITY,
                        description={
                            "suggested_value": opts.get(CONF_SMARTTHINGS_ENTITY)
                        },
                    ): EntitySelector(EntitySelectorConfig(domain="media_player")),
                }
            ),
        )
