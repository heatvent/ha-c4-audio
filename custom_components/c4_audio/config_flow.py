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
    CONF_IDENT,
    CONF_MODEL,
    CONF_ON_VOLUME,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_NAMES,
    CONF_SWITCH_ENTRY_ID,
    CONF_SWITCH_FEEDS,
    CONF_UDP_TIMEOUT,
    CONF_ZONE_NAMES,
    CONF_ZONES,
    DEFAULT_ON_VOLUME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SWITCH_FEEDS,
    DEFAULT_SWITCH_ON_VOLUME,
    DEFAULT_UDP_TIMEOUT,
    DOMAIN,
    MODEL_AMP16,
    MODELS,
    SETUP_MODELS,
)
from .discovery import async_sddp_search, identity_from_info
from .udp_client import async_probe_identity

MANUAL_ENTRY = "manual"


def _default_lines(count: int, prefix: str) -> str:
    return "\n".join(f"{prefix} {index}" for index in range(1, count + 1))


def _zone_name_key(index: int) -> str:
    return f"zone_{index}_name"


def _zone_area_key(index: int) -> str:
    return f"zone_{index}_area"


def _stored_zone_map(data: dict[str, Any], options: dict[str, Any] | None, count: int) -> dict[int, dict]:
    from .routing import parse_zone_map

    blob = (options or {}).get(CONF_ZONES, data.get(CONF_ZONES))
    legacy = (options or {}).get(CONF_ZONE_NAMES, data.get(CONF_ZONE_NAMES))
    return parse_zone_map(blob, count, legacy)


def _zone_schema(count: int, stored: dict[int, dict]) -> dict[Any, Any]:
    fields: dict[Any, Any] = {}
    for index in range(1, count + 1):
        cfg = stored.get(index, {})
        fields[vol.Optional(_zone_name_key(index), default=cfg.get("name") or "")] = str
        area = cfg.get("area_id")
        if area:
            fields[
                vol.Optional(_zone_area_key(index), default=area)
            ] = selector.AreaSelector()
        else:
            fields[vol.Optional(_zone_area_key(index))] = selector.AreaSelector()
    return fields


def _extract_zones(user_input: dict[str, Any], count: int) -> dict[str, Any]:
    packed = dict(user_input)
    zones: dict[str, dict[str, str | None]] = {}
    for index in range(1, count + 1):
        name_key = _zone_name_key(index)
        area_key = _zone_area_key(index)
        name = str(packed.pop(name_key, "") or "").strip()
        area = packed.pop(area_key, None) or None
        zones[str(index)] = {"name": name, "area_id": area}
    packed[CONF_ZONES] = zones
    packed.pop(CONF_ZONE_NAMES, None)
    return packed


def _model_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Control4 Amp")): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(
                CONF_MODEL, default=defaults.get(CONF_MODEL, MODEL_AMP16)
            ): vol.In({key: info["name"] for key, info in SETUP_MODELS.items()}),
        }
    )


class C4AudioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add one chassis (amp or matrix) per entry. Repeat for more amps or a switch."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._discovered: list = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is None:
            self._discovered = await async_sddp_search()
            if self._discovered:
                return await self.async_step_discover()
            return self.async_show_form(step_id="user", data_schema=_model_schema())
        return await self._async_validate_manual(user_input, errors)

    async def async_step_discover(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            options = [
                selector.SelectOptionDict(
                    value=device.ident,
                    label=f"{device.model_name or device.sddp_type or 'Control4'} ({device.host})",
                )
                for device in self._discovered
            ]
            options.append(
                selector.SelectOptionDict(value=MANUAL_ENTRY, label="Enter IP address manually")
            )
            return self.async_show_form(
                step_id="discover",
                data_schema=vol.Schema(
                    {
                        vol.Required("device"): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=options, mode=selector.SelectSelectorMode.DROPDOWN
                            )
                        )
                    }
                ),
            )
        if user_input["device"] == MANUAL_ENTRY:
            return self.async_show_form(step_id="user", data_schema=_model_schema())
        device = next(item for item in self._discovered if item.ident == user_input["device"])
        identity = await async_probe_identity(device.host, DEFAULT_PORT, DEFAULT_UDP_TIMEOUT)
        if identity is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_model_schema(
                    {
                        CONF_HOST: device.host,
                        CONF_NAME: device.model_name or "Control4 Amp",
                        CONF_MODEL: device.suggested_model or MODEL_AMP16,
                    }
                ),
                errors={"base": "cannot_connect"},
            )
        unique = identity_from_info(identity.info, device.ident)
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
        model = identity.model_id or device.suggested_model or MODEL_AMP16
        self._data = {
            CONF_NAME: device.model_name or device.ident,
            CONF_HOST: device.host,
            CONF_PORT: DEFAULT_PORT,
            CONF_MODEL: model,
            CONF_IDENT: unique,
        }
        return await self.async_step_names()

    async def async_step_dhcp(self, discovery_info: Any):
        host = discovery_info.ip
        identity = await async_probe_identity(host, DEFAULT_PORT, DEFAULT_UDP_TIMEOUT)
        if identity is None or identity.model_id is None:
            return self.async_abort(reason="not_audio_chassis")
        unique = identity_from_info(identity.info, getattr(discovery_info, "macaddress", host))
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._data = {
            CONF_NAME: identity.info or host,
            CONF_HOST: host,
            CONF_PORT: DEFAULT_PORT,
            CONF_MODEL: identity.model_id,
            CONF_IDENT: unique,
        }
        return await self.async_step_names()

    async def _async_validate_manual(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ):
        host = user_input[CONF_HOST].strip()
        port = int(user_input[CONF_PORT])
        identity = await async_probe_identity(host, port, DEFAULT_UDP_TIMEOUT)
        if identity is None:
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user", data_schema=_model_schema(user_input), errors=errors
            )
        unique = identity_from_info(identity.info, host)
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        model = user_input.get(CONF_MODEL) or identity.model_id or MODEL_AMP16
        if identity.model_id:
            model = identity.model_id
        self._data = {
            **user_input,
            CONF_HOST: host,
            CONF_MODEL: model,
            CONF_IDENT: unique,
        }
        return await self.async_step_names()

    async def async_step_names(self, user_input: dict[str, Any] | None = None):
        model = MODELS[self._data[CONF_MODEL]]
        is_matrix = model["kind"] == "matrix"
        default_volume = DEFAULT_SWITCH_ON_VOLUME if is_matrix else DEFAULT_ON_VOLUME
        if user_input is not None:
            self._data.update(_extract_zones(user_input, model["zones"]))
            if is_matrix:
                return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
            return await self.async_step_link()

        stored = _stored_zone_map(self._data, None, model["zones"])
        fields: dict[Any, Any] = {}
        fields.update(_zone_schema(model["zones"], stored))
        fields[
            vol.Required(
                CONF_SOURCE_NAMES, default=_default_lines(model["inputs"], "Input")
            )
        ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
        fields[vol.Required(CONF_ON_VOLUME, default=default_volume)] = vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        )
        fields[vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL)] = vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        )
        fields[vol.Required(CONF_UDP_TIMEOUT, default=DEFAULT_UDP_TIMEOUT)] = vol.All(
            vol.Coerce(float), vol.Range(min=0.25, max=5.0)
        )
        fields[vol.Optional(CONF_ENABLE_EQ, default=not is_matrix)] = bool
        return self.async_show_form(step_id="names", data_schema=vol.Schema(fields))

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
            schema[vol.Optional(CONF_SWITCH_ENTRY_ID)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=switches, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            schema[vol.Optional(CONF_SWITCH_FEEDS, default=DEFAULT_SWITCH_FEEDS)] = (
                selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            )
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
            packed = _extract_zones(user_input, model["zones"])
            if not packed.get(CONF_SWITCH_ENTRY_ID):
                packed[CONF_SWITCH_ENTRY_ID] = None
            return self.async_create_entry(title="", data=packed)

        default_volume = DEFAULT_SWITCH_ON_VOLUME if is_matrix else DEFAULT_ON_VOLUME
        stored = _stored_zone_map(self._entry.data, dict(self._entry.options), model["zones"])
        fields: dict[Any, Any] = {}
        fields.update(_zone_schema(model["zones"], stored))
        fields[
            vol.Required(
                CONF_SOURCE_NAMES,
                default=self._entry.options.get(
                    CONF_SOURCE_NAMES, self._entry.data.get(CONF_SOURCE_NAMES, "")
                ),
            )
        ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
        fields[
            vol.Required(
                CONF_ON_VOLUME,
                default=self._entry.options.get(
                    CONF_ON_VOLUME, self._entry.data.get(CONF_ON_VOLUME, default_volume)
                ),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
        fields[
            vol.Required(
                CONF_POLL_INTERVAL,
                default=self._entry.options.get(
                    CONF_POLL_INTERVAL,
                    self._entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=5, max=300))
        fields[
            vol.Required(
                CONF_UDP_TIMEOUT,
                default=self._entry.options.get(
                    CONF_UDP_TIMEOUT,
                    self._entry.data.get(CONF_UDP_TIMEOUT, DEFAULT_UDP_TIMEOUT),
                ),
            )
        ] = vol.All(vol.Coerce(float), vol.Range(min=0.25, max=5.0))
        if not is_matrix:
            fields[
                vol.Optional(
                    CONF_ENABLE_EQ,
                    default=self._entry.options.get(
                        CONF_ENABLE_EQ, self._entry.data.get(CONF_ENABLE_EQ, True)
                    ),
                )
            ] = bool
            switches = [selector.SelectOptionDict(value="", label="Not linked")] + [
                selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
                if MODELS.get(entry.data.get(CONF_MODEL), {}).get("kind") == "matrix"
            ]
            current_switch = self._entry.options.get(
                CONF_SWITCH_ENTRY_ID, self._entry.data.get(CONF_SWITCH_ENTRY_ID, "")
            ) or ""
            fields[vol.Optional(CONF_SWITCH_ENTRY_ID, default=current_switch)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=switches, mode=selector.SelectSelectorMode.DROPDOWN
                    )
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
