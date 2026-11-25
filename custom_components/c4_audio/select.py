"""Source picker on the amp device (dropdown on the device page)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .coordinator import C4AudioCoordinator
from .entity import adopt_zone_area
from .entity_ids import entity_unique_id

SOURCE_OFF = "Off"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = entry.runtime_data
    async_add_entities(
        C4SourceSelect(coordinator, zone) for zone in coordinator.enabled_zones
    )


class C4SourceSelect(CoordinatorEntity[C4AudioCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "source"
    _attr_icon = "mdi:import"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: C4AudioCoordinator, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = entity_unique_id(coordinator.entry, f"zone_{zone}_source")
        self._attr_device_info = device_info_for(coordinator)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        adopt_zone_area(self.hass, self.coordinator, self.entity_id, self._zone)

    @property
    def name(self) -> str:
        return f"{self.coordinator.zone_names[self._zone - 1]} source"

    @property
    def options(self) -> list[str]:
        names = self.coordinator.media_source_list()
        current = self.coordinator.media_source_name(self._zone)
        if current and current not in names:
            # Control4 can route a zone to an input that has no name here.
            names = [*names, current]
        return [SOURCE_OFF, *names]

    @property
    def current_option(self) -> str:
        return self.coordinator.media_source_name(self._zone) or SOURCE_OFF

    async def async_select_option(self, option: str) -> None:
        if option == SOURCE_OFF:
            await self.coordinator.async_turn_off(self._zone)
            return
        await self.coordinator.async_select_source(self._zone, option)
