"""Optional bass/treble controls, and opt-in balance and input level."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .const import BALANCE_LIMIT, INPUT_GAIN_LIMIT
from .coordinator import C4AudioCoordinator
from .entity import adopt_zone_area
from .entity_ids import entity_unique_id

_LABELS = {"bass": "Bass", "treble": "Treble", "balance": "Balance"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = entry.runtime_data
    kinds = ["bass", "treble"] if coordinator.eq_enabled else []
    if coordinator.experimental_enabled:
        kinds.append("balance")
    entities: list[NumberEntity] = [
        C4ToneNumber(coordinator, zone, kind)
        for zone in coordinator.enabled_zones
        for kind in kinds
    ]
    if coordinator.experimental_enabled:
        entities.extend(
            C4InputGainNumber(coordinator, source) for source in coordinator.enabled_inputs
        )
    async_add_entities(entities)


class C4ToneNumber(CoordinatorEntity[C4AudioCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: C4AudioCoordinator, zone: int, kind: str) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._kind = kind
        limit = BALANCE_LIMIT if kind == "balance" else 12
        self._attr_native_min_value = -limit
        self._attr_native_max_value = limit
        self._attr_unique_id = entity_unique_id(coordinator.entry, f"zone_{zone}_{kind}")
        self._attr_device_info = device_info_for(coordinator)
        self._attr_translation_key = kind

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        adopt_zone_area(self.hass, self.coordinator, self.entity_id, self._zone)

    @property
    def name(self) -> str:
        return f"{self.coordinator.zone_names[self._zone - 1]} {_LABELS[self._kind]}"

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator.state.zones[self._zone], self._kind)

    async def async_set_native_value(self, value: float) -> None:
        setter = getattr(self.coordinator, f"async_set_{self._kind}")
        await setter(self._zone, int(value))


class C4InputGainNumber(CoordinatorEntity[C4AudioCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = -INPUT_GAIN_LIMIT
    _attr_native_max_value = INPUT_GAIN_LIMIT
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER
    _attr_translation_key = "input_gain"

    def __init__(self, coordinator: C4AudioCoordinator, source: int) -> None:
        super().__init__(coordinator)
        self._source = source
        self._attr_unique_id = entity_unique_id(coordinator.entry, f"input_{source}_gain")
        self._attr_device_info = device_info_for(coordinator)

    @property
    def name(self) -> str:
        return f"{self.coordinator.source_names[self._source - 1]} input level"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.state.input_gain.get(self._source)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_input_gain(self._source, int(value))
