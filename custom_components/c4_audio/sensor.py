"""UDP activity sensor — last SET / unsolicited frames for the dashboard."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .coordinator import C4AudioCoordinator
from .entity_ids import entity_unique_id


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = entry.runtime_data
    async_add_entities([C4UdpActivitySensor(coordinator)])


class C4UdpActivitySensor(CoordinatorEntity[C4AudioCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "udp_activity"
    _attr_icon = "mdi:console-line"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_force_update = True
    # Twenty lines on every frame would fill the recorder.
    _unrecorded_attributes = frozenset({"activity"})

    def __init__(self, coordinator: C4AudioCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.entry, "udp_activity")
        self._attr_device_info = device_info_for(coordinator)

    @property
    def native_value(self) -> str:
        lines = self.coordinator.client.activity_lines
        if not lines:
            return "idle"
        return lines[-1][:255]

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        lines = self.coordinator.client.activity_lines
        return {"activity": "\n".join(lines) if lines else ""}
