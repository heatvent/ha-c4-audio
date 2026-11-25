"""Set up Control4 Audio."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from .const import CONF_IDENT, CONF_MODEL, DOMAIN, MODELS, PLATFORMS, REMOVED_OPTIONS
from .coordinator import C4AudioCoordinator, source_store
from .entity_ids import migrated_unique_id, stable_instance_id, unused_suffix

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_ROUTE = "set_route"
SERVICE_TURN_OFF_ALL = "turn_off_all"
SERVICE_TURN_ON_ALL = "turn_on_all"
ATTR_COMMAND = "command"
ATTR_OUTPUT = "output"
ATTR_INPUT = "input"


type C4AudioConfigEntry = ConfigEntry[C4AudioCoordinator]


def _coordinators(hass: HomeAssistant) -> list[C4AudioCoordinator]:
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and isinstance(getattr(entry, "runtime_data", None), C4AudioCoordinator)
    ]


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[C4AudioCoordinator]:
    """Chassis picked by device or host. Every loaded chassis when neither is given."""
    items = _coordinators(hass)
    host = call.data.get(CONF_HOST)
    device_ids = call.data.get(ATTR_DEVICE_ID)
    if not host and not device_ids:
        return items
    registry = dr.async_get(hass)
    wanted = set(device_ids or [])
    matched = [
        item
        for item in items
        if (host and item.host == host)
        or any(
            device.id in wanted
            for device in dr.async_entries_for_config_entry(registry, item.entry.entry_id)
        )
    ]
    if not matched:
        raise ServiceValidationError(f"No loaded Control4 Audio amp matches {call.service}")
    return matched


def _one_target(hass: HomeAssistant, call: ServiceCall) -> C4AudioCoordinator:
    """One chassis. A device (or host) is required when more than one entry is loaded."""
    matched = _targets(hass, call)
    if not matched:
        raise ServiceValidationError(f"No Control4 Audio amp is loaded for {call.service}")
    if len(matched) > 1:
        raise ServiceValidationError(
            f"{call.service} needs one device when more than one Control4 amp is configured"
        )
    return matched[0]


async def _run_on_all(
    hass: HomeAssistant,
    call: ServiceCall,
    action: Callable[[C4AudioCoordinator], Awaitable[None]],
) -> None:
    """Run on every target. One amp failing does not stop the next."""
    matched = _targets(hass, call)
    if not matched:
        _LOGGER.error("No Control4 Audio amp is loaded for %s", call.service)
        return
    errors: list[str] = []
    for coordinator in matched:
        try:
            await action(coordinator)
        except HomeAssistantError as err:
            errors.append(f"{coordinator.entry.title}: {err}")
    if errors:
        raise HomeAssistantError("; ".join(errors))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once, so automations validate even before an entry loads."""
    _register_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: C4AudioConfigEntry) -> bool:
    """Drop the audio switch link from amp entries made by 1.0.13 and earlier."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        hass.config_entries.async_update_entry(
            entry,
            data={key: val for key, val in entry.data.items() if key not in REMOVED_OPTIONS},
            options={key: val for key, val in entry.options.items() if key not in REMOVED_OPTIONS},
            minor_version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: C4AudioConfigEntry) -> bool:
    if entry.data.get(CONF_MODEL) not in MODELS:
        raise ConfigEntryError(
            f"{entry.title} is not a supported amplifier. The Control4 audio switch and the "
            "16-zone profile are no longer supported; delete this entry."
        )
    coordinator = C4AudioCoordinator(hass, entry)
    try:
        await coordinator.async_start()
    except OSError as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(f"Could not reach {coordinator.host}: {err}") from err
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await _async_migrate_entity_unique_ids(hass, entry)
    _remove_unused_entities(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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


@callback
def _remove_unused_entities(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: C4AudioCoordinator
) -> None:
    """Remove entities of zones whose name was cleared, and of switched-off experimental controls."""
    if not coordinator.enabled_zones:
        return
    registry = er.async_get(hass)
    prefix = f"{stable_instance_id(entry)}_"
    inputs = coordinator.enabled_inputs if coordinator.experimental_enabled else []
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.startswith(prefix) and unused_suffix(
            entity.unique_id[len(prefix) :],
            zones=coordinator.enabled_zones,
            inputs=inputs,
            balance=coordinator.experimental_enabled,
        ):
            registry.async_remove(entity.entity_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await source_store(hass, entry.entry_id).async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: C4AudioConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Close the socket only once every platform let go; otherwise entities stay live.
        await entry.runtime_data.async_shutdown()
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def handle_send_command(call: ServiceCall) -> None:
        command = call.data[ATTR_COMMAND]
        coordinator = _one_target(hass, call)
        reply = await coordinator.async_send_raw(command)
        if reply is None:
            raise HomeAssistantError(f"No reply from {coordinator.host} for {command}")
        _LOGGER.info("Raw command %s → %s", command, reply)

    async def handle_set_route(call: ServiceCall) -> None:
        coordinator = _one_target(hass, call)
        await coordinator.async_route_output(int(call.data[ATTR_OUTPUT]), int(call.data[ATTR_INPUT]))
        await coordinator.async_request_refresh()

    async def handle_turn_off_all(call: ServiceCall) -> None:
        await _run_on_all(hass, call, lambda item: item.async_turn_off_all())

    async def handle_turn_on_all(call: ServiceCall) -> None:
        await _run_on_all(hass, call, lambda item: item.async_turn_on_all())

    target = {
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        schema=vol.Schema(
            {
                vol.Required(ATTR_COMMAND): cv.string,
                **target,
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
                **target,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_OFF_ALL,
        handle_turn_off_all,
        schema=vol.Schema(target),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_ON_ALL,
        handle_turn_on_all,
        schema=vol.Schema(target),
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
