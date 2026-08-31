"""Encode/decode Control4 Ethernet audio UDP strings.

Packet shape captured from a C4-AMP108-1B (port 8750):

    0se76c c4.amp.out 02 01\\r\\n
    0re76c v01
    0t0040 sa c4.amp.mute 02 00

The C4-16AMP3-B uses the same `c4.amp.*` names with more zone slots.
The AVM-16S1-B / C4-16ZAMSV3-B audio switch uses `c4.asw.*` (not `c4.amp`).
Switch volume is percent as hex (`64` = 100 = unity), not percent+155.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from .const import (
        CMD_PREFIX_GET,
        CMD_PREFIX_SET,
        REPLY_PREFIX,
        STATUS_PREFIX,
        VOLUME_OFFSET,
    )
except ImportError:  # running tests without the HA package
    from const import (  # type: ignore
        CMD_PREFIX_GET,
        CMD_PREFIX_SET,
        REPLY_PREFIX,
        STATUS_PREFIX,
        VOLUME_OFFSET,
    )

_HEX_BYTE = re.compile(r"^[0-9a-fA-F]{2}$")


def to_hex_byte(value: int) -> str:
    return f"{int(value) & 0xFF:02x}"


def from_hex_byte(token: str) -> int:
    return int(token.strip(), 16)


def volume_percent_to_hex(percent: float) -> str:
    pct = max(0, min(100, int(round(percent))))
    return to_hex_byte(pct + VOLUME_OFFSET)


def volume_hex_to_percent(token: str) -> int:
    raw = from_hex_byte(token)
    return max(0, min(100, raw - VOLUME_OFFSET))


def signed_gain_to_hex(db: int) -> str:
    """Map -12..+12 dB to a two's-complement hex byte."""
    db = max(-12, min(12, int(db)))
    return to_hex_byte(db & 0xFF)


def hex_to_signed_gain(token: str) -> int:
    raw = from_hex_byte(token)
    if raw >= 128:
        raw -= 256
    return max(-12, min(12, raw))


def build_frame(prefix: str, sequence: int, body: str) -> bytes:
    seq = sequence & 0xFFFF
    payload = f"{prefix}{seq:04x} {body.strip()}\r\n"
    return payload.encode("ascii")


def next_sequence(current: int) -> int:
    return (current + 1) & 0xFFFF


@dataclass(slots=True)
class ParsedPacket:
    kind: str  # "reply" | "status" | "other"
    sequence: int | None
    status_code: str | None
    command: str | None
    args: list[str]
    raw: str


def parse_packet(data: bytes | str) -> ParsedPacket | None:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
    else:
        text = data
    text = text.strip()
    if not text:
        return None

    parts = text.split()
    header = parts[0]
    if len(header) < 3:
        return ParsedPacket("other", None, None, None, [], text)

    tag = header[:2]
    seq_hex = header[2:]
    sequence = None
    if seq_hex and all(c in "0123456789abcdefABCDEF" for c in seq_hex):
        try:
            sequence = int(seq_hex, 16)
        except ValueError:
            sequence = None

    if tag == REPLY_PREFIX:
        # 0rXXXX 000 [command args...]
        # 0rXXXX v01
        # 0rXXXX n01
        rest = parts[1:]
        status = rest[0] if rest else None
        cmd = None
        args: list[str] = []
        if len(rest) >= 2 and rest[1].startswith("c4."):
            cmd = rest[1]
            args = rest[2:]
        return ParsedPacket("reply", sequence, status, cmd, args, text)

    if tag == STATUS_PREFIX:
        # 0t0040 sa c4.amp.mute 02 00
        rest = parts[1:]
        if rest and rest[0] in {"sa", "nsa"}:
            rest = rest[1:]
        cmd = rest[0] if rest else None
        args = rest[1:] if len(rest) > 1 else []
        return ParsedPacket("status", sequence, None, cmd, args, text)

    return ParsedPacket("other", sequence, None, None, parts[1:], text)


def parse_hex_list(tokens: list[str]) -> list[int | None]:
    values: list[int | None] = []
    for token in tokens:
        if _HEX_BYTE.match(token):
            values.append(from_hex_byte(token))
        else:
            values.append(None)
    return values


class DeviceCommands:
    """Builders for c4.amp.* (amplifiers) or c4.asw.* (audio switch)."""

    def __init__(self, namespace: str = "c4.amp", volume_set: str = "chvol", volume_mode: str = "offset") -> None:
        self.ns = namespace
        self.volume_set = volume_set
        self.volume_mode = volume_mode

    def get_firmware(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, "c4.sy.fwv"

    def get_info(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, "c4.sy.info"

    def get_power_save(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.psave"

    def set_power_save(self, mode: str) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.psave {mode}"

    def get_inputs(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.ain"

    def get_volumes(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.avol"

    def get_mutes(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.amut"

    def get_bass(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.abss"

    def get_treble(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.atrb"

    def get_balance(self) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.abal"

    def get_digital(self, input_index: int) -> tuple[str, str]:
        return CMD_PREFIX_GET, f"{self.ns}.digi {to_hex_byte(input_index)}"

    def set_output(self, zone: int, source: int) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.out {to_hex_byte(zone)} {to_hex_byte(source)}"

    def set_mute(self, zone: int, muted: bool) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.mute {to_hex_byte(zone)} {to_hex_byte(1 if muted else 0)}"

    def encode_volume(self, percent: float) -> str:
        pct = max(0, min(100, int(round(percent))))
        if self.volume_mode == "percent_hex":
            return to_hex_byte(pct)
        return volume_percent_to_hex(pct)

    def decode_volume(self, token: str) -> int:
        if self.volume_mode == "percent_hex":
            return max(0, min(100, from_hex_byte(token)))
        return volume_hex_to_percent(token)

    def set_volume(self, zone: int, percent: float) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.{self.volume_set} {to_hex_byte(zone)} {self.encode_volume(percent)}"

    def set_bass(self, zone: int, db: int) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.bassgain {to_hex_byte(zone)} {signed_gain_to_hex(db)}"

    def set_treble(self, zone: int, db: int) -> tuple[str, str]:
        return CMD_PREFIX_SET, f"{self.ns}.trebgain {to_hex_byte(zone)} {signed_gain_to_hex(db)}"


# Back-compat name used by unit tests.
class AmpCommands(DeviceCommands):
    def __init__(self) -> None:
        super().__init__("c4.amp", "chvol", "offset")

    @staticmethod
    def set_output(zone: int, source: int) -> tuple[str, str]:
        return DeviceCommands("c4.amp").set_output(zone, source)
