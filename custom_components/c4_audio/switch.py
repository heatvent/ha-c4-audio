"""Whole-chassis on/off for Alexa and automations."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .const import DOMAIN
from .coordinator import C4AudioCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([C4AllZonesSwitch(coordinator)])


class C4AllZonesSwitch(CoordinatorEntity[C4AudioCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "all_zones"
    _attr_icon = "mdi:speaker-multiple"

    def __init__(self, coordinator: C4AudioCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_all_zones"
        self._attr_device_info = device_info_for(coordinator)

    @property
    def is_on(self) -> bool:
        return any(self.coordinator.zone_is_on(zone) for zone in self.coordinator.enabled_zones)

    async def async_turn_on(self, **kwargs) -> None:  # noqa: ANN003
        await self.coordinator.async_turn_on_all()

    async def async_turn_off(self, **kwargs) -> None:  # noqa: ANN003
        await self.coordinator.async_turn_off_all()
