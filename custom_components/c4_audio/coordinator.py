"""Data coordinator for a Control4 amp."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ACTIVE_POLL_INTERVAL,
    CONF_ENABLE_EQ,
    CONF_EXPERIMENTAL,
    CONF_MAX_VOLUME,
    CONF_MODEL,
    CONF_ON_VOLUME,
    CONF_POLL_INTERVAL,
    CONF_REMEMBER_SOURCE,
    CONF_SOURCE_NAMES,
    CONF_UDP_TIMEOUT,
    CONF_ZONE_NAMES,
    CONF_ZONES,
    DEFAULT_ACTIVE_POLL_INTERVAL,
    DEFAULT_MAX_VOLUME,
    DEFAULT_ON_VOLUME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_UDP_TIMEOUT,
    DOMAIN,
    EVENT_EXTERNAL_CHANGE,
    GET_RETRIES,
    MAX_FAILED_POLLS,
    MAX_FAILED_ZONES,
    MODELS,
    REJECTED,
    SET_RETRIES,
    VOLUME_INTERVAL_S,
)
from .entity_ids import entity_unique_id
from .protocol import (
    AmpCommands,
    ParsedPacket,
    from_hex_byte,
    hex_to_signed,
    hex_to_signed_gain,
    parse_hex_list,
    split_user_command,
)
from .routing import (
    clamp_volume,
    displayed_source,
    enabled_indexes,
    ha_volume_to_percent,
    parse_zone_map,
    resolve_source_choice,
    split_names,
    visible_names,
    volume_reading_is_stale,
)
from .udp_client import C4UdpClient

_LOGGER = logging.getLogger(__name__)

# Ignore GET avol that still shows the old 100% for a moment after we write chvol.
_VOLUME_HOLD_S = 2.5
# A change this soon after one of our own commands is not reported as an outside change.
_OWN_CHANGE_S = 5.0
_STORAGE_VERSION = 1
_SAVE_DELAY_S = 5.0


@dataclass
class ZoneState:
    source: int = 0
    volume: int = 0
    muted: bool = False
    bass: int = 0
    treble: int = 0
    balance: int = 0


@dataclass
class DeviceState:
    firmware: str | None = None
    available: bool = False
    zones: dict[int, ZoneState] = field(default_factory=dict)
    input_gain: dict[int, int] = field(default_factory=dict)


def source_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, int]]:
    """Last source of each zone, kept across restarts."""
    return Store(hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


class C4AudioCoordinator(DataUpdateCoordinator[DeviceState]):
    """Poll GET commands and apply unsolicited 0t status frames."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        model_id = entry.data[CONF_MODEL]
        self.model = MODELS[model_id]
        self.model_id = model_id
        self.zone_count = self.model["zones"]
        self.input_count = self.model["inputs"]
        self._poll_interval = int(self._option(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
        self._active_poll_interval = min(
            self._poll_interval,
            int(self._option(CONF_ACTIVE_POLL_INTERVAL, DEFAULT_ACTIVE_POLL_INTERVAL)),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=self._poll_interval),
        )
        timeout = float(self._option(CONF_UDP_TIMEOUT, DEFAULT_UDP_TIMEOUT))
        self.cmds = AmpCommands()
        self.client = C4UdpClient(entry.data[CONF_HOST], int(entry.data[CONF_PORT]), timeout)
        self.client.add_listener(self._on_packet)
        self.client.add_activity_listener(self._on_udp_activity)
        self.state = DeviceState(
            zones={index: ZoneState() for index in range(1, self.zone_count + 1)}
        )
        self._last_commanded_volume: dict[int, tuple[float, int]] = {}
        self._failed_polls = 0
        self._last_full_poll: float | None = None
        # Outside changes are reported only once the first poll has set a baseline.
        self._baseline = False
        self._commanding: dict[int, int] = {}
        self._commanded_at: dict[int, float] = {}
        self._external: dict[int, dict[str, Any]] = {}
        self._volume_target: dict[int, int] = {}
        self._volume_sent_at: dict[int, float] = {}
        self._volume_locks = {zone: asyncio.Lock() for zone in self.state.zones}
        self._last_source: dict[int, int] = {}
        self._store = source_store(hass, entry.entry_id)

    def _option(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    # ------------------------------------------------------------- settings

    @property
    def zone_map(self) -> dict[int, dict[str, Any]]:
        return parse_zone_map(
            self._option(CONF_ZONES, None),
            self.zone_count,
            self._option(CONF_ZONE_NAMES, None),
        )

    @property
    def zone_names(self) -> list[str]:
        mapping = self.zone_map
        return [str(mapping[index]["name"] or "") for index in range(1, self.zone_count + 1)]

    def zone_area_id(self, zone: int) -> str | None:
        area = self.zone_map.get(zone, {}).get("area_id")
        return str(area) if area else None

    @property
    def source_names(self) -> list[str]:
        return split_names(self._option(CONF_SOURCE_NAMES, None), self.input_count, "Input")

    @property
    def enabled_zones(self) -> list[int]:
        return enabled_indexes(self.zone_names)

    @property
    def enabled_inputs(self) -> list[int]:
        return enabled_indexes(self.source_names)

    def on_volume(self, zone: int) -> int:
        """Turn-on volume: the zone's own, else the amp's."""
        volume = self.zone_map[zone]["on_volume"]
        if volume is None:
            volume = int(self.entry.options.get(CONF_ON_VOLUME, DEFAULT_ON_VOLUME))
        return clamp_volume(volume, self.max_volume)

    @property
    def max_volume(self) -> int:
        return clamp_volume(int(self._option(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME)), 100)

    @property
    def eq_enabled(self) -> bool:
        return bool(self._option(CONF_ENABLE_EQ, True))

    @property
    def experimental_enabled(self) -> bool:
        return bool(self._option(CONF_EXPERIMENTAL, False))

    @property
    def host(self) -> str:
        return self.entry.data[CONF_HOST]

    def media_source_list(self) -> list[str]:
        return visible_names(self.source_names)

    def media_source_name(self, zone: int) -> str | None:
        return displayed_source(self.state.zones[zone].source, self.source_names)

    def default_source_index(self, zone: int) -> int:
        """Input to use when a zone is turned on with no current route."""
        enabled = self.enabled_inputs
        if self._option(CONF_REMEMBER_SOURCE, True):
            last = self._last_source.get(zone)
            if last in enabled:
                return last
        return enabled[0] if enabled else 1

    def zone_is_on(self, zone: int) -> bool:
        return self.state.zones[zone].source > 0

    # ------------------------------------------------------------- lifecycle

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self._last_source = {
            int(zone): int(source) for zone, source in stored.items() if str(zone).isdigit()
        }
        await self.client.async_start()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.async_stop()

    # ------------------------------------------------------------- commands

    def _check_output(self, zone: int, source: int | None = None) -> None:
        if zone not in self.state.zones:
            raise HomeAssistantError(
                f"Output {zone} is out of range for {self.host} (1-{self.zone_count})"
            )
        if source is not None and (source < 0 or source > self.input_count):
            raise HomeAssistantError(
                f"Input {source} is out of range for {self.host} (0-{self.input_count})"
            )

    @contextmanager
    def _own_change(self, zone: int) -> Iterator[None]:
        """Changes to this zone are ours while the block runs, and shortly after."""
        self._commanding[zone] = self._commanding.get(zone, 0) + 1
        try:
            yield
        finally:
            self._commanding[zone] -= 1
            self._commanded_at[zone] = time.monotonic()

    def _is_own_change(self, zone: int) -> bool:
        if self._commanding.get(zone):
            return True
        commanded_at = self._commanded_at.get(zone)
        return commanded_at is not None and time.monotonic() - commanded_at < _OWN_CHANGE_S

    async def _async_require_send(self, command: tuple[str, str]) -> ParsedPacket:
        packet = await self.client.async_send(*command, retries=SET_RETRIES)
        if packet is None:
            raise HomeAssistantError(f"No reply from {self.host} for {command[1]}")
        if packet.status_code in REJECTED:
            raise HomeAssistantError(
                f"{self.host} rejected {command[1]} ({packet.status_code})"
            )
        return packet

    async def _async_wake(self) -> None:
        # Best effort: a model without power save answers n01.
        if self.model["wake_power_save"]:
            await self.client.async_send(*self.cmds.set_power_save("00"), retries=SET_RETRIES)

    async def async_send_raw(self, body: str) -> str | None:
        prefix, command = split_user_command(body)
        packet = await self.client.async_send(prefix, command)
        return packet.raw if packet else None

    def _volume_is_stale(self, zone: int, decoded: int) -> bool:
        last = self._last_commanded_volume.get(zone)
        if last is None:
            return False
        return volume_reading_is_stale(
            now=time.monotonic(),
            commanded_at=last[0],
            commanded=last[1],
            decoded=decoded,
            hold_s=_VOLUME_HOLD_S,
        )

    def _read_volume(self, zone: int, value: int) -> int:
        decoded = self.cmds.decode_volume(f"{value:02x}")
        last = self._last_commanded_volume.get(zone)
        if decoded == 1 and last is not None and last[1] == 0:
            # The C4-8AMP1-B stores 0% as 1%.
            return 0
        return decoded

    def _remember_volume(self, zone: int, percent: int) -> None:
        self._last_commanded_volume[zone] = (time.monotonic(), percent)

    def _note_source(self, zone: int, source: int) -> None:
        if source <= 0 or self._last_source.get(zone) == source:
            return
        self._last_source[zone] = source
        self._store.async_delay_save(
            lambda: {str(key): value for key, value in self._last_source.items()}, _SAVE_DELAY_S
        )

    async def _async_send_volume(self, zone: int, percent: int) -> None:
        await self._async_require_send(self.cmds.set_volume(zone, percent))
        self._volume_sent_at[zone] = time.monotonic()
        self.state.zones[zone].volume = percent
        self._remember_volume(zone, percent)

    async def _async_unmute(self, zone: int) -> None:
        await self._async_require_send(self.cmds.set_mute(zone, False))
        self.state.zones[zone].muted = False

    async def _async_power_up(self, zone: int, source: int, volume: int, *, wake: bool) -> None:
        """Route while muted, set the volume, then unmute."""
        if wake:
            await self._async_wake()
        await self.async_route_output(zone, source, unmute=False)
        await self._async_send_volume(zone, volume)
        await self._async_unmute(zone)
        self.async_set_updated_data(self.state)

    async def async_select_source(self, zone: int, source_name: str) -> None:
        self._check_output(zone)
        try:
            source = resolve_source_choice(source_name, self.source_names)
        except ValueError as err:
            raise HomeAssistantError(f"Unknown source {source_name}") from err
        with self._own_change(zone):
            if self.zone_is_on(zone):
                await self.async_route_output(zone, source)
            else:
                await self._async_power_up(zone, source, self.on_volume(zone), wake=True)
        await self._async_confirm()

    async def async_route_output(self, zone: int, source: int, *, unmute: bool = True) -> None:
        self._check_output(zone, source)
        with self._own_change(zone):
            if source > 0 and self.model["digital_inputs"]:
                # Control4 asks this before routing. The answer is not needed.
                await self.client.async_send(*self.cmds.get_digital(source))
            await self._async_require_send(self.cmds.set_output(zone, source))
            self.state.zones[zone].source = source
            self._note_source(zone, source)
            if source > 0 and unmute:
                await self._async_unmute(zone)
            self.async_set_updated_data(self.state)

    async def async_turn_on(
        self,
        zone: int,
        *,
        confirm: bool = True,
        volume: int | None = None,
        wake: bool = True,
    ) -> None:
        self._check_output(zone)
        with self._own_change(zone):
            if self.zone_is_on(zone):
                if self.state.zones[zone].muted:
                    await self._async_unmute(zone)
                    self.async_set_updated_data(self.state)
            else:
                percent = (
                    self.on_volume(zone)
                    if volume is None
                    else clamp_volume(int(volume), self.max_volume)
                )
                await self._async_power_up(
                    zone, self.default_source_index(zone), percent, wake=wake
                )
        if confirm:
            await self._async_confirm()

    async def async_turn_off(self, zone: int, *, confirm: bool = True) -> None:
        self._check_output(zone)
        self._volume_target.pop(zone, None)
        with self._own_change(zone):
            await self._async_require_send(self.cmds.set_mute(zone, True))
            await self._async_require_send(self.cmds.set_output(zone, 0))
            # Never send chvolmax here. 16AMP3 firmware snaps live volume to the cap.
            self.state.zones[zone].source = 0
            self.state.zones[zone].muted = True
            self.async_set_updated_data(self.state)
        if confirm:
            await self._async_confirm()

    async def _async_all_zones(
        self, action: str, command: Callable[[int], Awaitable[None]]
    ) -> None:
        """Run a command on every zone. One failure does not stop the others."""
        failed: list[str] = []
        in_a_row = 0
        last_error: HomeAssistantError | None = None
        zones = self.enabled_zones
        for position, zone in enumerate(zones):
            try:
                await command(zone)
                in_a_row = 0
            except HomeAssistantError as err:
                last_error = err
                failed.append(self.zone_names[zone - 1])
                in_a_row += 1
                if in_a_row >= MAX_FAILED_ZONES:
                    # The chassis is not answering; do not wait out every zone.
                    failed.extend(self.zone_names[rest - 1] for rest in zones[position + 1 :])
                    break
        await self._async_confirm()
        if last_error is not None:
            raise HomeAssistantError(
                f"{action} failed for {', '.join(failed)}: {last_error}"
            ) from last_error

    async def async_turn_on_all(self) -> None:
        if any(not self.zone_is_on(zone) for zone in self.enabled_zones):
            await self._async_wake()
        await self._async_all_zones(
            "All on", lambda zone: self.async_turn_on(zone, confirm=False, wake=False)
        )

    async def async_turn_off_all(self) -> None:
        await self._async_all_zones(
            "All off", lambda zone: self.async_turn_off(zone, confirm=False)
        )

    async def async_set_volume(self, zone: int, volume: float, *, as_percent: bool = False) -> None:
        self._check_output(zone)
        percent = clamp_volume(ha_volume_to_percent(volume, as_percent=as_percent), self.max_volume)
        if not self.zone_is_on(zone):
            await self.async_turn_on(zone, volume=percent)
            return
        # Latest wins: a fast slider drag sends one step per interval, not every step.
        self._volume_target[zone] = percent
        with self._own_change(zone):
            async with self._volume_locks[zone]:
                if zone not in self._volume_target:
                    return  # An earlier call in the queue already sent this value.
                wait = self._volume_sent_at.get(zone, 0.0) + VOLUME_INTERVAL_S - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                target = self._volume_target.pop(zone, None)
                if target is None or not self.zone_is_on(zone):
                    return  # Turned off meanwhile.
                await self._async_send_volume(zone, target)
                if target > 0 and self.state.zones[zone].muted:
                    await self._async_unmute(zone)
                self.async_set_updated_data(self.state)

    async def async_adjust_volume(self, zone: int, delta: int) -> None:
        self._check_output(zone)
        if not self.zone_is_on(zone):
            current = self.on_volume(zone)
        else:
            current = self._volume_target.get(zone, self.state.zones[zone].volume)
        await self.async_set_volume(zone, current + delta, as_percent=True)

    async def async_set_mute(self, zone: int, muted: bool) -> None:
        self._check_output(zone)
        with self._own_change(zone):
            await self._async_require_send(self.cmds.set_mute(zone, muted))
            self.state.zones[zone].muted = muted
            self.async_set_updated_data(self.state)

    async def async_set_bass(self, zone: int, db: int) -> None:
        self._check_output(zone)
        await self._async_require_send(self.cmds.set_bass(zone, db))
        self.state.zones[zone].bass = db
        self.async_set_updated_data(self.state)

    async def async_set_treble(self, zone: int, db: int) -> None:
        self._check_output(zone)
        await self._async_require_send(self.cmds.set_treble(zone, db))
        self.state.zones[zone].treble = db
        self.async_set_updated_data(self.state)

    async def async_set_balance(self, zone: int, value: int) -> None:
        """Experimental. Read back, because it is not confirmed on every model."""
        self._check_output(zone)
        await self._async_require_send(self.cmds.set_balance(zone, value))
        await self._async_poll_list(self.cmds.get_balance(), self._apply_balance, required=False)
        self.async_set_updated_data(self.state)
        if self.state.zones[zone].balance != value:
            raise HomeAssistantError(f"{self.host} did not change the balance of zone {zone}")

    async def async_set_input_gain(self, source: int, db: int) -> None:
        """Experimental. Read back, because it is not confirmed on every model."""
        await self._async_require_send(self.cmds.set_input_gain(source, db))
        await self._async_read_input_gain(source)
        self.async_set_updated_data(self.state)
        if self.state.input_gain.get(source) != db:
            raise HomeAssistantError(f"{self.host} did not change the level of input {source}")

    async def _async_confirm(self) -> None:
        """Re-read this chassis."""
        await self.async_request_refresh()

    # ------------------------------------------------------------- polling

    async def _async_update_data(self) -> DeviceState:
        try:
            await self._async_poll()
        except UpdateFailed:
            self._failed_polls += 1
            if self._baseline and self._failed_polls < MAX_FAILED_POLLS:
                _LOGGER.debug(
                    "Missed poll %s of %s from %s; keeping the last state",
                    self._failed_polls,
                    MAX_FAILED_POLLS,
                    self.host,
                )
                return self.state
            self.state.available = False
            raise
        self._failed_polls = 0
        self.state.available = True
        self._fire_external_changes()
        self._baseline = True
        playing = any(zone.source > 0 for zone in self.state.zones.values())
        self.update_interval = timedelta(
            seconds=self._active_poll_interval if playing else self._poll_interval
        )
        return self.state

    async def _async_poll(self) -> None:
        now = time.monotonic()
        full = (
            self._last_full_poll is None
            or self.state.firmware is None
            or now - self._last_full_poll >= self._poll_interval - 0.5
        )
        await self._async_poll_list(self.cmds.get_inputs(), self._apply_sources, required=True)
        await self._async_poll_list(self.cmds.get_volumes(), self._apply_volumes, required=True)
        await self._async_poll_list(self.cmds.get_mutes(), self._apply_mutes, required=True)
        if not full:
            return
        # Slow-changing values: at the normal interval, even while music plays.
        firmware = await self._async_get(self.cmds.get_firmware())
        if firmware is not None and firmware.args:
            self.state.firmware = firmware.args[0].strip('"')
        if self.eq_enabled:
            await self._async_poll_list(self.cmds.get_bass(), self._apply_bass, required=False)
            await self._async_poll_list(self.cmds.get_treble(), self._apply_treble, required=False)
        if self.experimental_enabled:
            await self._async_poll_list(
                self.cmds.get_balance(), self._apply_balance, required=False
            )
            for source in self.enabled_inputs:
                await self._async_read_input_gain(source)
        self._last_full_poll = now

    async def _async_get(self, command: tuple[str, str]) -> ParsedPacket | None:
        return await self.client.async_send(*command, retries=GET_RETRIES)

    async def _async_poll_list(
        self,
        command: tuple[str, str],
        apply: Callable[[list[int | None]], None],
        *,
        required: bool,
    ) -> None:
        packet = await self._async_get(command)
        if packet is None:
            if required:
                raise UpdateFailed(f"No reply from {self.host} for {command[1]}")
            return
        if packet.status_code in REJECTED:
            return
        apply(parse_hex_list(packet.args))

    async def _async_read_input_gain(self, source: int) -> None:
        packet = await self._async_get(self.cmds.get_input_gain(source))
        if packet is None or packet.status_code in REJECTED or len(packet.args) < 2:
            return
        self.state.input_gain[source] = hex_to_signed(packet.args[1])

    def _observe(self, zone: int, name: str, value: Any) -> None:
        """Store a value read from the chassis, and note it when we did not cause it."""
        state = self.state.zones[zone]
        old = getattr(state, name)
        if name == "source":
            self._note_source(zone, value)
        if old == value:
            return
        setattr(state, name, value)
        if self._baseline and not self._is_own_change(zone):
            self._external.setdefault(zone, {}).setdefault(name, old)

    def _fire_external_changes(self) -> None:
        changes, self._external = self._external, {}
        for zone, previous in changes.items():
            state = self.state.zones[zone]
            previous = {
                name: old for name, old in previous.items() if old != getattr(state, name)
            }
            if not previous:
                continue
            self.hass.bus.async_fire(
                EVENT_EXTERNAL_CHANGE,
                {
                    ATTR_ENTITY_ID: er.async_get(self.hass).async_get_entity_id(
                        "media_player", DOMAIN, entity_unique_id(self.entry, f"zone_{zone}")
                    ),
                    "config_entry_id": self.entry.entry_id,
                    "zone": zone,
                    "zone_name": self.zone_names[zone - 1] or f"Zone {zone}",
                    "changed": sorted(previous),
                    "previous": previous,
                    "source": state.source,
                    "source_name": self.media_source_name(zone),
                    "volume": state.volume,
                    "muted": state.muted,
                },
            )

    def _zone_values(self, values: list[int | None]) -> Iterator[tuple[int, int]]:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is not None:
                yield index, value

    def _apply_sources(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            self._observe(zone, "source", value)

    def _apply_volumes(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            decoded = self._read_volume(zone, value)
            if not self._volume_is_stale(zone, decoded):
                self._observe(zone, "volume", decoded)

    def _apply_mutes(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            self._observe(zone, "muted", bool(value))

    def _apply_bass(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            self.state.zones[zone].bass = hex_to_signed_gain(f"{value:02x}")

    def _apply_treble(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            self.state.zones[zone].treble = hex_to_signed_gain(f"{value:02x}")

    def _apply_balance(self, values: list[int | None]) -> None:
        for zone, value in self._zone_values(values):
            self.state.zones[zone].balance = hex_to_signed(f"{value:02x}")

    @callback
    def _on_udp_activity(self) -> None:
        # async_update_listeners, not async_set_updated_data: the latter reschedules the
        # poll, so a chatty chassis would keep pushing the next full GET back forever.
        self.async_update_listeners()

    @callback
    def _on_packet(self, packet: ParsedPacket) -> None:
        if packet.kind != "status" or not packet.command or len(packet.args) < 2:
            return
        cmd = packet.command
        zone = from_hex_byte(packet.args[0])
        if zone not in self.state.zones:
            return
        if cmd == f"{self.cmds.ns}.out":
            self._observe(zone, "source", from_hex_byte(packet.args[1]))
        elif cmd == f"{self.cmds.ns}.mute":
            self._observe(zone, "muted", from_hex_byte(packet.args[1]) == 1)
        elif cmd in {f"{self.cmds.ns}.chvol", f"{self.cmds.ns}.vol"}:
            decoded = self._read_volume(zone, from_hex_byte(packet.args[1]))
            if self._volume_is_stale(zone, decoded):
                return
            self._observe(zone, "volume", decoded)
            self._remember_volume(zone, decoded)
        else:
            return
        self._fire_external_changes()
        self.async_update_listeners()
