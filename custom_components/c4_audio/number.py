"""Optional bass/treble controls."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    if not coordinator.eq_enabled:
        return
    entities: list[NumberEntity] = []
    for zone in coordinator.enabled_zones:
        entities.append(C4ToneNumber(coordinator, zone, "bass"))
        entities.append(C4ToneNumber(coordinator, zone, "treble"))
    async_add_entities(entities)


class C4ToneNumber(CoordinatorEntity[C4AudioCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_native_min_value = -12
    _attr_native_max_value = 12
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: C4AudioCoordinator, zone: int, kind: str) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._kind = kind
        self._attr_unique_id = f"{coordinator.host}_zone_{zone}_{kind}"
        self._attr_device_info = device_info_for(coordinator)
        self._attr_translation_key = kind

    @property
    def name(self) -> str:
        zone_name = self.coordinator.zone_names[self._zone - 1]
        label = "Bass" if self._kind == "bass" else "Treble"
        return f"{zone_name} {label}"

    @property
    def native_value(self) -> float:
        zone = self.coordinator.state.zones[self._zone]
        return zone.bass if self._kind == "bass" else zone.treble

    async def async_set_native_value(self, value: float) -> None:
        db = int(value)
        if self._kind == "bass":
            await self.coordinator.async_set_bass(self._zone, db)
        else:
            await self.coordinator.async_set_treble(self._zone, db)
