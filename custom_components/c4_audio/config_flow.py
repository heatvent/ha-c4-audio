"""Config flow for Control4 Audio."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_EQ,
    CONF_MODEL,
    CONF_ON_VOLUME,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_NAMES,
    CONF_SWITCH_ENTRY_ID,
    CONF_SWITCH_FEEDS,
    CONF_UDP_TIMEOUT,
    CONF_ZONE_NAMES,
    DEFAULT_ON_VOLUME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SWITCH_FEEDS,
    DEFAULT_SWITCH_ON_VOLUME,
    DEFAULT_UDP_TIMEOUT,
    DOMAIN,
    MODELS,
)
from .udp_client import async_probe_firmware


def _default_lines(count: int, prefix: str) -> str:
    return "\n".join(f"{prefix} {index}" for index in range(1, count + 1))


def _model_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Control4 Amp")): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(
                CONF_MODEL, default=defaults.get(CONF_MODEL, "c4_16amp3_b")
            ): vol.In({key: info["name"] for key, info in MODELS.items()}),
        }
    )


class C4AudioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add one chassis (amp or matrix) per entry. Repeat for more amps or a switch."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            firmware = await async_probe_firmware(host, port, DEFAULT_UDP_TIMEOUT)
            if firmware is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()
                self._data = {**user_input, CONF_HOST: host}
                return await self.async_step_names()
        return self.async_show_form(
            step_id="user", data_schema=_model_schema(), errors=errors
        )

    async def async_step_names(self, user_input: dict[str, Any] | None = None):
        model = MODELS[self._data[CONF_MODEL]]
        is_matrix = model["kind"] == "matrix"
        default_volume = DEFAULT_SWITCH_ON_VOLUME if is_matrix else DEFAULT_ON_VOLUME
        if user_input is not None:
            self._data.update(user_input)
            if is_matrix:
                return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
            return await self.async_step_link()

        return self.async_show_form(
            step_id="names",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ZONE_NAMES, default=_default_lines(model["zones"], "Zone")
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Required(
                        CONF_SOURCE_NAMES, default=_default_lines(model["inputs"], "Input")
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Required(CONF_ON_VOLUME, default=default_volume): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=100)
                    ),
                    vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=300)
                    ),
                    vol.Required(CONF_UDP_TIMEOUT, default=DEFAULT_UDP_TIMEOUT): vol.All(
                        vol.Coerce(float), vol.Range(min=0.25, max=5.0)
                    ),
                    vol.Optional(CONF_ENABLE_EQ, default=not is_matrix): bool,
                }
            ),
        )

    async def async_step_link(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            data = {**self._data, **user_input}
            if not data.get(CONF_SWITCH_ENTRY_ID):
                data.pop(CONF_SWITCH_ENTRY_ID, None)
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        switches = [
            selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if MODELS.get(entry.data.get(CONF_MODEL), {}).get("kind") == "matrix"
        ]
        schema: dict[Any, Any] = {}
        if switches:
            schema[
                vol.Optional(CONF_SWITCH_ENTRY_ID)
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=switches, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            schema[
                vol.Optional(CONF_SWITCH_FEEDS, default=DEFAULT_SWITCH_FEEDS)
            ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
        if not schema:
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="link", data_schema=vol.Schema(schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return C4AudioOptionsFlow(config_entry)


class C4AudioOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        model = MODELS[self._entry.data[CONF_MODEL]]
        is_matrix = model["kind"] == "matrix"
        if user_input is not None:
            if not user_input.get(CONF_SWITCH_ENTRY_ID):
                user_input[CONF_SWITCH_ENTRY_ID] = None
            return self.async_create_entry(title="", data=user_input)

        default_volume = DEFAULT_SWITCH_ON_VOLUME if is_matrix else DEFAULT_ON_VOLUME
        fields: dict[Any, Any] = {
            vol.Required(
                CONF_ZONE_NAMES,
                default=self._entry.options.get(
                    CONF_ZONE_NAMES, self._entry.data.get(CONF_ZONE_NAMES, "")
                ),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_SOURCE_NAMES,
                default=self._entry.options.get(
                    CONF_SOURCE_NAMES, self._entry.data.get(CONF_SOURCE_NAMES, "")
                ),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_ON_VOLUME,
                default=self._entry.options.get(
                    CONF_ON_VOLUME, self._entry.data.get(CONF_ON_VOLUME, default_volume)
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Required(
                CONF_POLL_INTERVAL,
                default=self._entry.options.get(
                    CONF_POLL_INTERVAL,
                    self._entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            vol.Required(
                CONF_UDP_TIMEOUT,
                default=self._entry.options.get(
                    CONF_UDP_TIMEOUT,
                    self._entry.data.get(CONF_UDP_TIMEOUT, DEFAULT_UDP_TIMEOUT),
                ),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.25, max=5.0)),
        }
        if not is_matrix:
            fields[
                vol.Optional(
                    CONF_ENABLE_EQ,
                    default=self._entry.options.get(
                        CONF_ENABLE_EQ, self._entry.data.get(CONF_ENABLE_EQ, True)
                    ),
                )
            ] = bool
            switches = [
                selector.SelectOptionDict(value="", label="Not linked")
            ] + [
                selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
                if MODELS.get(entry.data.get(CONF_MODEL), {}).get("kind") == "matrix"
            ]
            current_switch = self._entry.options.get(
                CONF_SWITCH_ENTRY_ID, self._entry.data.get(CONF_SWITCH_ENTRY_ID, "")
            ) or ""
            fields[
                vol.Optional(CONF_SWITCH_ENTRY_ID, default=current_switch)
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=switches, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            fields[
                vol.Optional(
                    CONF_SWITCH_FEEDS,
                    default=self._entry.options.get(
                        CONF_SWITCH_FEEDS,
                        self._entry.data.get(CONF_SWITCH_FEEDS, DEFAULT_SWITCH_FEEDS),
                    ),
                )
            ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
            description_placeholders={"model": model["name"]},
        )
