"""Data coordinator for a Control4 amp or matrix switch."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ENABLE_EQ,
    CONF_MODEL,
    CONF_ON_VOLUME,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_NAMES,
    CONF_SWITCH_ENTRY_ID,
    CONF_SWITCH_FEEDS,
    CONF_UDP_TIMEOUT,
    CONF_ZONE_NAMES,
    DEFAULT_ON_VOLUME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SWITCH_FEEDS,
    DEFAULT_SWITCH_ON_VOLUME,
    DEFAULT_UDP_TIMEOUT,
    DOMAIN,
    MODELS,
)
from .protocol import (
    DeviceCommands,
    ParsedPacket,
    from_hex_byte,
    hex_to_signed_gain,
    parse_hex_list,
)
from .routing import (
    KIND_SWITCH,
    displayed_amp_source,
    enabled_indexes,
    merged_source_list,
    parse_feeds,
    resolve_source_choice,
    split_names,
    visible_names,
)
from .udp_client import C4UdpClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZoneState:
    source: int = 0
    volume: int = 0
    muted: bool = False
    bass: int = 0
    treble: int = 0


@dataclass
class DeviceState:
    firmware: str | None = None
    available: bool = False
    zones: dict[int, ZoneState] = field(default_factory=dict)


class C4AudioCoordinator(DataUpdateCoordinator[DeviceState]):
    """Poll GET commands and apply unsolicited 0t status frames."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        model_id = entry.data[CONF_MODEL]
        self.model = MODELS[model_id]
        self.model_id = model_id
        self.zone_count = self.model["zones"]
        self.input_count = self.model["inputs"]
        poll = entry.options.get(
            CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=int(poll)),
        )
        timeout = float(
            entry.options.get(
                CONF_UDP_TIMEOUT, entry.data.get(CONF_UDP_TIMEOUT, DEFAULT_UDP_TIMEOUT)
            )
        )
        self.cmds = DeviceCommands(
            self.model.get("cmd_ns", "c4.amp"),
            self.model.get("volume_set", "chvol"),
            self.model.get("volume_mode", "offset"),
        )
        self.is_matrix = self.model.get("kind") == "matrix"
        self.client = C4UdpClient(entry.data[CONF_HOST], int(entry.data[CONF_PORT]), timeout)
        self.client.add_listener(self._on_packet)
        self.state = DeviceState(
            zones={index: ZoneState() for index in range(1, self.zone_count + 1)}
        )

    @property
    def zone_names(self) -> list[str]:
        return split_names(
            self.entry.options.get(CONF_ZONE_NAMES, self.entry.data.get(CONF_ZONE_NAMES)),
            self.zone_count,
            "Zone",
        )

    @property
    def source_names(self) -> list[str]:
        return split_names(
            self.entry.options.get(CONF_SOURCE_NAMES, self.entry.data.get(CONF_SOURCE_NAMES)),
            self.input_count,
            "Input",
        )

    @property
    def enabled_zones(self) -> list[int]:
        return enabled_indexes(self.zone_names)

    @property
    def switch_feeds(self) -> dict[int, int]:
        return parse_feeds(
            self.entry.options.get(
                CONF_SWITCH_FEEDS,
                self.entry.data.get(CONF_SWITCH_FEEDS, DEFAULT_SWITCH_FEEDS),
            )
        )

    @property
    def on_volume(self) -> int:
        default = DEFAULT_SWITCH_ON_VOLUME if self.is_matrix else DEFAULT_ON_VOLUME
        return int(
            self.entry.options.get(
                CONF_ON_VOLUME, self.entry.data.get(CONF_ON_VOLUME, default)
            )
        )

    @property
    def eq_enabled(self) -> bool:
        if self.is_matrix:
            return False
        return bool(
            self.entry.options.get(CONF_ENABLE_EQ, self.entry.data.get(CONF_ENABLE_EQ, True))
        )

    @property
    def host(self) -> str:
        return self.entry.data[CONF_HOST]

    def linked_switch(self) -> C4AudioCoordinator | None:
        if self.is_matrix:
            return None
        entry_id = self.entry.options.get(
            CONF_SWITCH_ENTRY_ID, self.entry.data.get(CONF_SWITCH_ENTRY_ID)
        )
        if not entry_id:
            return None
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None or not getattr(coordinator, "is_matrix", False):
            return None
        return coordinator

    def media_source_list(self) -> list[str]:
        switch = self.linked_switch()
        if switch is None:
            return visible_names(self.source_names)
        return merged_source_list(self.source_names, switch.source_names, self.switch_feeds)

    def media_source_name(self, zone: int) -> str | None:
        amp_input = self.state.zones[zone].source
        switch = self.linked_switch()
        switch_input = None
        switch_names = None
        if switch is not None and amp_input in self.switch_feeds:
            switch_output = self.switch_feeds[amp_input]
            switch_input = switch.state.zones.get(switch_output, ZoneState()).source
            switch_names = switch.source_names
        return displayed_amp_source(
            amp_input, self.source_names, self.switch_feeds, switch_input, switch_names
        )

    def zone_is_on(self, zone: int) -> bool:
        return self.state.zones[zone].source > 0

    async def async_start(self) -> None:
        await self.client.async_start()
        if self.model.get("wake_power_save"):
            await self.client.async_send(*self.cmds.set_power_save("00"))

    async def async_shutdown(self) -> None:
        await self.client.async_stop()

    async def async_send_raw(self, body: str) -> str | None:
        text = body.strip()
        if text.startswith(("0s", "0g")):
            packet = await self.client.async_send("0s", text)
            return packet.raw if packet else None
        get_bodies = {
            "c4.sy.fwv",
            "c4.sy.info",
            "c4.amp.ain",
            "c4.amp.avol",
            "c4.amp.amut",
            "c4.amp.psave",
            "c4.amp.abss",
            "c4.amp.atrb",
            "c4.amp.abal",
            "c4.asw.ain",
            "c4.asw.avol",
            "c4.asw.amut",
            "c4.asw.abss",
            "c4.asw.atrb",
            "c4.asw.abal",
        }
        prefix = "0g" if text in get_bodies or text.startswith(("c4.amp.digi", "c4.asw.ain", "c4.asw.avol", "c4.asw.amut")) else "0s"
        if " " not in text and text.startswith("c4."):
            prefix = "0g"
        packet = await self.client.async_send(prefix, text)
        return packet.raw if packet else None

    async def async_select_source(self, zone: int, source_name: str) -> None:
        switch = self.linked_switch()
        switch_names = switch.source_names if switch else None
        try:
            kind, amp_input, switch_output, switch_input = resolve_source_choice(
                source_name, self.source_names, switch_names, self.switch_feeds
            )
        except ValueError as err:
            raise HomeAssistantError(f"Unknown source {source_name}") from err

        if kind == KIND_SWITCH and switch is not None and switch_output and switch_input:
            await switch.async_route_output(switch_output, switch_input)
            await self.async_route_output(zone, amp_input)
        else:
            await self.async_route_output(zone, amp_input)
        await self._async_confirm()

    async def async_route_output(self, zone: int, source: int) -> None:
        if not self.is_matrix and source > 0:
            await self.client.async_send(*self.cmds.get_digital(source))
        await self.client.async_send(*self.cmds.set_output(zone, source))
        if source > 0:
            await self.client.async_send(*self.cmds.set_mute(zone, False))
            self.state.zones[zone].muted = False
        self.state.zones[zone].source = source
        self.async_set_updated_data(self.state)

    async def async_turn_on(self, zone: int) -> None:
        current = self.state.zones[zone]
        source = current.source or 1
        volume = current.volume or self.on_volume
        if self.model.get("wake_power_save"):
            await self.client.async_send(*self.cmds.set_power_save("00"))
        await self.async_route_output(zone, source)
        await self.client.async_send(*self.cmds.set_volume(zone, volume))
        current.volume = volume
        self.async_set_updated_data(self.state)
        await self._async_confirm()

    async def async_turn_off(self, zone: int, *, confirm: bool = True) -> None:
        await self.client.async_send(*self.cmds.set_mute(zone, True))
        await self.client.async_send(*self.cmds.set_output(zone, 0))
        self.state.zones[zone].source = 0
        self.state.zones[zone].muted = True
        self.async_set_updated_data(self.state)
        if confirm:
            await self._async_confirm()

    async def async_turn_off_all(self) -> None:
        for zone in self.enabled_zones:
            await self.async_turn_off(zone, confirm=False)
        await self._async_confirm()

    async def async_set_volume(self, zone: int, volume: float) -> None:
        percent = int(round(volume * 100)) if volume <= 1 else int(round(volume))
        percent = max(0, min(100, percent))
        await self.client.async_send(*self.cmds.set_volume(zone, percent))
        self.state.zones[zone].volume = percent
        if percent > 0:
            self.state.zones[zone].muted = False
        self.async_set_updated_data(self.state)

    async def async_adjust_volume(self, zone: int, delta: int) -> None:
        current = self.state.zones[zone].volume
        await self.async_set_volume(zone, current + delta)

    async def async_set_mute(self, zone: int, muted: bool) -> None:
        await self.client.async_send(*self.cmds.set_mute(zone, muted))
        self.state.zones[zone].muted = muted
        self.async_set_updated_data(self.state)

    async def async_set_bass(self, zone: int, db: int) -> None:
        await self.client.async_send(*self.cmds.set_bass(zone, db))
        self.state.zones[zone].bass = db
        self.async_set_updated_data(self.state)

    async def async_set_treble(self, zone: int, db: int) -> None:
        await self.client.async_send(*self.cmds.set_treble(zone, db))
        self.state.zones[zone].treble = db
        self.async_set_updated_data(self.state)

    async def _async_confirm(self) -> None:
        """Re-read hardware after a SET so HA matches the chassis."""
        await self.async_request_refresh()
        switch = self.linked_switch()
        if switch is not None:
            await switch.async_request_refresh()

    async def _async_update_data(self) -> DeviceState:
        fw = await self.client.async_send(*self.cmds.get_firmware())
        if fw is None:
            self.state.available = False
            raise UpdateFailed(f"No reply from {self.host}:{self.entry.data[CONF_PORT]}")
        self.state.available = True
        if fw.args:
            self.state.firmware = fw.args[0].strip('"')

        await self._poll_list(self.cmds.get_inputs(), self._apply_sources)
        await self._poll_list(self.cmds.get_volumes(), self._apply_volumes)
        await self._poll_list(self.cmds.get_mutes(), self._apply_mutes)
        if self.eq_enabled:
            await self._poll_list(self.cmds.get_bass(), self._apply_bass)
            await self._poll_list(self.cmds.get_treble(), self._apply_treble)
        return self.state

    async def _poll_list(self, command: tuple[str, str], apply) -> None:  # noqa: ANN001
        packet = await self.client.async_send(*command)
        if packet is None or packet.status_code in {"n01", "e00"}:
            return
        apply(parse_hex_list(packet.args))

    def _apply_sources(self, values: list[int | None]) -> None:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is None:
                continue
            self.state.zones[index].source = value

    def _apply_volumes(self, values: list[int | None]) -> None:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is None:
                continue
            self.state.zones[index].volume = self.cmds.decode_volume(f"{value:02x}")

    def _apply_mutes(self, values: list[int | None]) -> None:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is None:
                continue
            self.state.zones[index].muted = bool(value)

    def _apply_bass(self, values: list[int | None]) -> None:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is None:
                continue
            self.state.zones[index].bass = hex_to_signed_gain(f"{value:02x}")

    def _apply_treble(self, values: list[int | None]) -> None:
        for index, value in enumerate(values[: self.zone_count], start=1):
            if value is None:
                continue
            self.state.zones[index].treble = hex_to_signed_gain(f"{value:02x}")

    @callback
    def _on_packet(self, packet: ParsedPacket) -> None:
        if packet.kind != "status" or not packet.command:
            return
        cmd = packet.command
        args = packet.args
        if cmd == f"{self.cmds.ns}.out" and len(args) >= 2:
            zone = from_hex_byte(args[0])
            source = from_hex_byte(args[1])
            if zone in self.state.zones:
                self.state.zones[zone].source = source
        elif cmd == f"{self.cmds.ns}.mute" and len(args) >= 2:
            zone = from_hex_byte(args[0])
            if zone in self.state.zones:
                self.state.zones[zone].muted = from_hex_byte(args[1]) == 1
        elif cmd in {f"{self.cmds.ns}.chvol", f"{self.cmds.ns}.vol"} and len(args) >= 2:
            zone = from_hex_byte(args[0])
            if zone in self.state.zones:
                self.state.zones[zone].volume = self.cmds.decode_volume(args[1])
        else:
            return
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, self.state)
