"""Set up Control4 Audio."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_IDENT, DOMAIN, MODELS, PLATFORMS
from .coordinator import C4AudioCoordinator
from .entity_ids import migrated_unique_id, stable_instance_id

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_ROUTE = "set_route"
SERVICE_TURN_OFF_ALL = "turn_off_all"
SERVICE_TURN_ON_ALL = "turn_on_all"
ATTR_COMMAND = "command"
ATTR_OUTPUT = "output"
ATTR_INPUT = "input"


def _coordinators(hass: HomeAssistant) -> list[C4AudioCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _match(hass: HomeAssistant, host: str | None, *, amps_only: bool = False) -> list[C4AudioCoordinator]:
    items = _coordinators(hass)
    if host:
        items = [item for item in items if item.host == host]
    elif amps_only:
        items = [item for item in items if not item.is_matrix]
    return items


def _one_device(hass: HomeAssistant, host: str | None, service: str) -> C4AudioCoordinator:
    """One chassis. host is required when more than one entry is loaded."""
    matched = _match(hass, host)
    if not matched:
        raise HomeAssistantError(f"No Control4 Audio device matched for {service}")
    if not host and len(matched) > 1:
        raise HomeAssistantError(
            f"{service} needs host when more than one Control4 Audio chassis is configured"
        )
    return matched[0]


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
    await _async_migrate_entity_unique_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_migrate_entity_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rewrite IP-based unique IDs so a DHCP change does not orphan entities."""
    stable = stable_instance_id(entry)
    host = entry.data.get(CONF_HOST)
    registry = er.async_get(hass)
    updates: dict[str, str] = {}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        new_id = migrated_unique_id(entity.unique_id, stable_id=stable, host=host)
        if not new_id:
            continue
        existing = registry.async_get_entity_id(entity.domain, DOMAIN, new_id)
        if existing and existing != entity.entity_id:
            registry.async_remove(entity.entity_id)
            continue
        updates[entity.entity_id] = new_id

    if not updates:
        return

    @callback
    def _migrator(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
        new_id = updates.get(entity_entry.entity_id)
        if not new_id:
            return None
        return {"new_unique_id": new_id}

    await er.async_migrate_entries(hass, entry.entry_id, _migrator)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator: C4AudioCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_shutdown()
    if unload_ok and not hass.data[DOMAIN]:
        for service in (SERVICE_SEND_COMMAND, SERVICE_SET_ROUTE, SERVICE_TURN_OFF_ALL, SERVICE_TURN_ON_ALL):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def handle_send_command(call: ServiceCall) -> None:
        command = call.data[ATTR_COMMAND]
        coordinator = _one_device(hass, call.data.get(CONF_HOST), SERVICE_SEND_COMMAND)
        reply = await coordinator.async_send_raw(command)
        if reply is None:
            raise HomeAssistantError(f"No reply from {coordinator.host} for {command}")
        _LOGGER.info("Raw command %s → %s", command, reply)

    async def handle_set_route(call: ServiceCall) -> None:
        coordinator = _one_device(hass, call.data.get(CONF_HOST), SERVICE_SET_ROUTE)
        await coordinator.async_route_output(int(call.data[ATTR_OUTPUT]), int(call.data[ATTR_INPUT]))
        await coordinator.async_request_refresh()

    async def handle_turn_off_all(call: ServiceCall) -> None:
        matched = _match(hass, call.data.get(CONF_HOST), amps_only=True)
        if not matched:
            _LOGGER.error("No Control4 Audio device matched for turn_off_all")
            return
        for coordinator in matched:
            await coordinator.async_turn_off_all()

    async def handle_turn_on_all(call: ServiceCall) -> None:
        matched = _match(hass, call.data.get(CONF_HOST), amps_only=True)
        if not matched:
            _LOGGER.error("No Control4 Audio device matched for turn_on_all")
            return
        for coordinator in matched:
            await coordinator.async_turn_on_all()

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_ON_ALL,
        handle_turn_on_all,
        schema=vol.Schema({vol.Optional(CONF_HOST): cv.string}),
    )


def device_info_for(coordinator: C4AudioCoordinator) -> DeviceInfo:
    model = MODELS[coordinator.model_id]
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.entry.data.get(CONF_IDENT, coordinator.host))},
        name=coordinator.entry.title,
        manufacturer="Control4",
        model=model["name"],
        sw_version=coordinator.state.firmware,
        serial_number=coordinator.entry.data.get(CONF_IDENT),
        configuration_url=None,
    )
