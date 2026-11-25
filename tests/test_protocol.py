"""Protocol unit tests (no Home Assistant required)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from protocol import (
    AmpCommands,
    build_frame,
    parse_packet,
    split_user_command,
    volume_hex_to_percent,
    volume_percent_to_hex,
)


def test_volume_round_trip_matches_amp108_capture():
    # Dining room capture used a7 while changing volume around 12%.
    assert volume_percent_to_hex(12) == "a7"
    assert volume_hex_to_percent("a7") == 12
    assert volume_percent_to_hex(0) == "9b"


def test_set_output_frame():
    prefix, body = AmpCommands().set_output(2, 1)
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
    _prefix, body = AmpCommands().set_output(1, 0)
    assert body == "c4.amp.out 01 00"


def test_zone_16_is_hex_10():
    _prefix, body = AmpCommands().set_output(16, 4)
    assert body == "c4.amp.out 10 04"


def test_amp_volume_command():
    cmds = AmpCommands()
    _prefix, body = cmds.set_volume(1, 12)
    assert body == "c4.amp.chvol 01 a7"
    assert cmds.decode_volume("a7") == 12


def test_split_user_command_get_vs_set():
    assert split_user_command("c4.amp.avol") == ("0g", "c4.amp.avol")
    assert split_user_command("0g c4.amp.avol") == ("0g", "c4.amp.avol")
    assert split_user_command("0g630b c4.amp.avol") == ("0g", "c4.amp.avol")
    assert split_user_command("c4.amp.out 02 01") == ("0s", "c4.amp.out 02 01")
    assert split_user_command("0s c4.amp.mute 02 00") == ("0s", "c4.amp.mute 02 00")


def test_amp_volume_limit_command():
    cmds = AmpCommands()
    _prefix, body = cmds.set_volume_max(2, 40)
    assert body == "c4.amp.chvolmax 02 c3"
    _prefix, get_body = cmds.get_volume_limits()
    assert get_body == "c4.amp.vlim"
    cmds = AmpCommands()
    _prefix, body = cmds.set_mute(2, False)
    assert body == "c4.amp.mute 02 00"
