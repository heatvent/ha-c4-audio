"""Protocol unit tests (no Home Assistant required)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from protocol import (
    AmpCommands,
    DeviceCommands,
    build_frame,
    parse_packet,
    volume_hex_to_percent,
    volume_percent_to_hex,
)


def test_volume_round_trip_matches_amp108_capture():
    # Dining room capture used a7 while changing volume around 12%.
    assert volume_percent_to_hex(12) == "a7"
    assert volume_hex_to_percent("a7") == 12
    assert volume_percent_to_hex(0) == "9b"


def test_set_output_frame():
    prefix, body = AmpCommands.set_output(2, 1)
    frame = build_frame(prefix, 0xE76C, body)
    assert frame == b"0se76c c4.amp.out 02 01\r\n"


def test_parse_reply_and_status():
    reply = parse_packet(b'0r630b 000 c4.sy.fwv "03.24.45"')
    assert reply.kind == "reply"
    assert reply.sequence == 0x630B
    assert reply.status_code == "000"
    assert reply.args[0] == '"03.24.45"'

    status = parse_packet("0t0040 sa c4.amp.mute 02 00")
    assert status.kind == "status"
    assert status.command == "c4.amp.mute"
    assert status.args == ["02", "00"]


def test_turn_off_is_source_zero():
    _prefix, body = AmpCommands.set_output(1, 0)
    assert body == "c4.amp.out 01 00"


def test_switch_namespace_and_unity_volume():
    cmds = DeviceCommands("c4.asw", "vol", "percent_hex")
    _prefix, route = cmds.set_output(16, 4)
    assert route == "c4.asw.out 10 04"
    _prefix, vol = cmds.set_volume(1, 100)
    assert vol == "c4.asw.vol 01 64"
    assert cmds.decode_volume("64") == 100


def test_amp_mute_requires_second_byte():
    cmds = DeviceCommands("c4.amp", "chvol", "offset")
    _prefix, body = cmds.set_mute(2, False)
    assert body == "c4.amp.mute 02 00"
