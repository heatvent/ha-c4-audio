"""Media player entities — one per enabled zone."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info_for
from .coordinator import C4AudioCoordinator
from .entity import adopt_zone_area
from .entity_ids import entity_unique_id


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: C4AudioCoordinator = entry.runtime_data
    async_add_entities(
        C4ZoneMediaPlayer(coordinator, zone) for zone in coordinator.enabled_zones
    )


class C4ZoneMediaPlayer(CoordinatorEntity[C4AudioCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "zone"
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: C4AudioCoordinator, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = entity_unique_id(coordinator.entry, f"zone_{zone}")
        self._attr_device_info = device_info_for(coordinator)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        adopt_zone_area(self.hass, self.coordinator, self.entity_id, self._zone)

    @property
    def name(self) -> str:
        return self.coordinator.zone_names[self._zone - 1]

    @property
    def source_list(self) -> list[str]:
        return self.coordinator.media_source_list()

    @property
    def _zone_state(self):
        return self.coordinator.state.zones[self._zone]

    @property
    def state(self) -> MediaPlayerState:
        zone = self._zone_state
        if zone.source <= 0:
            return MediaPlayerState.OFF
        if zone.muted:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def source(self) -> str | None:
        return self.coordinator.media_source_name(self._zone)

    @property
    def volume_level(self) -> float:
        if self._zone_state.source <= 0:
            return self.coordinator.on_volume(self._zone) / 100.0
        return self._zone_state.volume / 100.0

    @property
    def is_volume_muted(self) -> bool:
        return self._zone_state.muted

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "zone": self._zone,
            "host": self.coordinator.host,
            "model": self.coordinator.model_id,
            "input_index": self._zone_state.source,
            "firmware": self.coordinator.state.firmware,
        }

    async def async_turn_on(self) -> None:
        await self.coordinator.async_turn_on(self._zone)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_turn_off(self._zone)

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.async_select_source(self._zone, source)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_set_volume(self._zone, volume)

    async def async_volume_up(self) -> None:
        await self.coordinator.async_adjust_volume(self._zone, 1)

    async def async_volume_down(self) -> None:
        await self.coordinator.async_adjust_volume(self._zone, -1)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_set_mute(self._zone, mute)
