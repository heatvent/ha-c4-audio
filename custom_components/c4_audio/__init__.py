"""Set up Control4 Audio."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, MODELS, PLATFORMS
from .coordinator import C4AudioCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_ROUTE = "set_route"
SERVICE_TURN_OFF_ALL = "turn_off_all"
ATTR_COMMAND = "command"
ATTR_OUTPUT = "output"
ATTR_INPUT = "input"


def _coordinators(hass: HomeAssistant) -> list[C4AudioCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _match(hass: HomeAssistant, host: str | None) -> list[C4AudioCoordinator]:
    items = _coordinators(hass)
    if host:
        items = [item for item in items if item.host == host]
    return items


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    coordinator = C4AudioCoordinator(hass, entry)
    await coordinator.async_start()
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(str(err)) from err
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator: C4AudioCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_shutdown()
    if unload_ok and not hass.data[DOMAIN]:
        for service in (SERVICE_SEND_COMMAND, SERVICE_SET_ROUTE, SERVICE_TURN_OFF_ALL):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def handle_send_command(call: ServiceCall) -> None:
        command = call.data[ATTR_COMMAND]
        matched = _match(hass, call.data.get(CONF_HOST))
        if not matched:
            _LOGGER.error("No Control4 Audio device matched for send_command")
            return
        reply = await matched[0].async_send_raw(command)
        _LOGGER.info("Raw command %s → %s", command, reply)

    async def handle_set_route(call: ServiceCall) -> None:
        matched = _match(hass, call.data.get(CONF_HOST))
        if not matched:
            _LOGGER.error("No Control4 Audio device matched for set_route")
            return
        await matched[0].async_route_output(int(call.data[ATTR_OUTPUT]), int(call.data[ATTR_INPUT]))
        await matched[0].async_request_refresh()

    async def handle_turn_off_all(call: ServiceCall) -> None:
        matched = _match(hass, call.data.get(CONF_HOST))
        if not matched:
            _LOGGER.error("No Control4 Audio device matched for turn_off_all")
            return
        for coordinator in matched:
            await coordinator.async_turn_off_all()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        schema=vol.Schema(
            {
                vol.Required(ATTR_COMMAND): cv.string,
                vol.Optional(CONF_HOST): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ROUTE,
        handle_set_route,
        schema=vol.Schema(
            {
                vol.Required(ATTR_OUTPUT): vol.Coerce(int),
                vol.Required(ATTR_INPUT): vol.Coerce(int),
                vol.Optional(CONF_HOST): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_OFF_ALL,
        handle_turn_off_all,
        schema=vol.Schema({vol.Optional(CONF_HOST): cv.string}),
    )


def device_info_for(coordinator: C4AudioCoordinator) -> DeviceInfo:
    model = MODELS[coordinator.model_id]
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.host)},
        name=coordinator.entry.title,
        manufacturer="Control4",
        model=model["name"],
        sw_version=coordinator.state.firmware,
        configuration_url=None,
    )
